"""Offline-first Census TIGERweb source snapshot adapter.

The adapter keeps source acquisition separate from parsing:

``fetch`` -> ``verify`` -> ``cache`` -> ``parse``

Only TIGERweb attributes are requested. Geometry is intentionally excluded;
feature-specific GeoJSON URL construction belongs to the downstream resolver.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from logging import getLogger
from pathlib import Path
from typing import Any, Mapping, Protocol
from urllib.parse import urlencode

logger = getLogger(__name__)

TIGERWEB_BASE_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb"
)
DEFAULT_RESULT_RECORD_COUNT = 100_000
MANIFEST_SCHEMA_VERSION = 1


class TigerAdapterError(Exception):
    """Base error for TIGER source snapshot operations."""


class TigerSourceResponseError(TigerAdapterError):
    """Raised when TIGERweb returns malformed, partial, or error data."""


class TigerCacheMissError(TigerAdapterError):
    """Raised when a conditional request has no existing cached snapshot."""


class TigerSnapshotIntegrityError(TigerAdapterError):
    """Raised when a cached snapshot does not match its manifest checksum."""


class BytesFetcher(Protocol):
    """Minimal interface implemented by ``AsyncDownloader``."""

    async def fetch_bytes(
        self, url: str, *, force: bool = False
    ) -> bytes | None: ...


class TigerGeography(StrEnum):
    """TIGER geography classes required by the GUS rework."""

    STATE = "state"
    COUNTY = "county"
    PLACE = "place"
    COUNTY_SUBDIVISION = "county_subdivision"
    UNIFIED_SCHOOL_DISTRICT = "unified_school_district"
    SECONDARY_SCHOOL_DISTRICT = "secondary_school_district"
    ELEMENTARY_SCHOOL_DISTRICT = "elementary_school_district"


@dataclass(frozen=True)
class TigerLayerSpec:
    """Pinned TIGERweb layer contract for one geography class."""

    geography_type: TigerGeography
    vintage: str
    service_name: str
    layer_id: int
    layer_name: str
    geoid_length: int
    code_field: str
    code_length: int
    required_fields: tuple[str, ...]
    ansi_field: str | None = None

    @property
    def layer_url(self) -> str:
        return (
            f"{TIGERWEB_BASE_URL}/{self.service_name}/MapServer/"
            f"{self.layer_id}"
        )

    @property
    def query_fields(self) -> tuple[str, ...]:
        fields = list(self.required_fields)
        if self.ansi_field and self.ansi_field not in fields:
            fields.append(self.ansi_field)
        return tuple(fields)


_COMMON_FIELDS = (
    "GEOID",
    "STATE",
    "BASENAME",
    "NAME",
    "LSADC",
    "FUNCSTAT",
    "MTFCC",
    "OID",
)

# These layer IDs are under the versioned ``ACS 2025`` groups in TIGERweb,
# not the mutable current-vintage layers at the top of each MapServer.
TIGER_LAYERS_2025: Mapping[TigerGeography, TigerLayerSpec] = {
    TigerGeography.STATE: TigerLayerSpec(
        geography_type=TigerGeography.STATE,
        vintage="2025",
        service_name="State_County",
        layer_id=18,
        layer_name="States",
        geoid_length=2,
        code_field="STATE",
        code_length=2,
        required_fields=_COMMON_FIELDS
        + ("STATENS", "STUSAB", "REGION", "DIVISION"),
        ansi_field="STATENS",
    ),
    TigerGeography.COUNTY: TigerLayerSpec(
        geography_type=TigerGeography.COUNTY,
        vintage="2025",
        service_name="State_County",
        layer_id=19,
        layer_name="Counties",
        geoid_length=5,
        code_field="COUNTY",
        code_length=3,
        required_fields=_COMMON_FIELDS + ("COUNTY", "COUNTYNS"),
        ansi_field="COUNTYNS",
    ),
    TigerGeography.PLACE: TigerLayerSpec(
        geography_type=TigerGeography.PLACE,
        vintage="2025",
        service_name="Places_CouSub_ConCity_SubMCD",
        layer_id=11,
        layer_name="Incorporated Places",
        geoid_length=7,
        code_field="PLACE",
        code_length=5,
        required_fields=_COMMON_FIELDS + ("PLACE", "PLACENS"),
        ansi_field="PLACENS",
    ),
    TigerGeography.COUNTY_SUBDIVISION: TigerLayerSpec(
        geography_type=TigerGeography.COUNTY_SUBDIVISION,
        vintage="2025",
        service_name="Places_CouSub_ConCity_SubMCD",
        layer_id=8,
        layer_name="County Subdivisions",
        geoid_length=10,
        code_field="COUSUB",
        code_length=5,
        required_fields=_COMMON_FIELDS
        + ("COUNTY", "COUSUB", "COUSUBNS"),
        ansi_field="COUSUBNS",
    ),
    TigerGeography.UNIFIED_SCHOOL_DISTRICT: TigerLayerSpec(
        geography_type=TigerGeography.UNIFIED_SCHOOL_DISTRICT,
        vintage="2025",
        service_name="School",
        layer_id=5,
        layer_name="Unified School Districts",
        geoid_length=7,
        code_field="SDUNI",
        code_length=5,
        required_fields=_COMMON_FIELDS
        + ("SDUNI", "SDTYP", "LOGRADE", "HIGRADE"),
    ),
    TigerGeography.SECONDARY_SCHOOL_DISTRICT: TigerLayerSpec(
        geography_type=TigerGeography.SECONDARY_SCHOOL_DISTRICT,
        vintage="2025",
        service_name="School",
        layer_id=6,
        layer_name="Secondary School Districts",
        geoid_length=7,
        code_field="SDSEC",
        code_length=5,
        required_fields=_COMMON_FIELDS
        + ("SDSEC", "SDTYP", "LOGRADE", "HIGRADE"),
    ),
    TigerGeography.ELEMENTARY_SCHOOL_DISTRICT: TigerLayerSpec(
        geography_type=TigerGeography.ELEMENTARY_SCHOOL_DISTRICT,
        vintage="2025",
        service_name="School",
        layer_id=7,
        layer_name="Elementary School Districts",
        geoid_length=7,
        code_field="SDELM",
        code_length=5,
        required_fields=_COMMON_FIELDS
        + ("SDELM", "SDTYP", "LOGRADE", "HIGRADE"),
    ),
}

_LAYER_CATALOGS: Mapping[
    str, Mapping[TigerGeography, TigerLayerSpec]
] = {"2025": TIGER_LAYERS_2025}


@dataclass(frozen=True)
class VerifiedTigerSnapshot:
    """Structurally verified source response ready to cache."""

    spec: TigerLayerSpec
    source_url: str
    payload: bytes
    record_count: int


@dataclass(frozen=True)
class TigerSnapshotMetadata:
    """Sidecar metadata for one cached TIGER source response."""

    geography_type: TigerGeography
    vintage: str
    service_name: str
    layer_id: int
    layer_name: str
    source_url: str
    retrieved_at: str
    sha256: str
    record_count: int
    snapshot_path: Path
    manifest_path: Path


@dataclass(frozen=True)
class TigerRecord:
    """Normalized geography attributes parsed from a TIGER snapshot."""

    geography_type: TigerGeography
    geoid: str
    name: str
    basename: str
    state_fips: str
    state_abbreviation: str | None
    county_fips: str | None
    place_fips: str | None
    county_subdivision_fips: str | None
    school_district_fips: str | None
    ansi_code: str | None
    lsad_code: str
    functional_status: str
    mtfcc: str
    source_oid: str
    school_district_type: str | None
    low_grade: str | None
    high_grade: str | None


@dataclass(frozen=True)
class TigerParseError:
    """One source row that could not be normalized."""

    feature_index: int
    geoid: str | None
    message: str
    attributes: Mapping[str, Any]


@dataclass(frozen=True)
class TigerParseResult:
    """Parsed records plus explicit errors; no input row disappears."""

    records: tuple[TigerRecord, ...]
    errors: tuple[TigerParseError, ...]

    @property
    def input_count(self) -> int:
        return len(self.records) + len(self.errors)


class TigerAdapter:
    """Fetch, verify, cache, and parse pinned TIGERweb snapshots."""

    def __init__(
        self,
        cache_root: str | os.PathLike[str],
        *,
        vintage: str = "2025",
        result_record_count: int = DEFAULT_RESULT_RECORD_COUNT,
    ) -> None:
        if vintage not in _LAYER_CATALOGS:
            supported = ", ".join(sorted(_LAYER_CATALOGS))
            raise ValueError(
                f"Unsupported TIGER vintage {vintage!r}; supported: {supported}"
            )
        if result_record_count < 1:
            raise ValueError("result_record_count must be positive")

        self.cache_root = Path(cache_root)
        self.vintage = vintage
        self.result_record_count = result_record_count

    def get_spec(self, geography_type: TigerGeography) -> TigerLayerSpec:
        return _LAYER_CATALOGS[self.vintage][geography_type]

    def build_query_url(self, spec: TigerLayerSpec) -> str:
        """Build the national attributes-only query for a pinned layer."""

        params = (
            ("where", "1=1"),
            ("outFields", ",".join(spec.query_fields)),
            ("returnGeometry", "false"),
            ("orderByFields", "GEOID"),
            ("resultRecordCount", str(self.result_record_count)),
            ("f", "json"),
        )
        return f"{spec.layer_url}/query?{urlencode(params)}"

    async def fetch(
        self,
        downloader: BytesFetcher,
        geography_type: TigerGeography,
        *,
        force: bool = False,
    ) -> bytes | None:
        """Fetch raw source bytes; ``None`` means HTTP 304/not modified."""

        spec = self.get_spec(geography_type)
        return await downloader.fetch_bytes(
            self.build_query_url(spec), force=force
        )

    def verify(
        self,
        geography_type: TigerGeography,
        payload: bytes,
    ) -> VerifiedTigerSnapshot:
        """Verify ArcGIS response shape and guard against partial snapshots."""

        spec = self.get_spec(geography_type)
        source_url = self.build_query_url(spec)
        document = _load_json_object(payload, source_url=source_url)

        if "error" in document:
            raise TigerSourceResponseError(
                f"TIGERweb returned an error for {geography_type.value}: "
                f"{document['error']!r}"
            )
        if document.get("exceededTransferLimit") is True:
            raise TigerSourceResponseError(
                "TIGERweb response exceeded its transfer limit; refusing "
                "to cache a partial snapshot"
            )

        features = document.get("features")
        if not isinstance(features, list):
            raise TigerSourceResponseError(
                "TIGERweb response must contain a features list"
            )
        if not features:
            raise TigerSourceResponseError(
                "TIGERweb national layer response contained no features"
            )

        expected_fields = set(spec.query_fields)
        for index, feature in enumerate(features):
            if not isinstance(feature, Mapping):
                raise TigerSourceResponseError(
                    f"Feature {index} is not an object"
                )
            attributes = feature.get("attributes")
            if not isinstance(attributes, Mapping):
                raise TigerSourceResponseError(
                    f"Feature {index} has no attributes object"
                )
            missing = expected_fields.difference(attributes)
            if missing:
                missing_text = ", ".join(sorted(missing))
                raise TigerSourceResponseError(
                    f"Feature {index} is missing requested fields: "
                    f"{missing_text}"
                )

        return VerifiedTigerSnapshot(
            spec=spec,
            source_url=source_url,
            payload=payload,
            record_count=len(features),
        )

    def cache(
        self,
        snapshot: VerifiedTigerSnapshot,
        *,
        retrieved_at: datetime | None = None,
    ) -> TigerSnapshotMetadata:
        """Atomically cache raw bytes plus a provenance/checksum manifest."""

        snapshot_path, manifest_path = self._cache_paths(
            snapshot.spec.geography_type
        )
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        digest = sha256(snapshot.payload).hexdigest()
        timestamp = _format_utc(retrieved_at or datetime.now(timezone.utc))

        _atomic_write_bytes(snapshot_path, snapshot.payload)
        manifest = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "dataset": "census_tigerweb",
            "geography_type": snapshot.spec.geography_type.value,
            "vintage": snapshot.spec.vintage,
            "service_name": snapshot.spec.service_name,
            "layer_id": snapshot.spec.layer_id,
            "layer_name": snapshot.spec.layer_name,
            "source_url": snapshot.source_url,
            "retrieved_at": timestamp,
            "sha256": digest,
            "record_count": snapshot.record_count,
            "snapshot_file": snapshot_path.name,
        }
        _atomic_write_text(
            manifest_path,
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )

        metadata = TigerSnapshotMetadata(
            geography_type=snapshot.spec.geography_type,
            vintage=snapshot.spec.vintage,
            service_name=snapshot.spec.service_name,
            layer_id=snapshot.spec.layer_id,
            layer_name=snapshot.spec.layer_name,
            source_url=snapshot.source_url,
            retrieved_at=timestamp,
            sha256=digest,
            record_count=snapshot.record_count,
            snapshot_path=snapshot_path,
            manifest_path=manifest_path,
        )
        logger.info(
            "Cached TIGER source snapshot",
            extra={
                "geography_type": metadata.geography_type.value,
                "vintage": metadata.vintage,
                "record_count": metadata.record_count,
                "sha256": metadata.sha256,
            },
        )
        return metadata

    def load_cached_metadata(
        self, geography_type: TigerGeography
    ) -> TigerSnapshotMetadata:
        """Load and integrity-check a cached snapshot manifest."""

        spec = self.get_spec(geography_type)
        snapshot_path, manifest_path = self._cache_paths(geography_type)
        if not snapshot_path.is_file() or not manifest_path.is_file():
            raise TigerCacheMissError(
                f"No cached TIGER snapshot for {geography_type.value} "
                f"vintage {self.vintage}"
            )

        manifest = _load_json_object(
            manifest_path.read_bytes(), source_url=str(manifest_path)
        )
        schema_version = _required_manifest_int(
            manifest, "schema_version"
        )
        if schema_version != MANIFEST_SCHEMA_VERSION:
            raise TigerSnapshotIntegrityError(
                "Unsupported TIGER snapshot manifest schema version"
            )
        if manifest.get("dataset") != "census_tigerweb":
            raise TigerSnapshotIntegrityError(
                "TIGER snapshot manifest dataset is invalid"
            )
        if manifest.get("geography_type") != geography_type.value:
            raise TigerSnapshotIntegrityError(
                "TIGER snapshot manifest geography type does not match path"
            )
        if manifest.get("vintage") != self.vintage:
            raise TigerSnapshotIntegrityError(
                "TIGER snapshot manifest vintage does not match adapter"
            )
        if manifest.get("service_name") != spec.service_name:
            raise TigerSnapshotIntegrityError(
                "TIGER snapshot manifest service does not match catalog"
            )
        if manifest.get("layer_id") != spec.layer_id:
            raise TigerSnapshotIntegrityError(
                "TIGER snapshot manifest layer does not match catalog"
            )
        if manifest.get("layer_name") != spec.layer_name:
            raise TigerSnapshotIntegrityError(
                "TIGER snapshot manifest layer name does not match catalog"
            )
        if manifest.get("snapshot_file") != snapshot_path.name:
            raise TigerSnapshotIntegrityError(
                "TIGER snapshot manifest filename does not match path"
            )

        payload = snapshot_path.read_bytes()
        actual_digest = sha256(payload).hexdigest()
        expected_digest = _required_manifest_text(manifest, "sha256")
        if actual_digest != expected_digest:
            raise TigerSnapshotIntegrityError(
                f"Checksum mismatch for cached TIGER snapshot "
                f"{snapshot_path}"
            )

        verified = self.verify(geography_type, payload)
        source_url = _required_manifest_text(manifest, "source_url")
        if source_url != verified.source_url:
            raise TigerSnapshotIntegrityError(
                "TIGER snapshot source URL does not match adapter query"
            )
        record_count = _required_manifest_int(manifest, "record_count")
        if record_count != verified.record_count:
            raise TigerSnapshotIntegrityError(
                "TIGER snapshot record count does not match manifest"
            )

        return TigerSnapshotMetadata(
            geography_type=geography_type,
            vintage=self.vintage,
            service_name=spec.service_name,
            layer_id=spec.layer_id,
            layer_name=spec.layer_name,
            source_url=source_url,
            retrieved_at=_required_manifest_text(manifest, "retrieved_at"),
            sha256=expected_digest,
            record_count=record_count,
            snapshot_path=snapshot_path,
            manifest_path=manifest_path,
        )

    async def refresh(
        self,
        downloader: BytesFetcher,
        geography_type: TigerGeography,
        *,
        force: bool = False,
        retrieved_at: datetime | None = None,
    ) -> TigerSnapshotMetadata:
        """Fetch and cache a snapshot, or reuse the cache after HTTP 304."""

        payload = await self.fetch(
            downloader, geography_type, force=force
        )
        if payload is None:
            return self.load_cached_metadata(geography_type)
        verified = self.verify(geography_type, payload)
        return self.cache(verified, retrieved_at=retrieved_at)

    def parse(
        self, geography_type: TigerGeography
    ) -> TigerParseResult:
        """Parse a cached snapshot into normalized records and row errors."""

        metadata = self.load_cached_metadata(geography_type)
        document = _load_json_object(
            metadata.snapshot_path.read_bytes(),
            source_url=str(metadata.snapshot_path),
        )
        features = document.get("features")
        if not isinstance(features, list):
            raise TigerSourceResponseError(
                "Cached TIGER snapshot must contain a features list"
            )

        spec = self.get_spec(geography_type)
        records: list[TigerRecord] = []
        errors: list[TigerParseError] = []
        seen_geoids: set[str] = set()

        for index, feature in enumerate(features):
            attributes: Mapping[str, Any]
            if isinstance(feature, Mapping) and isinstance(
                feature.get("attributes"), Mapping
            ):
                attributes = feature["attributes"]
            else:
                attributes = {}

            geoid = _optional_text(attributes, "GEOID")
            try:
                record = _parse_record(spec, attributes)
                if record.geoid in seen_geoids:
                    raise ValueError(
                        f"duplicate GEOID {record.geoid!r} in snapshot"
                    )
                seen_geoids.add(record.geoid)
                records.append(record)
            except (TypeError, ValueError) as exc:
                errors.append(
                    TigerParseError(
                        feature_index=index,
                        geoid=geoid,
                        message=str(exc),
                        attributes=dict(attributes),
                    )
                )

        return TigerParseResult(
            records=tuple(records),
            errors=tuple(errors),
        )

    def _cache_paths(
        self, geography_type: TigerGeography
    ) -> tuple[Path, Path]:
        directory = self.cache_root / self.vintage
        snapshot_path = directory / f"{geography_type.value}.json"
        manifest_path = directory / (
            f"{geography_type.value}.manifest.json"
        )
        return snapshot_path, manifest_path


def _parse_record(
    spec: TigerLayerSpec, attributes: Mapping[str, Any]
) -> TigerRecord:
    geoid = _required_digits(attributes, "GEOID", spec.geoid_length)
    state_fips = _required_digits(attributes, "STATE", 2)
    local_code = _required_digits(
        attributes, spec.code_field, spec.code_length
    )

    county_fips: str | None = None
    place_fips: str | None = None
    county_subdivision_fips: str | None = None
    school_district_fips: str | None = None
    state_abbreviation: str | None = None

    if spec.geography_type is TigerGeography.STATE:
        expected_geoid = state_fips
        state_abbreviation = _required_code(attributes, "STUSAB", 2)
    elif spec.geography_type is TigerGeography.COUNTY:
        county_fips = local_code
        expected_geoid = state_fips + county_fips
    elif spec.geography_type is TigerGeography.PLACE:
        place_fips = local_code
        expected_geoid = state_fips + place_fips
    elif spec.geography_type is TigerGeography.COUNTY_SUBDIVISION:
        county_fips = _required_digits(attributes, "COUNTY", 3)
        county_subdivision_fips = local_code
        expected_geoid = (
            state_fips + county_fips + county_subdivision_fips
        )
    else:
        school_district_fips = local_code
        expected_geoid = state_fips + school_district_fips

    if geoid != expected_geoid:
        raise ValueError(
            f"GEOID {geoid!r} does not match component fields "
            f"({expected_geoid!r})"
        )

    ansi_code = (
        _optional_text(attributes, spec.ansi_field)
        if spec.ansi_field
        else None
    )
    is_school = spec.geography_type in {
        TigerGeography.UNIFIED_SCHOOL_DISTRICT,
        TigerGeography.SECONDARY_SCHOOL_DISTRICT,
        TigerGeography.ELEMENTARY_SCHOOL_DISTRICT,
    }

    return TigerRecord(
        geography_type=spec.geography_type,
        geoid=geoid,
        name=_required_text(attributes, "NAME"),
        basename=_required_text(attributes, "BASENAME"),
        state_fips=state_fips,
        state_abbreviation=state_abbreviation,
        county_fips=county_fips,
        place_fips=place_fips,
        county_subdivision_fips=county_subdivision_fips,
        school_district_fips=school_district_fips,
        ansi_code=ansi_code,
        lsad_code=_required_digits(attributes, "LSADC", 2),
        functional_status=_required_code(attributes, "FUNCSTAT", 1),
        mtfcc=_required_code(attributes, "MTFCC", 5),
        source_oid=_required_text(attributes, "OID"),
        school_district_type=(
            _optional_code(attributes, "SDTYP", 1)
            if is_school
            else None
        ),
        low_grade=(
            _required_code(attributes, "LOGRADE", 2)
            if is_school
            else None
        ),
        high_grade=(
            _required_code(attributes, "HIGRADE", 2)
            if is_school
            else None
        ),
    )


def _load_json_object(
    payload: bytes, *, source_url: str
) -> dict[str, Any]:
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TigerSourceResponseError(
            f"Invalid JSON from {source_url}: {exc}"
        ) from exc
    if not isinstance(document, dict):
        raise TigerSourceResponseError(
            f"JSON from {source_url} must be an object"
        )
    return document


def _required_text(attributes: Mapping[str, Any], field: str) -> str:
    value = attributes.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(
    attributes: Mapping[str, Any], field: str | None
) -> str | None:
    if field is None:
        return None
    value = attributes.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _required_digits(
    attributes: Mapping[str, Any], field: str, length: int
) -> str:
    value = _required_text(attributes, field)
    if len(value) != length or not value.isdigit():
        raise ValueError(
            f"{field} must be an exact {length}-digit string"
        )
    return value


def _required_code(
    attributes: Mapping[str, Any], field: str, length: int
) -> str:
    value = _required_text(attributes, field)
    if len(value) != length or not value.isalnum():
        raise ValueError(
            f"{field} must be an exact {length}-character code string"
        )
    return value


def _optional_code(
    attributes: Mapping[str, Any], field: str, length: int
) -> str | None:
    value = _optional_text(attributes, field)
    if value is None:
        return None
    if len(value) != length or not value.isalnum():
        raise ValueError(
            f"{field} must be blank or an exact "
            f"{length}-character code string"
        )
    return value


def _required_manifest_text(
    manifest: Mapping[str, Any], field: str
) -> str:
    value = manifest.get(field)
    if not isinstance(value, str) or not value:
        raise TigerSnapshotIntegrityError(
            f"TIGER snapshot manifest field {field!r} is invalid"
        )
    return value


def _required_manifest_int(
    manifest: Mapping[str, Any], field: str
) -> int:
    value = manifest.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TigerSnapshotIntegrityError(
            f"TIGER snapshot manifest field {field!r} is invalid"
        )
    return value


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("retrieved_at must be timezone-aware")
    normalized = value.astimezone(timezone.utc)
    return normalized.isoformat().replace("+00:00", "Z")


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def _atomic_write_text(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)
