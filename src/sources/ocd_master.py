"""
Open Civic Data division-id corpus as an in-memory exact-lookup index.

The national ``country-us.csv`` is the canonical roster of OCD Division
identifiers. Per-state ``state-<st>-local_gov.csv`` files list the local
governments each state file claims; they are loaded alongside the master
so a caller can see which local ids the master lacks.

Membership is an exact string match on the id. Fuzzy suggestions exist for
human review only and are returned by a separate call that never feeds
membership.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from logging import getLogger

from rapidfuzz import fuzz

from src.errors import OCDIdParsingError
from src.init_migration.download_manager import LOCAL_TEMPLATE, MASTER_PATH, RAW_BASE
from src.init_migration.downloader import AsyncDownloader
from src.models.ocdid import OCDIdParsed
from src.models.source import SourceObj, SourceType
from src.sources.snapshot import (
    Snapshot,
    SnapshotMetadata,
    SnapshotSpec,
    SnapshotStore,
    source_obj_from_snapshot,
)

logger = getLogger(__name__)

SOURCE = "ocd_master"
SOURCE_NAME = "Open Civic Data"
DATASET_MASTER = "ocd-division-ids/identifiers/country-us.csv"
DATASET_LOCAL = "ocd-division-ids/identifiers/country-us/state-{state}-local_gov.csv"
DEFAULT_RELEASE = "master"
MASTER_FILENAME = MASTER_PATH
LOCAL_FILENAME = "state-{state}-local_gov.csv"
LOCAL_COLUMNS = ("id", "name")


def master_url() -> str:
    return f"{RAW_BASE}/{MASTER_PATH}"


def local_url(state: str) -> str:
    return f"{RAW_BASE}/{LOCAL_TEMPLATE.format(state=state.lower())}"


def master_spec(release: str = DEFAULT_RELEASE) -> SnapshotSpec:
    """Snapshot spec for the national master CSV at ``release`` (a git ref)."""
    return SnapshotSpec(
        source=SOURCE,
        source_name=SOURCE_NAME,
        dataset=DATASET_MASTER,
        release=release,
        filename=MASTER_FILENAME,
        url=master_url(),
    )


def local_spec(state: str, release: str = DEFAULT_RELEASE) -> SnapshotSpec:
    """Snapshot spec for one state's local-government CSV."""
    state = state.lower()
    return SnapshotSpec(
        source=SOURCE,
        source_name=SOURCE_NAME,
        dataset=DATASET_LOCAL.format(state=state),
        release=release,
        filename=LOCAL_FILENAME.format(state=state),
        url=local_url(state),
    )


async def fetch_master(
    store: SnapshotStore,
    downloader: AsyncDownloader,
    *,
    retrieved_at: datetime,
    release: str = DEFAULT_RELEASE,
    refresh: bool = False,
) -> Snapshot:
    return await store.fetch(
        master_spec(release), downloader, retrieved_at=retrieved_at, refresh=refresh
    )


async def fetch_local(
    store: SnapshotStore,
    downloader: AsyncDownloader,
    state: str,
    *,
    retrieved_at: datetime,
    release: str = DEFAULT_RELEASE,
    refresh: bool = False,
) -> Snapshot:
    return await store.fetch(
        local_spec(state, release),
        downloader,
        retrieved_at=retrieved_at,
        refresh=refresh,
    )


@dataclass(frozen=True, slots=True)
class OCDMasterEntry:
    """One master row: the id, its upstream name, the parsed id, other columns."""

    ocdid: str
    name: str
    parsed: OCDIdParsed
    attributes: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class OCDRowError:
    """A row that could not be indexed, kept so nothing is dropped silently."""

    file: str
    line: int
    raw_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class Suggestion:
    """A near match offered for human review. Never a membership result."""

    ocdid: str
    name: str
    score: float


def _parse(
    raw_id: str, file: str, line: int, errors: list[OCDRowError]
) -> OCDIdParsed | None:
    try:
        return OCDIdParsed.parse_ocdid(raw_id)
    except OCDIdParsingError as error:
        errors.append(
            OCDRowError(file=file, line=line, raw_id=raw_id, reason=str(error.message))
        )
        return None


def parse_master_csv(
    text: str, file: str = MASTER_FILENAME
) -> tuple[list[OCDMasterEntry], list[OCDRowError]]:
    """Parse the master CSV (upstream header) into entries and row errors."""
    entries: list[OCDMasterEntry] = []
    errors: list[OCDRowError] = []
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames is None or "id" not in reader.fieldnames:
        errors.append(
            OCDRowError(file=file, line=1, raw_id="", reason="missing id column")
        )
        return entries, errors
    for row in reader:
        line = reader.line_num
        raw_id = (row.get("id") or "").strip()
        if not raw_id:
            errors.append(
                OCDRowError(file=file, line=line, raw_id="", reason="empty id")
            )
            continue
        parsed = _parse(raw_id, file, line, errors)
        if parsed is None:
            continue
        attributes = {
            key: (value or "")
            for key, value in row.items()
            if key not in ("id", "name") and key is not None
        }
        entries.append(
            OCDMasterEntry(
                ocdid=raw_id,
                name=(row.get("name") or "").strip(),
                parsed=parsed,
                attributes=attributes,
            )
        )
    return entries, errors


def parse_local_csv(
    text: str, file: str
) -> tuple[list[tuple[str, str]], list[OCDRowError]]:
    """Parse a headerless ``id,name`` state file into (id, name) pairs."""
    rows: list[tuple[str, str]] = []
    errors: list[OCDRowError] = []
    reader = csv.reader(io.StringIO(text, newline=""))
    for line, record in enumerate(reader, start=1):
        if not record or not any(cell.strip() for cell in record):
            continue
        raw_id = record[0].strip()
        name = record[1].strip() if len(record) > 1 else ""
        if _parse(raw_id, file, line, errors) is None:
            continue
        rows.append((raw_id, name))
    return rows, errors


class OCDMasterIndex:
    """Exact membership over the master roster, with optional local files."""

    def __init__(
        self,
        entries: Iterable[OCDMasterEntry],
        *,
        metadata: SnapshotMetadata,
        errors: Iterable[OCDRowError] = (),
        local: Mapping[str, Iterable[str]] | None = None,
    ) -> None:
        self._entries: dict[str, OCDMasterEntry] = {}
        for entry in entries:
            self._entries.setdefault(entry.ocdid, entry)
        self.metadata = metadata
        self.errors: list[OCDRowError] = list(errors)
        self._local: dict[str, frozenset[str]] = {
            state.lower(): frozenset(ids) for state, ids in (local or {}).items()
        }

    @classmethod
    def from_snapshots(
        cls,
        master: Snapshot,
        local: Mapping[str, Snapshot] | None = None,
    ) -> OCDMasterIndex:
        """Build the index from a master snapshot and per-state local snapshots."""
        entries, errors = parse_master_csv(master.read_text(), master.path.name)
        local_ids: dict[str, list[str]] = {}
        for state, snapshot in (local or {}).items():
            rows, local_errors = parse_local_csv(
                snapshot.read_text(), snapshot.path.name
            )
            errors.extend(local_errors)
            local_ids[state.lower()] = [ocdid for ocdid, _ in rows]
        logger.info(
            "ocd master index loaded",
            extra={
                "entries": len(entries),
                "row_errors": len(errors),
                "local_states": sorted(local_ids),
                "release": master.metadata.release,
            },
        )
        return cls(entries, metadata=master.metadata, errors=errors, local=local_ids)

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[OCDMasterEntry]:
        return iter(self._entries.values())

    def __contains__(self, ocdid: object) -> bool:
        return ocdid in self._entries

    def contains(self, ocdid: str) -> bool:
        """Exact membership: the string is a master id, character for character."""
        return ocdid in self._entries

    def get(self, ocdid: str) -> OCDMasterEntry | None:
        return self._entries.get(ocdid)

    def local_states(self) -> list[str]:
        return sorted(self._local)

    def local_ids(self, state: str) -> frozenset[str]:
        return self._local.get(state.lower(), frozenset())

    def local_orphans(self, state: str) -> list[str]:
        """Ids in the state's local file that the master does not contain."""
        return sorted(
            ocdid for ocdid in self.local_ids(state) if ocdid not in self._entries
        )

    def place_names_by_state(self) -> dict[str, set[str]]:
        """Lowercased upstream names of ``place:`` ids, grouped by state."""
        by_state: dict[str, set[str]] = {}
        for entry in self._entries.values():
            if entry.parsed.place and entry.parsed.state:
                by_state.setdefault(entry.parsed.state, set()).add(entry.name.lower())
        return by_state

    def suggest(
        self, ocdid: str, *, limit: int = 5, min_score: float = 80.0
    ) -> list[Suggestion]:
        """Near matches for review, best first. Independent of membership.

        Candidates are narrowed to the query's state when the query parses
        with one; otherwise every master id is scored.
        """
        state: str | None = None
        try:
            state = OCDIdParsed.parse_ocdid(ocdid).state
        except OCDIdParsingError:
            state = None
        candidates = (
            entry
            for entry in self._entries.values()
            if state is None or entry.parsed.state == state
        )
        scored = [
            Suggestion(ocdid=entry.ocdid, name=entry.name, score=score)
            for entry in candidates
            if (score := float(fuzz.ratio(ocdid, entry.ocdid))) >= min_score
        ]
        scored.sort(key=lambda suggestion: (-suggestion.score, suggestion.ocdid))
        return scored[:limit]

    def source_obj(
        self,
        field: list[str],
        *,
        source_type: SourceType = SourceType.SCRAPED,
        source_description: str | None = None,
    ) -> SourceObj:
        """Provenance for values taken from this roster."""
        return source_obj_from_snapshot(
            self.metadata,
            field=field,
            source_type=source_type,
            source_description=source_description,
        )
