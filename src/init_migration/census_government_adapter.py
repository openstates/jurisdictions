"""Offline-first Census Government Units source snapshot adapter.

The adapter keeps source acquisition separate from downstream normalization:

``fetch`` -> ``verify`` -> ``cache`` -> ``parse``

The source is the Census Bureau's annual Government Units ZIP archive. The
original archive is cached unchanged, while workbook rows are exposed as raw
source records with explicit provenance and structured parsing errors.
"""

from __future__ import annotations

import io
import json
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from logging import getLogger
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Iterator, Mapping, Protocol
from xml.etree import ElementTree

logger = getLogger(__name__)

CENSUS_GOVERNMENT_BASE_URL = (
    "https://www2.census.gov/programs-surveys/gus/datasets"
)
MANIFEST_SCHEMA_VERSION = 1
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_WORKBOOK_UNCOMPRESSED_BYTES = 128 * 1024 * 1024

_SPREADSHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_OFFICE_REL_NS = (
    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
)
_PACKAGE_REL_NS = (
    "{http://schemas.openxmlformats.org/package/2006/relationships}"
)
_CELL_REF_RE = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")


class CensusGovernmentAdapterError(Exception):
    """Base error for Census Government Units snapshot operations."""


class CensusGovernmentSourceError(CensusGovernmentAdapterError):
    """Raised when the source archive or workbook contract is invalid."""


class CensusGovernmentCacheMissError(CensusGovernmentAdapterError):
    """Raised when a conditional request has no valid cached archive."""


class CensusGovernmentSnapshotIntegrityError(CensusGovernmentAdapterError):
    """Raised when cached bytes do not match their manifest."""


class BytesFetcher(Protocol):
    """Minimal network interface implemented by ``AsyncDownloader``."""

    async def fetch_bytes(
        self, url: str, *, force: bool = False
    ) -> bytes | None: ...


class CensusGovernmentSheet(StrEnum):
    """Source workbook tabs in the 2025 Government Units release."""

    GENERAL_PURPOSE = "General Purpose"
    SPECIAL_DISTRICT = "Special District"
    SCHOOL_DISTRICT = "School District"
    DEPENDENT_SCHOOL_DISTRICT = "DEP School Dist"
    PUBLIC_PENSION_SYSTEM = "Public Pension Sys"


@dataclass(frozen=True)
class CensusGovernmentSheetSpec:
    """Pinned workbook contract for one source tab."""

    sheet: CensusGovernmentSheet
    headers: tuple[str, ...]
    expected_data_rows: int
    allowed_unit_types: frozenset[str]


@dataclass(frozen=True)
class CensusGovernmentReleaseSpec:
    """Pinned source contract for one annual Government Units release."""

    release_year: str
    source_snapshot_date: str
    source_url: str
    archive_filename: str
    workbook_member: str
    documentation_member: str
    sheets: tuple[CensusGovernmentSheetSpec, ...]

    @property
    def sheet_specs(self) -> Mapping[CensusGovernmentSheet, CensusGovernmentSheetSpec]:
        return MappingProxyType({spec.sheet: spec for spec in self.sheets})


_GENERAL_HEADERS = (
    "CENSUS_ID_PID6",
    "UNIT_NAME",
    "UNIT_TYPE",
    "TITLE",
    "ADDRESS1",
    "ADDRESS2",
    "CITY",
    "STATE",
    "ZIP",
    "ZIP4",
    "WEB_ADDRESS",
    "POLITICAL_CODE_DESCRIPTION",
    "POPULATION",
    "POPULATION_SOURCE_YEAR",
    "FIPS_STATE",
    "FIPS_COUNTY",
    "FIPS_PLACE",
    "COUNTY_AREA_NAME",
    "ACTIVE",
)
_SPECIAL_HEADERS = (
    "CENSUS_ID_PID6",
    "UNIT_NAME",
    "UNIT_TYPE",
    "FUNCTION_NAME",
    "TITLE",
    "ADDRESS1",
    "ADDRESS2",
    "CITY",
    "STATE",
    "ZIP",
    "ZIP4",
    "WEB_ADDRESS",
    "FIPS_STATE",
    "FIPS_COUNTY",
    "COUNTY_AREA_NAME",
    "ACTIVE",
)
_SCHOOL_HEADERS = (
    "CENSUS_ID_PID6",
    "UNIT_NAME",
    "UNIT_TYPE",
    "TITLE",
    "ADDRESS1",
    "ADDRESS2",
    "CITY",
    "STATE",
    "ZIP",
    "ZIP4",
    "WEB_ADDRESS",
    "SCHOOL_ENROLLMENT",
    "ENROLLMENT_YEAR",
    "SCHOOL_LEVEL_DESCRIPTION",
    "FIPS_STATE",
    "FIPS_COUNTY",
    "COUNTY_AREA_NAME",
    "ACTIVE",
)
_DEPENDENT_SCHOOL_HEADERS = _SCHOOL_HEADERS + (
    "PARENT_CENSUS_ID_PID6",
    "PARENT_UNIT_NAME",
)
_PENSION_HEADERS = (
    "CENSUS_ID_PID6",
    "UNIT_NAME",
    "UNIT_TYPE",
    "ACTIVITY_NAME",
    "TITLE",
    "ADDRESS1",
    "ADDRESS2",
    "CITY",
    "STATE",
    "ZIP",
    "ZIP4",
    "WEB_ADDRESS",
    "FIPS_STATE",
    "FIPS_COUNTY",
    "COUNTY_AREA_NAME",
    "ACTIVE",
    "PARENT_CENSUS_ID_PID6",
    "PARENT_UNIT_NAME",
)

_GENERAL_TYPES = frozenset(
    {"1 - COUNTY", "2 - MUNICIPAL", "3 - TOWNSHIP"}
)
_SPECIAL_TYPES = frozenset({"4 - SPECIAL DISTRICT"})
_SCHOOL_TYPES = frozenset(
    {"5 - SCHOOL DISTRICT OR EDUCATIONAL SERVICE AGENCY"}
)
_DEPENDENT_SCHOOL_TYPES = frozenset(
    {"0 - STATE", "1 - COUNTY", "2 - MUNICIPAL", "3 - TOWNSHIP"}
)
_PENSION_TYPES = frozenset(
    {
        "0 - STATE",
        "1 - COUNTY",
        "2 - MUNICIPAL",
        "3 - TOWNSHIP",
        "4 - SPECIAL DISTRICT",
        "5 - SCHOOL DISTRICT OR EDUCATIONAL SERVICE AGENCY",
    }
)

CENSUS_GOVERNMENT_RELEASES: Mapping[str, CensusGovernmentReleaseSpec] = {
    "2025": CensusGovernmentReleaseSpec(
        release_year="2025",
        source_snapshot_date="2025-08-28",
        source_url=(
            f"{CENSUS_GOVERNMENT_BASE_URL}/2025/gov_units_2025.zip"
        ),
        archive_filename="gov_units_2025.zip",
        workbook_member="Govt_Units_2025_Final.xlsx",
        documentation_member="Government_Units_List_Documentation_2025.pdf",
        sheets=(
            CensusGovernmentSheetSpec(
                sheet=CensusGovernmentSheet.GENERAL_PURPOSE,
                headers=_GENERAL_HEADERS,
                expected_data_rows=38_704,
                allowed_unit_types=_GENERAL_TYPES,
            ),
            CensusGovernmentSheetSpec(
                sheet=CensusGovernmentSheet.SPECIAL_DISTRICT,
                headers=_SPECIAL_HEADERS,
                expected_data_rows=40_199,
                allowed_unit_types=_SPECIAL_TYPES,
            ),
            CensusGovernmentSheetSpec(
                sheet=CensusGovernmentSheet.SCHOOL_DISTRICT,
                headers=_SCHOOL_HEADERS,
                expected_data_rows=12_535,
                allowed_unit_types=_SCHOOL_TYPES,
            ),
            CensusGovernmentSheetSpec(
                sheet=CensusGovernmentSheet.DEPENDENT_SCHOOL_DISTRICT,
                headers=_DEPENDENT_SCHOOL_HEADERS,
                expected_data_rows=1_318,
                allowed_unit_types=_DEPENDENT_SCHOOL_TYPES,
            ),
            CensusGovernmentSheetSpec(
                sheet=CensusGovernmentSheet.PUBLIC_PENSION_SYSTEM,
                headers=_PENSION_HEADERS,
                expected_data_rows=4_485,
                allowed_unit_types=_PENSION_TYPES,
            ),
        ),
    )
}


@dataclass(frozen=True)
class CensusGovernmentWorkbookInventory:
    """Verified worksheet row counts for one source workbook."""

    sheet_data_rows: Mapping[CensusGovernmentSheet, int]

    @property
    def total_data_rows(self) -> int:
        return sum(self.sheet_data_rows.values())


@dataclass(frozen=True)
class VerifiedCensusGovernmentArchive:
    """Verified source archive ready to cache."""

    spec: CensusGovernmentReleaseSpec
    source_url: str
    payload: bytes
    archive_sha256: str
    workbook_sha256: str
    documentation_sha256: str
    inventory: CensusGovernmentWorkbookInventory


@dataclass(frozen=True)
class CensusGovernmentSnapshotMetadata:
    """Sidecar metadata for one cached Government Units archive."""

    release_year: str
    source_snapshot_date: str
    source_url: str
    retrieved_at: str
    archive_sha256: str
    archive_size: int
    workbook_member: str
    workbook_sha256: str
    documentation_member: str
    documentation_sha256: str
    sheet_data_rows: Mapping[CensusGovernmentSheet, int]
    archive_path: Path
    manifest_path: Path


@dataclass(frozen=True)
class CensusGovernmentSourceRecord:
    """One raw source row with stable source provenance."""

    release_year: str
    source_snapshot_date: str
    source_archive_url: str
    source_archive_sha256: str
    source_member_filename: str
    source_sheet: CensusGovernmentSheet
    source_row_number: int
    census_id_pid6: str
    parent_census_id_pid6: str | None
    unit_name: str
    unit_type: str
    active: str
    raw_fields: Mapping[str, str | None]


@dataclass(frozen=True)
class CensusGovernmentParseError:
    """One source row that could not be emitted as a valid raw record."""

    release_year: str
    source_sheet: CensusGovernmentSheet
    source_row_number: int
    census_id_pid6: str | None
    message: str
    raw_fields: Mapping[str, str | None]


@dataclass(frozen=True)
class CensusGovernmentParseResult:
    """Parsed records plus explicit row errors; no input row disappears."""

    metadata: CensusGovernmentSnapshotMetadata
    records: tuple[CensusGovernmentSourceRecord, ...]
    errors: tuple[CensusGovernmentParseError, ...]

    @property
    def input_count(self) -> int:
        return len(self.records) + len(self.errors)


class CensusGovernmentAdapter:
    """Fetch, verify, cache, and parse a pinned Government Units release."""

    def __init__(
        self,
        cache_root: str | os.PathLike[str],
        *,
        release_year: str = "2025",
        release_spec: CensusGovernmentReleaseSpec | None = None,
        max_archive_bytes: int = MAX_ARCHIVE_BYTES,
    ) -> None:
        if release_spec is None:
            try:
                release_spec = CENSUS_GOVERNMENT_RELEASES[release_year]
            except KeyError as exc:
                supported = ", ".join(sorted(CENSUS_GOVERNMENT_RELEASES))
                raise ValueError(
                    f"Unsupported Government Units release {release_year!r}; "
                    f"supported: {supported}"
                ) from exc
        elif release_spec.release_year != release_year:
            raise ValueError("release_spec year must match release_year")
        if max_archive_bytes < 1:
            raise ValueError("max_archive_bytes must be positive")

        self.cache_root = Path(cache_root)
        self.release_spec = release_spec
        self.max_archive_bytes = max_archive_bytes

    async def fetch(
        self,
        downloader: BytesFetcher,
        *,
        force: bool = False,
    ) -> bytes | None:
        """Fetch the annual source archive; ``None`` means not modified."""

        return await downloader.fetch_bytes(
            self.release_spec.source_url,
            force=force,
        )

    def verify(self, payload: bytes) -> VerifiedCensusGovernmentArchive:
        """Verify archive membership, workbook schema, and release row counts."""

        if not payload:
            raise CensusGovernmentSourceError(
                "Census Government Units archive is empty"
            )
        if len(payload) > self.max_archive_bytes:
            raise CensusGovernmentSourceError(
                "Census Government Units archive exceeds the configured size "
                "limit"
            )

        members = _read_outer_archive(payload, self.release_spec)
        workbook_payload = members[self.release_spec.workbook_member]
        documentation_payload = members[self.release_spec.documentation_member]
        if not documentation_payload.startswith(b"%PDF-"):
            raise CensusGovernmentSourceError(
                "Government Units documentation member is not a PDF"
            )

        inventory = _inspect_workbook(workbook_payload, self.release_spec)
        return VerifiedCensusGovernmentArchive(
            spec=self.release_spec,
            source_url=self.release_spec.source_url,
            payload=payload,
            archive_sha256=sha256(payload).hexdigest(),
            workbook_sha256=sha256(workbook_payload).hexdigest(),
            documentation_sha256=sha256(documentation_payload).hexdigest(),
            inventory=inventory,
        )

    def cache(
        self,
        snapshot: VerifiedCensusGovernmentArchive,
        *,
        retrieved_at: datetime | None = None,
    ) -> CensusGovernmentSnapshotMetadata:
        """Atomically cache the original ZIP plus a provenance manifest."""

        archive_path, manifest_path = self._cache_paths()
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = _format_utc(retrieved_at or datetime.now(timezone.utc))
        _atomic_write_bytes(archive_path, snapshot.payload)

        sheet_rows = {
            sheet.value: count
            for sheet, count in snapshot.inventory.sheet_data_rows.items()
        }
        manifest = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "dataset": "census_governments_master_address_file",
            "release_year": snapshot.spec.release_year,
            "source_snapshot_date": snapshot.spec.source_snapshot_date,
            "source_url": snapshot.source_url,
            "retrieved_at": timestamp,
            "archive_file": archive_path.name,
            "archive_sha256": snapshot.archive_sha256,
            "archive_size": len(snapshot.payload),
            "workbook_member": snapshot.spec.workbook_member,
            "workbook_sha256": snapshot.workbook_sha256,
            "documentation_member": snapshot.spec.documentation_member,
            "documentation_sha256": snapshot.documentation_sha256,
            "sheet_data_rows": sheet_rows,
        }
        _atomic_write_text(
            manifest_path,
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )

        metadata = CensusGovernmentSnapshotMetadata(
            release_year=snapshot.spec.release_year,
            source_snapshot_date=snapshot.spec.source_snapshot_date,
            source_url=snapshot.source_url,
            retrieved_at=timestamp,
            archive_sha256=snapshot.archive_sha256,
            archive_size=len(snapshot.payload),
            workbook_member=snapshot.spec.workbook_member,
            workbook_sha256=snapshot.workbook_sha256,
            documentation_member=snapshot.spec.documentation_member,
            documentation_sha256=snapshot.documentation_sha256,
            sheet_data_rows=MappingProxyType(
                dict(snapshot.inventory.sheet_data_rows)
            ),
            archive_path=archive_path,
            manifest_path=manifest_path,
        )
        logger.info(
            "Cached Census Government Units source archive",
            extra={
                "release_year": metadata.release_year,
                "archive_sha256": metadata.archive_sha256,
                "record_count": sum(metadata.sheet_data_rows.values()),
            },
        )
        return metadata

    def load_cached_metadata(self) -> CensusGovernmentSnapshotMetadata:
        """Load and integrity-check a cached archive and manifest."""

        archive_path, manifest_path = self._cache_paths()
        if not archive_path.is_file() or not manifest_path.is_file():
            raise CensusGovernmentCacheMissError(
                "No cached Census Government Units archive for release "
                f"{self.release_spec.release_year}"
            )

        manifest = _load_json_object(
            manifest_path.read_bytes(),
            source_name=str(manifest_path),
            error_type=CensusGovernmentSnapshotIntegrityError,
        )
        if _required_manifest_int(manifest, "schema_version") != (
            MANIFEST_SCHEMA_VERSION
        ):
            raise CensusGovernmentSnapshotIntegrityError(
                "Unsupported Government Units manifest schema version"
            )
        if manifest.get("dataset") != (
            "census_governments_master_address_file"
        ):
            raise CensusGovernmentSnapshotIntegrityError(
                "Government Units manifest dataset is invalid"
            )
        if manifest.get("release_year") != self.release_spec.release_year:
            raise CensusGovernmentSnapshotIntegrityError(
                "Government Units manifest release year does not match adapter"
            )
        if manifest.get("source_snapshot_date") != (
            self.release_spec.source_snapshot_date
        ):
            raise CensusGovernmentSnapshotIntegrityError(
                "Government Units manifest source snapshot date does not match "
                "adapter"
            )
        if manifest.get("source_url") != self.release_spec.source_url:
            raise CensusGovernmentSnapshotIntegrityError(
                "Government Units manifest source URL does not match adapter"
            )
        if manifest.get("archive_file") != archive_path.name:
            raise CensusGovernmentSnapshotIntegrityError(
                "Government Units manifest archive filename is invalid"
            )

        payload = archive_path.read_bytes()
        expected_archive_sha = _required_manifest_text(
            manifest,
            "archive_sha256",
        )
        if sha256(payload).hexdigest() != expected_archive_sha:
            raise CensusGovernmentSnapshotIntegrityError(
                "Checksum mismatch for cached Government Units archive"
            )
        if len(payload) != _required_manifest_int(manifest, "archive_size"):
            raise CensusGovernmentSnapshotIntegrityError(
                "Cached Government Units archive size does not match manifest"
            )

        try:
            verified = self.verify(payload)
        except CensusGovernmentSourceError as exc:
            raise CensusGovernmentSnapshotIntegrityError(
                "Cached Government Units archive no longer satisfies the "
                "pinned release contract"
            ) from exc
        if manifest.get("workbook_member") != self.release_spec.workbook_member:
            raise CensusGovernmentSnapshotIntegrityError(
                "Government Units manifest workbook member is invalid"
            )
        if manifest.get("documentation_member") != (
            self.release_spec.documentation_member
        ):
            raise CensusGovernmentSnapshotIntegrityError(
                "Government Units manifest documentation member is invalid"
            )
        if manifest.get("workbook_sha256") != verified.workbook_sha256:
            raise CensusGovernmentSnapshotIntegrityError(
                "Government Units workbook checksum does not match manifest"
            )
        if manifest.get("documentation_sha256") != (
            verified.documentation_sha256
        ):
            raise CensusGovernmentSnapshotIntegrityError(
                "Government Units documentation checksum does not match manifest"
            )

        manifest_rows = manifest.get("sheet_data_rows")
        if not isinstance(manifest_rows, Mapping):
            raise CensusGovernmentSnapshotIntegrityError(
                "Government Units manifest sheet row counts are invalid"
            )
        expected_rows = {
            sheet.value: count
            for sheet, count in verified.inventory.sheet_data_rows.items()
        }
        if dict(manifest_rows) != expected_rows:
            raise CensusGovernmentSnapshotIntegrityError(
                "Government Units sheet row counts do not match manifest"
            )

        return CensusGovernmentSnapshotMetadata(
            release_year=self.release_spec.release_year,
            source_snapshot_date=self.release_spec.source_snapshot_date,
            source_url=self.release_spec.source_url,
            retrieved_at=_required_utc_timestamp(manifest, "retrieved_at"),
            archive_sha256=expected_archive_sha,
            archive_size=len(payload),
            workbook_member=self.release_spec.workbook_member,
            workbook_sha256=verified.workbook_sha256,
            documentation_member=self.release_spec.documentation_member,
            documentation_sha256=verified.documentation_sha256,
            sheet_data_rows=MappingProxyType(
                dict(verified.inventory.sheet_data_rows)
            ),
            archive_path=archive_path,
            manifest_path=manifest_path,
        )

    async def refresh(
        self,
        downloader: BytesFetcher,
        *,
        force: bool = False,
        retrieved_at: datetime | None = None,
    ) -> CensusGovernmentSnapshotMetadata:
        """Fetch and cache a release, or reuse a valid cache after HTTP 304."""

        payload = await self.fetch(downloader, force=force)
        if payload is None:
            return self.load_cached_metadata()
        verified = self.verify(payload)
        return self.cache(verified, retrieved_at=retrieved_at)

    def iter_parse(
        self,
    ) -> Iterator[CensusGovernmentSourceRecord | CensusGovernmentParseError]:
        """Stream cached rows as raw records or structured row errors."""

        metadata = self.load_cached_metadata()
        yield from self._iter_parse_with_metadata(metadata)

    def parse(self) -> CensusGovernmentParseResult:
        """Materialize all streamed outcomes for tests and bounded workflows."""

        metadata = self.load_cached_metadata()
        records: list[CensusGovernmentSourceRecord] = []
        errors: list[CensusGovernmentParseError] = []
        for outcome in self._iter_parse_with_metadata(metadata):
            if isinstance(outcome, CensusGovernmentSourceRecord):
                records.append(outcome)
            else:
                errors.append(outcome)

        result = CensusGovernmentParseResult(
            metadata=metadata,
            records=tuple(records),
            errors=tuple(errors),
        )
        expected_input_count = sum(metadata.sheet_data_rows.values())
        if result.input_count != expected_input_count:
            raise CensusGovernmentSourceError(
                "Government Units parser did not account for every source row"
            )
        return result

    def _iter_parse_with_metadata(
        self,
        metadata: CensusGovernmentSnapshotMetadata,
    ) -> Iterator[CensusGovernmentSourceRecord | CensusGovernmentParseError]:
        archive_payload = metadata.archive_path.read_bytes()
        members = _read_outer_archive(archive_payload, self.release_spec)
        workbook_payload = members[self.release_spec.workbook_member]
        seen_ids: set[str] = set()

        for sheet_spec, row_number, raw_fields in _iter_workbook_rows(
            workbook_payload,
            self.release_spec,
        ):
            census_id = _optional_text(raw_fields, "CENSUS_ID_PID6")
            try:
                record = _parse_source_record(
                    metadata,
                    sheet_spec,
                    row_number,
                    raw_fields,
                )
                if record.census_id_pid6 in seen_ids:
                    raise ValueError(
                        "duplicate CENSUS_ID_PID6 "
                        f"{record.census_id_pid6!r} in workbook"
                    )
                seen_ids.add(record.census_id_pid6)
                yield record
            except (TypeError, ValueError) as exc:
                yield CensusGovernmentParseError(
                    release_year=metadata.release_year,
                    source_sheet=sheet_spec.sheet,
                    source_row_number=row_number,
                    census_id_pid6=census_id,
                    message=str(exc),
                    raw_fields=MappingProxyType(dict(raw_fields)),
                )

    def _cache_paths(self) -> tuple[Path, Path]:
        directory = self.cache_root / self.release_spec.release_year
        archive_path = directory / self.release_spec.archive_filename
        manifest_path = directory / (
            f"{self.release_spec.archive_filename}.manifest.json"
        )
        return archive_path, manifest_path


def _read_outer_archive(
    payload: bytes,
    spec: CensusGovernmentReleaseSpec,
) -> dict[str, bytes]:
    with _open_zip(payload, source_name=spec.archive_filename) as archive:
        infos = _validate_zip_members(
            archive,
            max_uncompressed_bytes=MAX_ARCHIVE_UNCOMPRESSED_BYTES,
            source_name=spec.archive_filename,
        )
        actual_members = {info.filename for info in infos}
        expected_members = {spec.workbook_member, spec.documentation_member}
        if actual_members != expected_members:
            missing = sorted(expected_members - actual_members)
            unexpected = sorted(actual_members - expected_members)
            raise CensusGovernmentSourceError(
                "Government Units archive members do not match the pinned "
                f"release; missing={missing}, unexpected={unexpected}"
            )
        bad_member = archive.testzip()
        if bad_member is not None:
            raise CensusGovernmentSourceError(
                f"Government Units archive CRC failed for {bad_member!r}"
            )
        return {name: archive.read(name) for name in sorted(expected_members)}


def _inspect_workbook(
    payload: bytes,
    spec: CensusGovernmentReleaseSpec,
) -> CensusGovernmentWorkbookInventory:
    with _open_zip(payload, source_name=spec.workbook_member) as workbook:
        _validate_zip_members(
            workbook,
            max_uncompressed_bytes=MAX_WORKBOOK_UNCOMPRESSED_BYTES,
            source_name=spec.workbook_member,
        )
        bad_member = workbook.testzip()
        if bad_member is not None:
            raise CensusGovernmentSourceError(
                f"Government Units workbook CRC failed for {bad_member!r}"
            )
        sheet_paths = _workbook_sheet_paths(workbook, spec)
        shared_strings = _load_shared_strings(workbook)
        sheet_rows: dict[CensusGovernmentSheet, int] = {}
        for sheet_spec in spec.sheets:
            data_rows = _inspect_sheet(
                workbook,
                sheet_paths[sheet_spec.sheet],
                sheet_spec,
                shared_strings,
            )
            sheet_rows[sheet_spec.sheet] = data_rows
        return CensusGovernmentWorkbookInventory(
            sheet_data_rows=MappingProxyType(sheet_rows)
        )


def _iter_workbook_rows(
    payload: bytes,
    spec: CensusGovernmentReleaseSpec,
) -> Iterator[
    tuple[CensusGovernmentSheetSpec, int, Mapping[str, str | None]]
]:
    with _open_zip(payload, source_name=spec.workbook_member) as workbook:
        sheet_paths = _workbook_sheet_paths(workbook, spec)
        shared_strings = _load_shared_strings(workbook)
        for sheet_spec in spec.sheets:
            path = sheet_paths[sheet_spec.sheet]
            yield from _iter_sheet_rows(
                workbook,
                path,
                sheet_spec,
                shared_strings,
            )


def _workbook_sheet_paths(
    workbook: zipfile.ZipFile,
    spec: CensusGovernmentReleaseSpec,
) -> Mapping[CensusGovernmentSheet, str]:
    required = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
    names = {info.filename for info in workbook.infolist() if not info.is_dir()}
    if not required.issubset(names):
        missing = sorted(required - names)
        raise CensusGovernmentSourceError(
            f"Government Units workbook is missing required members: {missing}"
        )

    workbook_root = _parse_xml(
        workbook.read("xl/workbook.xml"),
        source_name="xl/workbook.xml",
    )
    relationships_root = _parse_xml(
        workbook.read("xl/_rels/workbook.xml.rels"),
        source_name="xl/_rels/workbook.xml.rels",
    )
    relationship_targets = {
        relationship.attrib["Id"]: relationship.attrib["Target"]
        for relationship in relationships_root.findall(
            f"{_PACKAGE_REL_NS}Relationship"
        )
        if relationship.attrib.get("Id") and relationship.attrib.get("Target")
    }

    sheets_node = workbook_root.find(f"{_SPREADSHEET_NS}sheets")
    if sheets_node is None:
        raise CensusGovernmentSourceError(
            "Government Units workbook contains no sheets node"
        )
    actual_sheet_names: list[str] = []
    sheet_paths: dict[CensusGovernmentSheet, str] = {}
    expected_by_name = {sheet.sheet.value: sheet.sheet for sheet in spec.sheets}
    for sheet_node in sheets_node.findall(f"{_SPREADSHEET_NS}sheet"):
        name = sheet_node.attrib.get("name")
        relationship_id = sheet_node.attrib.get(f"{_OFFICE_REL_NS}id")
        if not name or not relationship_id:
            raise CensusGovernmentSourceError(
                "Government Units workbook has an invalid sheet declaration"
            )
        actual_sheet_names.append(name)
        try:
            sheet_enum = expected_by_name[name]
            target = relationship_targets[relationship_id]
        except KeyError as exc:
            raise CensusGovernmentSourceError(
                f"Unexpected Government Units workbook sheet {name!r}"
            ) from exc
        normalized_target = _normalize_workbook_target(target)
        if normalized_target not in names:
            raise CensusGovernmentSourceError(
                f"Worksheet member {normalized_target!r} is missing"
            )
        sheet_paths[sheet_enum] = normalized_target

    expected_sheet_names = [sheet.sheet.value for sheet in spec.sheets]
    if actual_sheet_names != expected_sheet_names:
        raise CensusGovernmentSourceError(
            "Government Units workbook sheet order/names do not match the "
            f"pinned release: {actual_sheet_names!r}"
        )
    return MappingProxyType(sheet_paths)


def _inspect_sheet(
    workbook: zipfile.ZipFile,
    path: str,
    sheet_spec: CensusGovernmentSheetSpec,
    shared_strings: tuple[str, ...],
) -> int:
    dimension_ref: str | None = None
    row_count = 0
    previous_row_number = 0
    header_values: tuple[str | None, ...] | None = None

    with workbook.open(path) as stream:
        for event, element in ElementTree.iterparse(
            stream,
            events=("start", "end"),
        ):
            if event == "start" and element.tag == (
                f"{_SPREADSHEET_NS}dimension"
            ):
                dimension_ref = element.attrib.get("ref")
            if event != "end" or element.tag != f"{_SPREADSHEET_NS}row":
                continue

            row_count += 1
            row_number = _required_row_number(element)
            if row_number != previous_row_number + 1:
                raise CensusGovernmentSourceError(
                    f"Worksheet {sheet_spec.sheet.value!r} has a row gap at "
                    f"row {row_number}"
                )
            previous_row_number = row_number
            values = _row_values(
                element,
                shared_strings,
                max_columns=len(sheet_spec.headers),
                expected_row_number=row_number,
            )
            if row_number == 1:
                header_values = tuple(values.get(i) for i in range(
                    len(sheet_spec.headers)
                ))
            element.clear()

    expected_total_rows = sheet_spec.expected_data_rows + 1
    expected_dimension = (
        f"A1:{_excel_column_name(len(sheet_spec.headers))}"
        f"{expected_total_rows}"
    )
    if dimension_ref != expected_dimension:
        raise CensusGovernmentSourceError(
            f"Worksheet {sheet_spec.sheet.value!r} dimension "
            f"{dimension_ref!r} does not match {expected_dimension!r}"
        )
    if row_count != expected_total_rows:
        raise CensusGovernmentSourceError(
            f"Worksheet {sheet_spec.sheet.value!r} has {row_count - 1} data "
            f"rows; expected {sheet_spec.expected_data_rows}"
        )
    if header_values != sheet_spec.headers:
        raise CensusGovernmentSourceError(
            f"Worksheet {sheet_spec.sheet.value!r} headers do not match the "
            "pinned release"
        )
    return row_count - 1


def _iter_sheet_rows(
    workbook: zipfile.ZipFile,
    path: str,
    sheet_spec: CensusGovernmentSheetSpec,
    shared_strings: tuple[str, ...],
) -> Iterator[tuple[CensusGovernmentSheetSpec, int, Mapping[str, str | None]]]:
    with workbook.open(path) as stream:
        for event, element in ElementTree.iterparse(stream, events=("end",)):
            if element.tag != f"{_SPREADSHEET_NS}row":
                continue
            row_number = _required_row_number(element)
            if row_number == 1:
                element.clear()
                continue
            values = _row_values(
                element,
                shared_strings,
                max_columns=len(sheet_spec.headers),
                expected_row_number=row_number,
            )
            raw_fields = {
                header: values.get(index)
                for index, header in enumerate(sheet_spec.headers)
            }
            yield sheet_spec, row_number, MappingProxyType(raw_fields)
            element.clear()


def _row_values(
    row_element: ElementTree.Element,
    shared_strings: tuple[str, ...],
    *,
    max_columns: int,
    expected_row_number: int,
) -> dict[int, str | None]:
    values: dict[int, str | None] = {}
    for cell in row_element.findall(f"{_SPREADSHEET_NS}c"):
        if cell.find(f"{_SPREADSHEET_NS}f") is not None:
            raise CensusGovernmentSourceError(
                "Government Units workbook must contain values, not formulas"
            )
        reference = cell.attrib.get("r")
        if reference is None:
            raise CensusGovernmentSourceError(
                "Government Units workbook cell is missing its reference"
            )
        column_index, cell_row_number = _parse_cell_reference(reference)
        if cell_row_number != expected_row_number:
            raise CensusGovernmentSourceError(
                f"Government Units workbook cell {reference!r} is outside "
                f"row {expected_row_number}"
            )
        if column_index in values:
            raise CensusGovernmentSourceError(
                f"Government Units workbook row {expected_row_number} "
                f"contains duplicate cell {reference!r}"
            )
        if column_index >= max_columns:
            raise CensusGovernmentSourceError(
                f"Government Units workbook contains unexpected column "
                f"{reference!r}"
            )
        values[column_index] = _cell_value(cell, shared_strings)
    return values


def _cell_value(
    cell: ElementTree.Element,
    shared_strings: tuple[str, ...],
) -> str | None:
    cell_type = cell.attrib.get("t")
    value_node = cell.find(f"{_SPREADSHEET_NS}v")
    if cell_type == "s":
        if value_node is None or value_node.text is None:
            return None
        try:
            return shared_strings[int(value_node.text)]
        except (ValueError, IndexError) as exc:
            raise CensusGovernmentSourceError(
                "Government Units workbook has an invalid shared-string index"
            ) from exc
    if cell_type == "inlineStr":
        inline = cell.find(f"{_SPREADSHEET_NS}is")
        if inline is None:
            return None
        return "".join(
            text.text or ""
            for text in inline.iter(f"{_SPREADSHEET_NS}t")
        )
    if cell_type == "e":
        raise CensusGovernmentSourceError(
            "Government Units workbook contains an Excel error cell"
        )
    if value_node is None:
        return None
    return value_node.text


def _load_shared_strings(workbook: zipfile.ZipFile) -> tuple[str, ...]:
    name = "xl/sharedStrings.xml"
    if name not in {info.filename for info in workbook.infolist()}:
        return ()
    strings: list[str] = []
    with workbook.open(name) as stream:
        for event, element in ElementTree.iterparse(stream, events=("end",)):
            if element.tag != f"{_SPREADSHEET_NS}si":
                continue
            strings.append(
                "".join(
                    text.text or ""
                    for text in element.iter(f"{_SPREADSHEET_NS}t")
                )
            )
            element.clear()
    return tuple(strings)


def _parse_source_record(
    metadata: CensusGovernmentSnapshotMetadata,
    sheet_spec: CensusGovernmentSheetSpec,
    row_number: int,
    raw_fields: Mapping[str, str | None],
) -> CensusGovernmentSourceRecord:
    census_id = _required_digits(raw_fields, "CENSUS_ID_PID6", 6)
    unit_name = _required_text(raw_fields, "UNIT_NAME")
    unit_type = _required_text(raw_fields, "UNIT_TYPE")
    if unit_type not in sheet_spec.allowed_unit_types:
        raise ValueError(
            f"UNIT_TYPE {unit_type!r} is invalid for "
            f"{sheet_spec.sheet.value!r}"
        )
    active = _required_text(raw_fields, "ACTIVE")
    if active not in {"Y", "N"}:
        raise ValueError("ACTIVE must be 'Y' or 'N'")

    # This is a source adapter, not the Phase 5 normalizer. Address, website,
    # population, enrollment, and geography fields are preserved exactly as
    # published—even when blank or imperfect. Only the row identity and the
    # source sheet's categorical contract are required here.
    parent_id: str | None = None
    if "PARENT_CENSUS_ID_PID6" in sheet_spec.headers:
        parent_id = _required_digits(
            raw_fields,
            "PARENT_CENSUS_ID_PID6",
            6,
        )
        _required_text(raw_fields, "PARENT_UNIT_NAME")

    return CensusGovernmentSourceRecord(
        release_year=metadata.release_year,
        source_snapshot_date=metadata.source_snapshot_date,
        source_archive_url=metadata.source_url,
        source_archive_sha256=metadata.archive_sha256,
        source_member_filename=metadata.workbook_member,
        source_sheet=sheet_spec.sheet,
        source_row_number=row_number,
        census_id_pid6=census_id,
        parent_census_id_pid6=parent_id,
        unit_name=unit_name,
        unit_type=unit_type,
        active=active,
        raw_fields=MappingProxyType(dict(raw_fields)),
    )


def _open_zip(payload: bytes, *, source_name: str) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise CensusGovernmentSourceError(
            f"{source_name} is not a valid ZIP archive"
        ) from exc


def _validate_zip_members(
    archive: zipfile.ZipFile,
    *,
    max_uncompressed_bytes: int,
    source_name: str,
) -> tuple[zipfile.ZipInfo, ...]:
    infos = tuple(info for info in archive.infolist() if not info.is_dir())
    names = [info.filename for info in infos]
    if len(names) != len(set(names)):
        raise CensusGovernmentSourceError(
            f"{source_name} contains duplicate member names"
        )
    total_uncompressed = 0
    for info in infos:
        _validate_member_path(info.filename, source_name=source_name)
        if info.flag_bits & 0x1:
            raise CensusGovernmentSourceError(
                f"{source_name} contains an encrypted member"
            )
        total_uncompressed += info.file_size
    if total_uncompressed > max_uncompressed_bytes:
        raise CensusGovernmentSourceError(
            f"{source_name} exceeds the configured uncompressed-size limit"
        )
    return infos


def _validate_member_path(name: str, *, source_name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise CensusGovernmentSourceError(
            f"{source_name} contains an unsafe member path {name!r}"
        )


def _normalize_workbook_target(target: str) -> str:
    path = PurePosixPath(target)
    if path.is_absolute() or ".." in path.parts:
        raise CensusGovernmentSourceError(
            f"Government Units workbook has an unsafe relationship {target!r}"
        )
    normalized = str(PurePosixPath("xl") / path)
    return normalized


def _parse_xml(payload: bytes, *, source_name: str) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise CensusGovernmentSourceError(
            f"Invalid XML in Government Units workbook member {source_name!r}"
        ) from exc


def _required_row_number(row_element: ElementTree.Element) -> int:
    value = row_element.attrib.get("r")
    if value is None or not value.isdigit() or int(value) < 1:
        raise CensusGovernmentSourceError(
            "Government Units workbook row is missing a valid row number"
        )
    return int(value)


def _parse_cell_reference(reference: str) -> tuple[int, int]:
    match = _CELL_REF_RE.fullmatch(reference)
    if match is None:
        raise CensusGovernmentSourceError(
            f"Invalid Government Units workbook cell reference {reference!r}"
        )
    column_text, row_text = match.groups()
    column_number = 0
    for character in column_text:
        column_number = column_number * 26 + ord(character) - 64
    return column_number - 1, int(row_text)


def _excel_column_name(column_count: int) -> str:
    if column_count < 1:
        raise ValueError("column_count must be positive")
    value = column_count
    characters: list[str] = []
    while value:
        value, remainder = divmod(value - 1, 26)
        characters.append(chr(65 + remainder))
    return "".join(reversed(characters))


def _required_text(
    fields: Mapping[str, str | None],
    field: str,
) -> str:
    value = fields.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(
    fields: Mapping[str, str | None],
    field: str,
) -> str | None:
    value = fields.get(field)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _required_digits(
    fields: Mapping[str, str | None],
    field: str,
    length: int,
) -> str:
    value = _required_text(fields, field)
    if len(value) != length or not value.isdigit():
        raise ValueError(
            f"{field} must be an exact {length}-digit string"
        )
    return value


def _load_json_object(
    payload: bytes,
    *,
    source_name: str,
    error_type: type[Exception],
) -> dict[str, Any]:
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise error_type(f"Invalid JSON in {source_name}: {exc}") from exc
    if not isinstance(document, dict):
        raise error_type(f"JSON in {source_name} must be an object")
    return document


def _required_manifest_text(
    manifest: Mapping[str, Any],
    field: str,
) -> str:
    value = manifest.get(field)
    if not isinstance(value, str) or not value:
        raise CensusGovernmentSnapshotIntegrityError(
            f"Government Units manifest field {field!r} is invalid"
        )
    return value


def _required_manifest_int(
    manifest: Mapping[str, Any],
    field: str,
) -> int:
    value = manifest.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CensusGovernmentSnapshotIntegrityError(
            f"Government Units manifest field {field!r} is invalid"
        )
    return value



def _required_utc_timestamp(
    manifest: Mapping[str, Any],
    field: str,
) -> str:
    value = _required_manifest_text(manifest, field)
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CensusGovernmentSnapshotIntegrityError(
            f"Government Units manifest field {field!r} is not an ISO timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise CensusGovernmentSnapshotIntegrityError(
            f"Government Units manifest field {field!r} must be UTC"
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
