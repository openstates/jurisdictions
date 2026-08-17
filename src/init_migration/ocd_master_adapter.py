"""Offline-first adapter for the Open Civic Data US division ID master.

The adapter keeps source acquisition separate from downstream OCDID generation:

``fetch`` -> ``verify`` -> ``cache`` -> ``parse``

Exact membership is the only acceptance rule. Optional nearest-ID suggestions are
explicitly review-only diagnostics and never change a negative membership result.
"""

from __future__ import annotations

import csv
import io
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1, sha256
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Literal, Mapping, Protocol

from rapidfuzz import fuzz, process

from src.models.ocdid import OCDIdParsed

MANIFEST_SCHEMA_VERSION = 1
MAX_SOURCE_BYTES = 96 * 1024 * 1024
OCD_MASTER_HEADERS = (
    "id",
    "name",
    "sameAs",
    "sameAsNote",
    "validThrough",
    "census_geoid",
    "census_geoid_12",
    "census_geoid_14",
    "openstates_district",
    "placeholder_id",
    "sch_dist_stateid",
    "state_id",
    "validFrom",
)


class OCDMasterAdapterError(Exception):
    """Base error for OCD master source snapshot operations."""


class OCDMasterSourceError(OCDMasterAdapterError):
    """Raised when source bytes do not satisfy the pinned CSV contract."""


class OCDMasterCacheMissError(OCDMasterAdapterError):
    """Raised when no complete cached snapshot exists."""


class OCDMasterSnapshotIntegrityError(OCDMasterAdapterError):
    """Raised when cached bytes or metadata fail integrity validation."""


class BytesFetcher(Protocol):
    """Minimal network interface implemented by ``AsyncDownloader``."""

    async def fetch_bytes(
        self, url: str, *, force: bool = False
    ) -> bytes | None: ...


@dataclass(frozen=True)
class OCDMasterReleaseSpec:
    """Pinned source contract for one OCD division ID master revision."""

    repository: str
    revision: str
    source_path: str
    source_url: str
    expected_git_blob_sha1: str | None
    headers: tuple[str, ...] = OCD_MASTER_HEADERS


OCD_MASTER_RELEASE = OCDMasterReleaseSpec(
    repository="opencivicdata/ocd-division-ids",
    revision="a52719a15852fc8c8418194016c16657591930ad",
    source_path="identifiers/country-us.csv",
    source_url=(
        "https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/"
        "a52719a15852fc8c8418194016c16657591930ad/"
        "identifiers/country-us.csv"
    ),
    expected_git_blob_sha1="bca1de20902adabb89961d08e68e0400d41dde50",
)


@dataclass(frozen=True)
class VerifiedOCDMasterSnapshot:
    """Verified source bytes ready to cache or parse."""

    spec: OCDMasterReleaseSpec
    payload: bytes
    source_sha256: str
    source_git_blob_sha1: str
    source_size: int
    data_row_count: int


@dataclass(frozen=True)
class OCDMasterSnapshotMetadata:
    """Provenance and integrity metadata for one cached source snapshot."""

    source_repository: str
    source_revision: str
    source_repository_path: str
    source_url: str
    retrieved_at: str
    source_sha256: str
    source_git_blob_sha1: str
    source_size: int
    data_row_count: int
    headers: tuple[str, ...]
    cache_path: Path
    manifest_path: Path


@dataclass(frozen=True)
class OCDMasterSourceRecord:
    """One exact source membership record with row provenance."""

    ocdid: str
    name: str
    source_row_number: int


@dataclass(frozen=True)
class OCDMasterParseResult:
    """Validated source records emitted from one pinned snapshot."""

    source_repository: str
    source_revision: str
    source_url: str
    source_sha256: str
    records: tuple[OCDMasterSourceRecord, ...]

    @property
    def record_count(self) -> int:
        return len(self.records)


@dataclass(frozen=True)
class OCDMasterSuggestion:
    """A nearest-ID diagnostic that requires human review."""

    candidate_ocdid: str
    suggested_ocdid: str
    suggested_name: str
    score: float
    review_only: Literal[True] = True


class OCDMasterIndex:
    """Immutable exact-membership index over validated OCD master records."""

    def __init__(self, records: Iterable[OCDMasterSourceRecord]) -> None:
        by_ocdid: dict[str, OCDMasterSourceRecord] = {}
        choices_by_scope: dict[tuple[str, str], list[tuple[str, str]]] = {}

        for record in records:
            parsed = _parse_division_ocdid(record.ocdid)
            if record.ocdid in by_ocdid:
                raise ValueError(f"Duplicate OCD ID in index: {record.ocdid}")
            by_ocdid[record.ocdid] = record
            parent, segment_type, leaf = _suggestion_scope(parsed)
            choices_by_scope.setdefault((parent, segment_type), []).append(
                (leaf, record.ocdid)
            )

        frozen_choices = {
            scope: tuple(sorted(choices, key=lambda item: item[1]))
            for scope, choices in choices_by_scope.items()
        }
        self._by_ocdid: Mapping[str, OCDMasterSourceRecord] = MappingProxyType(
            by_ocdid
        )
        self._choices_by_scope: Mapping[
            tuple[str, str], tuple[tuple[str, str], ...]
        ] = MappingProxyType(frozen_choices)

    def __len__(self) -> int:
        return len(self._by_ocdid)

    def exact_lookup(self, candidate_ocdid: str) -> OCDMasterSourceRecord | None:
        """Return the literal exact match, or ``None`` for a valid miss."""

        _parse_division_ocdid(candidate_ocdid)
        return self._by_ocdid.get(candidate_ocdid)

    def contains(self, candidate_ocdid: str) -> bool:
        """Return whether a valid candidate is an exact source member."""

        return self.exact_lookup(candidate_ocdid) is not None

    def suggest_for_review(
        self,
        candidate_ocdid: str,
        *,
        limit: int = 5,
        score_cutoff: float = 70.0,
    ) -> tuple[OCDMasterSuggestion, ...]:
        """Return same-parent nearest IDs without changing exact membership.

        Suggestions are intentionally limited to siblings with the same segment
        type under the candidate's immediate parent. They are diagnostics for a
        person to inspect; callers
        must never promote a suggestion into an accepted match automatically.
        """

        parsed_candidate = _parse_division_ocdid(candidate_ocdid)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        if not 0 <= score_cutoff <= 100:
            raise ValueError("score_cutoff must be between 0 and 100")
        if candidate_ocdid in self._by_ocdid:
            return ()

        parent, segment_type, candidate_leaf = _suggestion_scope(parsed_candidate)
        scoped_choices = self._choices_by_scope.get((parent, segment_type), ())
        if not scoped_choices:
            return ()

        leaf_choices = tuple(leaf for leaf, _ in scoped_choices)
        matches = process.extract(
            candidate_leaf,
            leaf_choices,
            scorer=fuzz.ratio,
            limit=limit,
            score_cutoff=score_cutoff,
        )
        ordered_matches = sorted(
            matches,
            key=lambda item: (-item[1], scoped_choices[item[2]][1]),
        )
        return tuple(
            OCDMasterSuggestion(
                candidate_ocdid=candidate_ocdid,
                suggested_ocdid=scoped_choices[index][1],
                suggested_name=self._by_ocdid[scoped_choices[index][1]].name,
                score=float(score),
            )
            for _, score, index in ordered_matches
        )


class OCDMasterAdapter:
    """Fetch, verify, cache, and parse a pinned US OCD master snapshot."""

    def __init__(
        self,
        cache_root: str | os.PathLike[str],
        *,
        release_spec: OCDMasterReleaseSpec = OCD_MASTER_RELEASE,
        max_source_bytes: int = MAX_SOURCE_BYTES,
    ) -> None:
        if max_source_bytes < 1:
            raise ValueError("max_source_bytes must be positive")
        if not release_spec.revision:
            raise ValueError("release_spec revision must not be empty")
        if not release_spec.headers:
            raise ValueError("release_spec headers must not be empty")

        self.cache_root = Path(cache_root)
        self.release_spec = release_spec
        self.max_source_bytes = max_source_bytes

    async def fetch(
        self,
        downloader: BytesFetcher,
        *,
        force: bool = False,
    ) -> bytes | None:
        """Fetch the pinned source; ``None`` means not modified."""

        return await downloader.fetch_bytes(
            self.release_spec.source_url,
            force=force,
        )

    def verify(self, payload: bytes) -> VerifiedOCDMasterSnapshot:
        """Verify pinned bytes, exact headers, IDs, and duplicate-free rows."""

        if not payload:
            raise OCDMasterSourceError("OCD master source is empty")
        if len(payload) > self.max_source_bytes:
            raise OCDMasterSourceError(
                "OCD master source exceeds the configured size limit"
            )
        if b"\x00" in payload:
            raise OCDMasterSourceError("OCD master source contains NUL bytes")

        source_git_blob_sha1 = _git_blob_sha1(payload)
        expected_blob_sha1 = self.release_spec.expected_git_blob_sha1
        if expected_blob_sha1 and source_git_blob_sha1 != expected_blob_sha1:
            raise OCDMasterSourceError(
                "OCD master source does not match the pinned Git blob"
            )

        data_row_count = _scan_rows(
            payload,
            self.release_spec,
            collect_records=False,
        )[0]
        return VerifiedOCDMasterSnapshot(
            spec=self.release_spec,
            payload=payload,
            source_sha256=sha256(payload).hexdigest(),
            source_git_blob_sha1=source_git_blob_sha1,
            source_size=len(payload),
            data_row_count=data_row_count,
        )

    def cache(
        self,
        snapshot: VerifiedOCDMasterSnapshot,
        *,
        retrieved_at: datetime | None = None,
    ) -> OCDMasterSnapshotMetadata:
        """Atomically cache original CSV bytes and a provenance manifest."""

        self._require_matching_snapshot(snapshot)
        cache_path, manifest_path = self._cache_paths()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = _format_utc(retrieved_at or datetime.now(timezone.utc))

        _atomic_write_bytes(cache_path, snapshot.payload)
        manifest = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "dataset": "ocd_division_ids_country_us",
            "source_repository": snapshot.spec.repository,
            "source_revision": snapshot.spec.revision,
            "source_repository_path": snapshot.spec.source_path,
            "source_url": snapshot.spec.source_url,
            "retrieved_at": timestamp,
            "source_file": cache_path.name,
            "source_sha256": snapshot.source_sha256,
            "source_git_blob_sha1": snapshot.source_git_blob_sha1,
            "source_size": snapshot.source_size,
            "data_row_count": snapshot.data_row_count,
            "headers": list(snapshot.spec.headers),
        }
        _atomic_write_text(
            manifest_path,
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )
        return self._metadata_from_snapshot(
            snapshot,
            retrieved_at=timestamp,
            cache_path=cache_path,
            manifest_path=manifest_path,
        )

    def load_cached_metadata(self) -> OCDMasterSnapshotMetadata:
        """Load and fully integrity-check a cached source and manifest."""

        cache_path, manifest_path = self._cache_paths()
        if not cache_path.is_file() or not manifest_path.is_file():
            raise OCDMasterCacheMissError(
                "No complete cached OCD master snapshot for revision "
                f"{self.release_spec.revision}"
            )

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OCDMasterSnapshotIntegrityError(
                "OCD master manifest cannot be read as UTF-8 JSON"
            ) from exc
        if not isinstance(manifest, dict):
            raise OCDMasterSnapshotIntegrityError(
                "OCD master manifest must contain a JSON object"
            )

        self._validate_manifest_contract(manifest, cache_path)
        try:
            payload = cache_path.read_bytes()
        except OSError as exc:
            raise OCDMasterSnapshotIntegrityError(
                "Cached OCD master source cannot be read"
            ) from exc

        expected_sha256 = _required_text(manifest, "source_sha256")
        if sha256(payload).hexdigest() != expected_sha256:
            raise OCDMasterSnapshotIntegrityError(
                "Checksum mismatch for cached OCD master source"
            )
        if len(payload) != _required_int(manifest, "source_size"):
            raise OCDMasterSnapshotIntegrityError(
                "Cached OCD master source size does not match manifest"
            )

        try:
            snapshot = self.verify(payload)
        except OCDMasterSourceError as exc:
            raise OCDMasterSnapshotIntegrityError(
                "Cached OCD master source no longer satisfies the pinned contract"
            ) from exc

        if snapshot.source_git_blob_sha1 != _required_text(
            manifest, "source_git_blob_sha1"
        ):
            raise OCDMasterSnapshotIntegrityError(
                "Git blob identity for cached OCD master source does not match manifest"
            )
        if snapshot.data_row_count != _required_int(manifest, "data_row_count"):
            raise OCDMasterSnapshotIntegrityError(
                "Cached OCD master row count does not match manifest"
            )

        retrieved_at = _required_utc_timestamp(manifest, "retrieved_at")
        return self._metadata_from_snapshot(
            snapshot,
            retrieved_at=retrieved_at,
            cache_path=cache_path,
            manifest_path=manifest_path,
        )

    async def refresh(
        self,
        downloader: BytesFetcher,
        *,
        force: bool = False,
        retrieved_at: datetime | None = None,
    ) -> OCDMasterSnapshotMetadata:
        """Fetch and cache a snapshot, or reuse a valid cache after HTTP 304."""

        payload = await self.fetch(downloader, force=force)
        if payload is None:
            return self.load_cached_metadata()
        return self.cache(self.verify(payload), retrieved_at=retrieved_at)

    def parse(
        self,
        snapshot: VerifiedOCDMasterSnapshot,
    ) -> OCDMasterParseResult:
        """Parse a verified snapshot into exact source membership records."""

        self._require_matching_snapshot(snapshot)
        data_row_count, records = _scan_rows(
            snapshot.payload,
            snapshot.spec,
            collect_records=True,
        )
        if data_row_count != snapshot.data_row_count:
            raise OCDMasterSourceError(
                "OCD master row count changed between verification and parsing"
            )
        return OCDMasterParseResult(
            source_repository=snapshot.spec.repository,
            source_revision=snapshot.spec.revision,
            source_url=snapshot.spec.source_url,
            source_sha256=snapshot.source_sha256,
            records=records,
        )

    def parse_cached(self) -> OCDMasterParseResult:
        """Integrity-check and parse the currently cached snapshot."""

        metadata = self.load_cached_metadata()
        snapshot = self.verify(metadata.cache_path.read_bytes())
        return self.parse(snapshot)

    @staticmethod
    def build_index(result: OCDMasterParseResult) -> OCDMasterIndex:
        """Build an immutable exact-membership index from parsed records."""

        return OCDMasterIndex(result.records)

    def _cache_paths(self) -> tuple[Path, Path]:
        filename = Path(self.release_spec.source_path).name
        cache_path = (
            self.cache_root
            / "ocd_master"
            / self.release_spec.revision
            / filename
        )
        manifest_path = cache_path.with_suffix(cache_path.suffix + ".manifest.json")
        return cache_path, manifest_path

    def _require_matching_snapshot(
        self, snapshot: VerifiedOCDMasterSnapshot
    ) -> None:
        if snapshot.spec != self.release_spec:
            raise ValueError("snapshot release spec does not match adapter")
        if sha256(snapshot.payload).hexdigest() != snapshot.source_sha256:
            raise OCDMasterSourceError("snapshot payload checksum is inconsistent")
        if _git_blob_sha1(snapshot.payload) != snapshot.source_git_blob_sha1:
            raise OCDMasterSourceError("snapshot Git blob identity is inconsistent")
        if len(snapshot.payload) != snapshot.source_size:
            raise OCDMasterSourceError("snapshot source size is inconsistent")

    def _validate_manifest_contract(
        self,
        manifest: Mapping[str, object],
        cache_path: Path,
    ) -> None:
        if _required_int(manifest, "schema_version") != MANIFEST_SCHEMA_VERSION:
            raise OCDMasterSnapshotIntegrityError(
                "Unsupported OCD master manifest schema version"
            )
        expected_text = {
            "dataset": "ocd_division_ids_country_us",
            "source_repository": self.release_spec.repository,
            "source_revision": self.release_spec.revision,
            "source_repository_path": self.release_spec.source_path,
            "source_url": self.release_spec.source_url,
            "source_file": cache_path.name,
        }
        for field, expected in expected_text.items():
            if _required_text(manifest, field) != expected:
                raise OCDMasterSnapshotIntegrityError(
                    f"OCD master manifest {field} does not match adapter"
                )

        headers = manifest.get("headers")
        if not isinstance(headers, list) or not all(
            isinstance(value, str) for value in headers
        ):
            raise OCDMasterSnapshotIntegrityError(
                "OCD master manifest headers are invalid"
            )
        if tuple(headers) != self.release_spec.headers:
            raise OCDMasterSnapshotIntegrityError(
                "OCD master manifest headers do not match adapter"
            )

    def _metadata_from_snapshot(
        self,
        snapshot: VerifiedOCDMasterSnapshot,
        *,
        retrieved_at: str,
        cache_path: Path,
        manifest_path: Path,
    ) -> OCDMasterSnapshotMetadata:
        return OCDMasterSnapshotMetadata(
            source_repository=snapshot.spec.repository,
            source_revision=snapshot.spec.revision,
            source_repository_path=snapshot.spec.source_path,
            source_url=snapshot.spec.source_url,
            retrieved_at=retrieved_at,
            source_sha256=snapshot.source_sha256,
            source_git_blob_sha1=snapshot.source_git_blob_sha1,
            source_size=snapshot.source_size,
            data_row_count=snapshot.data_row_count,
            headers=snapshot.spec.headers,
            cache_path=cache_path,
            manifest_path=manifest_path,
        )


def _scan_rows(
    payload: bytes,
    spec: OCDMasterReleaseSpec,
    *,
    collect_records: bool,
) -> tuple[int, tuple[OCDMasterSourceRecord, ...]]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise OCDMasterSourceError("OCD master source is not valid UTF-8") from exc

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader)
    except StopIteration as exc:
        raise OCDMasterSourceError("OCD master source has no CSV header") from exc
    except csv.Error as exc:
        raise OCDMasterSourceError("OCD master CSV header is malformed") from exc

    if tuple(header) != spec.headers:
        raise OCDMasterSourceError(
            "OCD master CSV headers do not match the pinned source contract"
        )

    seen_ocdids: set[str] = set()
    records: list[OCDMasterSourceRecord] = []
    data_row_count = 0
    try:
        for source_row_number, row in enumerate(reader, start=2):
            if len(row) != len(spec.headers):
                raise OCDMasterSourceError(
                    f"OCD master row {source_row_number} has {len(row)} columns; "
                    f"expected {len(spec.headers)}"
                )
            ocdid = row[0]
            name = row[1]
            if not ocdid:
                raise OCDMasterSourceError(
                    f"OCD master row {source_row_number} has an empty ID"
                )
            if ocdid != ocdid.strip():
                raise OCDMasterSourceError(
                    f"OCD master row {source_row_number} has whitespace around its ID"
                )
            if not name.strip():
                raise OCDMasterSourceError(
                    f"OCD master row {source_row_number} has an empty name"
                )
            try:
                _parse_division_ocdid(ocdid)
            except Exception as exc:
                raise OCDMasterSourceError(
                    f"OCD master row {source_row_number} has an invalid division ID: "
                    f"{ocdid}"
                ) from exc
            if ocdid in seen_ocdids:
                raise OCDMasterSourceError(
                    f"OCD master row {source_row_number} duplicates ID: {ocdid}"
                )
            seen_ocdids.add(ocdid)
            data_row_count += 1
            if collect_records:
                records.append(
                    OCDMasterSourceRecord(
                        ocdid=ocdid,
                        name=name,
                        source_row_number=source_row_number,
                    )
                )
    except csv.Error as exc:
        raise OCDMasterSourceError(
            f"OCD master CSV is malformed near line {reader.line_num}"
        ) from exc

    if data_row_count == 0:
        raise OCDMasterSourceError("OCD master source has no data rows")
    return data_row_count, tuple(records)


def _parse_division_ocdid(ocdid: str) -> OCDIdParsed:
    if not isinstance(ocdid, str) or not ocdid:
        raise ValueError("OCD ID must be a non-empty string")
    if ocdid != ocdid.strip():
        raise ValueError("OCD ID must not contain surrounding whitespace")
    parsed = OCDIdParsed.parse_ocdid(ocdid)
    if parsed.type != "ocd-division":
        raise ValueError("OCD master membership accepts division IDs only")
    return parsed


def _suggestion_scope(parsed: OCDIdParsed) -> tuple[str, str, str]:
    parts = parsed.get_ocdid_parts()
    if len(parts) < 2:
        raise ValueError("OCD ID does not contain a suggestion scope")
    leaf = parts[-1]
    segment_type, separator, _ = leaf.partition(":")
    if not separator or not segment_type:
        raise ValueError("OCD ID leaf segment is invalid")
    return "/".join(parts[:-1]), segment_type, leaf


def _git_blob_sha1(payload: bytes) -> str:
    digest = sha1(usedforsecurity=False)
    digest.update(f"blob {len(payload)}\0".encode("ascii"))
    digest.update(payload)
    return digest.hexdigest()


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("retrieved_at must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _required_utc_timestamp(
    manifest: Mapping[str, object], field: str
) -> str:
    value = _required_text(manifest, field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OCDMasterSnapshotIntegrityError(
            f"OCD master manifest {field} is not an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OCDMasterSnapshotIntegrityError(
            f"OCD master manifest {field} must be timezone-aware"
        )
    if parsed.utcoffset().total_seconds() != 0:
        raise OCDMasterSnapshotIntegrityError(
            f"OCD master manifest {field} must be UTC"
        )
    return value


def _required_text(manifest: Mapping[str, object], field: str) -> str:
    value = manifest.get(field)
    if not isinstance(value, str) or not value:
        raise OCDMasterSnapshotIntegrityError(
            f"OCD master manifest {field} must be non-empty text"
        )
    return value


def _required_int(manifest: Mapping[str, object], field: str) -> int:
    value = manifest.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise OCDMasterSnapshotIntegrityError(
            f"OCD master manifest {field} must be a non-negative integer"
        )
    return value


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
