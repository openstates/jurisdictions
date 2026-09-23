"""
Merge a Census of Governments benchmark with a later annual listing.

The benchmark (``census_governments.py``) is the government universe the
pipeline builds from every five years; the annual listing
(``census_gus.py``) updates it in between. This module diffs the two by
Census ID and produces the current universe:

- a government in both listings takes the annual listing's values, with the
  benchmark's ``legacy_id`` carried forward because the annual listing does
  not publish it;
- a government only in the annual listing is added;
- a government only in the benchmark is kept and flagged, never dropped.

Pension systems are not governments and are left out of both sides. Every
record in the merged output carries a status, and every field-level
difference is recorded so a reviewer can see exactly what the annual
listing changed. Both outputs are written under the cache root with
sidecars naming the two releases they were derived from.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from enum import Enum
from logging import getLogger
from pathlib import Path

from src.sources.government_units import (
    EXPORT_COLUMNS,
    CensusGovernmentRecord,
    GovernmentKind,
    ParseResult,
    record_values,
)
from src.sources.snapshot import (
    Snapshot,
    SnapshotMetadata,
    sha256_of_bytes,
    write_metadata,
)

logger = getLogger(__name__)

SOURCE = "government_units"
DEFAULT_CACHE_ROOT = Path("data/cache")
MERGED_FILENAME = "merged_governments.csv"
CHANGES_FILENAME = "government_changes.csv"

# Fields the annual listing publishes but the benchmark does not, or the
# reverse. They cannot differ meaningfully between the two, so they are not
# compared; the merged record takes them from whichever side has them.
ONE_SIDED_FIELDS = frozenset(
    {"legacy_id", "political_code", "parent_census_id", "parent_name"}
)
COMPARED_FIELDS = tuple(
    column
    for column in EXPORT_COLUMNS
    if column not in ONE_SIDED_FIELDS and column != "census_id"
)


class MergeStatus(str, Enum):
    """What the annual listing did to a benchmark government."""

    UNCHANGED = "unchanged"
    FILLED = "filled"
    CHANGED = "changed"
    ADDED = "added"
    REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class FieldChange:
    """One field that differs between the benchmark and the annual listing.

    ``filled`` is true when the benchmark had no value and the annual listing
    supplied one; a true change has a value on both sides.
    """

    census_id: str
    field: str
    benchmark_value: str
    annual_value: str
    filled: bool


@dataclass(frozen=True, slots=True)
class MergedRecord:
    record: CensusGovernmentRecord
    status: MergeStatus
    changes: tuple[FieldChange, ...] = ()


@dataclass(slots=True)
class MergeResult:
    benchmark: SnapshotMetadata
    annual: SnapshotMetadata
    records: list[MergedRecord] = field(default_factory=list)

    def by_status(self, status: MergeStatus) -> list[MergedRecord]:
        return [merged for merged in self.records if merged.status is status]

    def counts(self) -> dict[str, int]:
        return {status.value: len(self.by_status(status)) for status in MergeStatus}

    def changes(self) -> list[FieldChange]:
        return [change for merged in self.records for change in merged.changes]


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Y" if value else "N"
    if isinstance(value, GovernmentKind):
        return value.value
    return str(value)


def _governments(
    records: Iterable[CensusGovernmentRecord],
) -> dict[str, CensusGovernmentRecord]:
    index: dict[str, CensusGovernmentRecord] = {}
    for record in records:
        if record.kind is GovernmentKind.PUBLIC_PENSION_SYSTEM:
            continue
        index.setdefault(record.census_id, record)
    return index


def diff_records(
    benchmark: CensusGovernmentRecord, annual: CensusGovernmentRecord
) -> tuple[FieldChange, ...]:
    """Field-level differences on the compared fields, in field order."""
    changes: list[FieldChange] = []
    for column in COMPARED_FIELDS:
        old = getattr(benchmark, column)
        new = getattr(annual, column)
        if old == new:
            continue
        changes.append(
            FieldChange(
                census_id=benchmark.census_id,
                field=column,
                benchmark_value=_cell(old),
                annual_value=_cell(new),
                filled=old is None and new is not None,
            )
        )
    return tuple(changes)


def merge_records(
    benchmark: CensusGovernmentRecord, annual: CensusGovernmentRecord
) -> CensusGovernmentRecord:
    """The annual record, carrying the benchmark's one-sided fields when it lacks them."""
    carried = {
        column: getattr(benchmark, column)
        for column in ONE_SIDED_FIELDS
        if getattr(annual, column) is None and getattr(benchmark, column) is not None
    }
    return replace(annual, **carried) if carried else annual


def merge(benchmark: ParseResult, annual: ParseResult) -> MergeResult:
    """Diff and merge two parsed listings into the current government universe."""
    if benchmark.metadata is None or annual.metadata is None:
        raise ValueError("both parse results must carry snapshot metadata")
    old = _governments(benchmark.records)
    new = _governments(annual.records)
    result = MergeResult(benchmark=benchmark.metadata, annual=annual.metadata)

    for census_id in sorted(old.keys() | new.keys()):
        if census_id in old and census_id in new:
            changes = diff_records(old[census_id], new[census_id])
            if not changes:
                status = MergeStatus.UNCHANGED
            elif all(change.filled for change in changes):
                status = MergeStatus.FILLED
            else:
                status = MergeStatus.CHANGED
            record = merge_records(old[census_id], new[census_id])
        elif census_id in new:
            status, record, changes = MergeStatus.ADDED, new[census_id], ()
        else:
            status, record, changes = MergeStatus.REMOVED, old[census_id], ()
        result.records.append(
            MergedRecord(record=record, status=status, changes=changes)
        )

    logger.info(
        "government listings merged",
        extra={
            "benchmark_release": benchmark.metadata.release,
            "annual_release": annual.metadata.release,
            **result.counts(),
        },
    )
    return result


MERGED_COLUMNS = (
    *EXPORT_COLUMNS,
    "merge_status",
    "benchmark_release",
    "annual_release",
)
CHANGE_COLUMNS = ("census_id", "field", "benchmark_value", "annual_value", "filled")


def merged_csv(result: MergeResult) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(MERGED_COLUMNS)
    for merged in result.records:
        writer.writerow(
            [
                *record_values(merged.record),
                merged.status.value,
                result.benchmark.release,
                result.annual.release,
            ]
        )
    return buffer.getvalue()


def changes_csv(result: MergeResult) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CHANGE_COLUMNS)
    for change in result.changes():
        writer.writerow(
            [
                change.census_id,
                change.field,
                change.benchmark_value,
                change.annual_value,
                "Y" if change.filled else "N",
            ]
        )
    return buffer.getvalue()


def _write(
    result: MergeResult, directory: Path, filename: str, content: str, what: str
) -> Snapshot:
    later = max(result.benchmark.retrieved_at, result.annual.retrieved_at)
    data = content.encode("utf-8")
    path = directory / filename
    path.write_bytes(data)
    metadata = SnapshotMetadata(
        source=SOURCE,
        source_name=result.annual.source_name,
        dataset=(
            f"{what}: Census of Governments {result.benchmark.release} "
            f"({result.benchmark.filename}, sha256 {result.benchmark.sha256}) updated by "
            f"annual listing {result.annual.release} "
            f"({result.annual.filename}, sha256 {result.annual.sha256})"
        ),
        release=f"{result.benchmark.release}-{result.annual.release}",
        filename=filename,
        url=result.annual.url,
        sha256=sha256_of_bytes(data),
        size_bytes=len(data),
        retrieved_at=later,
        publication_date=result.annual.publication_date,
    )
    write_metadata(path, metadata)
    return Snapshot(path=path, metadata=metadata)


def export_merge(
    result: MergeResult, *, cache_root: Path = DEFAULT_CACHE_ROOT
) -> tuple[Snapshot, Snapshot]:
    """Write the merged universe and the change report under the cache root.

    Files land at ``<cache_root>/government_units/<benchmark>-<annual>/``.
    Each sidecar's ``dataset`` names both source files and checksums; its
    ``url`` is the annual listing's and its ``retrieved_at`` the later of the
    two sources' retrieval times.
    """
    directory = (
        Path(cache_root)
        / SOURCE
        / f"{result.benchmark.release}-{result.annual.release}"
    )
    directory.mkdir(parents=True, exist_ok=True)
    merged = _write(
        result,
        directory,
        MERGED_FILENAME,
        merged_csv(result),
        "Merged government units",
    )
    changes = _write(
        result,
        directory,
        CHANGES_FILENAME,
        changes_csv(result),
        "Government unit changes",
    )
    logger.info(
        "merge exported",
        extra={
            "directory": str(directory),
            "records": len(result.records),
            "changes": len(result.changes()),
        },
    )
    return merged, changes
