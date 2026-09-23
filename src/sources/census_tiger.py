"""
Census TIGER geography: TIGER/Line attribute tables and TIGERweb URLs.

``config/tiger_layers.yaml`` names, for each geography layer, the TIGER/Line
shapefile that carries its attribute table and the TIGERweb MapServer layer
that serves its boundary as GeoJSON. This module loads that configuration,
fetches TIGER/Line zips through the snapshot store, reads the attribute
table (never the geometry) into plain records, and builds the TIGERweb
query URL for a GEOID. No polygon is ever downloaded here.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path

import yaml

from src.init_migration.downloader import AsyncDownloader
from src.sources.dbf import read_dbf
from src.sources.snapshot import (
    Snapshot,
    SnapshotMetadata,
    SnapshotSpec,
    SnapshotStore,
)

logger = getLogger(__name__)

SOURCE = "tiger"
SOURCE_NAME = "Census TIGER/Line"
DATASET = "TIGER/Line Shapefiles"
DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "tiger_layers.yaml"
)

GEOJSON_QUERY = "query?where=GEOID%3D'{geoid}'&outFields=*&outSR=4326&f=geojson"

_STATEFP = re.compile(r"^\d{2}$")
_COUNTYFP = re.compile(r"^\d{3}$")
_FIVE_DIGITS = re.compile(r"^\d{5}$")
_DIGITS = re.compile(r"^\d+$")
LEA_COLUMNS = ("UNSDLEA", "SCSDLEA", "ELSDLEA")
CDP_CLASS_CODES = frozenset({"U1", "U2"})
CDP_LSAD = "57"


@dataclass(frozen=True, slots=True)
class TigerLineFile:
    directory: str
    filename: str
    scope: str

    def __post_init__(self) -> None:
        if self.scope not in ("national", "state"):
            raise ValueError(f"scope must be national or state, got {self.scope!r}")


@dataclass(frozen=True, slots=True)
class TigerWebLayer:
    service: str
    layer: int


@dataclass(frozen=True, slots=True)
class LayerConfig:
    key: str
    geography: str
    geoid_length: int
    tiger_line: TigerLineFile
    tigerweb: TigerWebLayer


@dataclass(frozen=True, slots=True)
class TigerConfig:
    tiger_line_base_url: str
    tigerweb_base_url: str
    layers: Mapping[str, LayerConfig]

    def layer(self, key: str) -> LayerConfig:
        try:
            return self.layers[key]
        except KeyError:
            raise KeyError(f"unknown TIGER layer {key!r}") from None

    def layers_for(self, geography: str) -> list[LayerConfig]:
        return [layer for layer in self.layers.values() if layer.geography == geography]

    def geographies(self) -> list[str]:
        return sorted({layer.geography for layer in self.layers.values()})


def parse_tiger_config(text: str) -> TigerConfig:
    raw = yaml.safe_load(text)
    layers: dict[str, LayerConfig] = {}
    for key, entry in raw["layers"].items():
        layers[key] = LayerConfig(
            key=key,
            geography=entry["geography"],
            geoid_length=int(entry["geoid_length"]),
            tiger_line=TigerLineFile(**entry["tiger_line"]),
            tigerweb=TigerWebLayer(
                service=entry["tigerweb"]["service"],
                layer=int(entry["tigerweb"]["layer"]),
            ),
        )
    return TigerConfig(
        tiger_line_base_url=raw["tiger_line_base_url"],
        tigerweb_base_url=raw["tigerweb_base_url"],
        layers=layers,
    )


def load_tiger_config(path: Path = DEFAULT_CONFIG_PATH) -> TigerConfig:
    return parse_tiger_config(Path(path).read_text(encoding="utf-8"))


def series_as_of(year: int | str) -> datetime:
    """The date a TIGER/Line release describes: January 1 of the release year."""
    return datetime(int(year), 1, 1, tzinfo=timezone.utc)


def tiger_line_filename(
    config: TigerConfig, layer_key: str, year: int | str, state_fips: str | None = None
) -> str:
    layer = config.layer(layer_key)
    if layer.tiger_line.scope == "state":
        if state_fips is None or not _STATEFP.match(state_fips):
            raise ValueError(
                f"layer {layer_key!r} is published per state; state_fips must be two digits"
            )
        return layer.tiger_line.filename.format(year=int(year), state=state_fips)
    if state_fips is not None:
        raise ValueError(f"layer {layer_key!r} is national; state_fips must be None")
    return layer.tiger_line.filename.format(year=int(year))


def tiger_line_url(
    config: TigerConfig, layer_key: str, year: int | str, state_fips: str | None = None
) -> str:
    layer = config.layer(layer_key)
    base = config.tiger_line_base_url.format(year=int(year))
    return f"{base}/{layer.tiger_line.directory}/{tiger_line_filename(config, layer_key, year, state_fips)}"


def tiger_line_spec(
    config: TigerConfig, layer_key: str, year: int | str, state_fips: str | None = None
) -> SnapshotSpec:
    """Snapshot spec for one TIGER/Line zip."""
    return SnapshotSpec(
        source=SOURCE,
        source_name=SOURCE_NAME,
        dataset=f"{DATASET}, {config.layer(layer_key).tiger_line.directory}",
        release=str(int(year)),
        filename=tiger_line_filename(config, layer_key, year, state_fips),
        url=tiger_line_url(config, layer_key, year, state_fips),
    )


async def fetch_tiger_line(
    store: SnapshotStore,
    downloader: AsyncDownloader,
    config: TigerConfig,
    layer_key: str,
    year: int | str,
    *,
    retrieved_at: datetime,
    state_fips: str | None = None,
    refresh: bool = False,
) -> Snapshot:
    return await store.fetch(
        tiger_line_spec(config, layer_key, year, state_fips),
        downloader,
        retrieved_at=retrieved_at,
        refresh=refresh,
    )


def tigerweb_service_url(config: TigerConfig, layer_key: str) -> str:
    """The MapServer a layer is served from; the URL cited as a geometry's source."""
    layer = config.layer(layer_key)
    return f"{config.tigerweb_base_url}/{layer.tigerweb.service}/MapServer"


def tigerweb_query_url(config: TigerConfig, layer_key: str, geoid: str) -> str:
    """The GeoJSON query for one GEOID in one layer. No request is made."""
    layer = config.layer(layer_key)
    if not _DIGITS.match(geoid) or len(geoid) != layer.geoid_length:
        raise ValueError(
            f"GEOID {geoid!r} is not {layer.geoid_length} digits as layer {layer_key!r} requires"
        )
    return (
        f"{tigerweb_service_url(config, layer_key)}/{layer.tigerweb.layer}/"
        + GEOJSON_QUERY.format(geoid=geoid)
    )


@dataclass(frozen=True, slots=True)
class TigerRecord:
    """One row of a TIGER/Line attribute table, geometry excluded.

    ``layer`` is the configuration key the row was read under and
    ``geography`` its class. Codes are strings exactly as published.
    """

    layer: str
    geography: str
    geoid: str
    name: str
    statefp: str
    geoidfq: str | None = None
    namelsad: str | None = None
    countyfp: str | None = None
    placefp: str | None = None
    cousubfp: str | None = None
    lea: str | None = None
    lsad: str | None = None
    classfp: str | None = None
    funcstat: str | None = None
    mtfcc: str | None = None
    attributes: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TigerRowError:
    file: str
    line: int
    geoid: str
    reason: str


@dataclass(slots=True)
class TigerParseResult:
    records: list[TigerRecord] = field(default_factory=list)
    errors: list[TigerRowError] = field(default_factory=list)
    metadata: SnapshotMetadata | None = None


NAMED_COLUMNS = frozenset(
    {
        "GEOID",
        "GEOIDFQ",
        "NAME",
        "NAMELSAD",
        "STATEFP",
        "COUNTYFP",
        "PLACEFP",
        "COUSUBFP",
        "LSAD",
        "CLASSFP",
        "FUNCSTAT",
        "MTFCC",
        *LEA_COLUMNS,
    }
)


def _code(
    value: str, pattern: re.Pattern[str], column: str, problems: list[str]
) -> str | None:
    if not value:
        return None
    if not pattern.match(value):
        problems.append(f"{column} is malformed: {value!r}")
        return None
    return value


def parse_row(
    row: Mapping[str, str], layer: LayerConfig, file: str, line: int
) -> TigerRecord | TigerRowError:
    cells = {str(key): (value or "").strip() for key, value in row.items() if key}
    problems: list[str] = []
    geoid = cells.get("GEOID", "")
    if not _DIGITS.match(geoid) or len(geoid) != layer.geoid_length:
        problems.append(f"GEOID is not {layer.geoid_length} digits: {geoid!r}")
    name = cells.get("NAME", "")
    if not name:
        problems.append("NAME is empty")
    statefp = cells.get("STATEFP", "")
    if not _STATEFP.match(statefp):
        problems.append(f"STATEFP is malformed: {statefp!r}")
    elif geoid and not geoid.startswith(statefp):
        problems.append(f"GEOID {geoid!r} does not start with STATEFP {statefp!r}")
    countyfp = _code(cells.get("COUNTYFP", ""), _COUNTYFP, "COUNTYFP", problems)
    placefp = _code(cells.get("PLACEFP", ""), _FIVE_DIGITS, "PLACEFP", problems)
    cousubfp = _code(cells.get("COUSUBFP", ""), _FIVE_DIGITS, "COUSUBFP", problems)
    lea = None
    for column in LEA_COLUMNS:
        if cells.get(column):
            lea = _code(cells[column], _FIVE_DIGITS, column, problems)
    if problems:
        return TigerRowError(
            file=file, line=line, geoid=geoid, reason="; ".join(problems)
        )
    return TigerRecord(
        layer=layer.key,
        geography=layer.geography,
        geoid=geoid,
        name=name,
        statefp=statefp,
        geoidfq=cells.get("GEOIDFQ") or None,
        namelsad=cells.get("NAMELSAD") or None,
        countyfp=countyfp,
        placefp=placefp,
        cousubfp=cousubfp,
        lea=lea,
        lsad=cells.get("LSAD") or None,
        classfp=cells.get("CLASSFP") or None,
        funcstat=cells.get("FUNCSTAT") or None,
        mtfcc=cells.get("MTFCC") or None,
        attributes={k: v for k, v in cells.items() if k not in NAMED_COLUMNS},
    )


def parse_rows(
    rows: Iterable[Mapping[str, str]],
    layer: LayerConfig,
    file: str,
    *,
    first_line: int = 2,
) -> TigerParseResult:
    result = TigerParseResult()
    for offset, row in enumerate(rows):
        outcome = parse_row(row, layer, file, first_line + offset)
        if isinstance(outcome, TigerRowError):
            result.errors.append(outcome)
        else:
            result.records.append(outcome)
    return result


def parse_csv(text: str, layer: LayerConfig, file: str) -> TigerParseResult:
    """Parse a CSV export of an attribute table (header row included)."""
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames is None:
        result = TigerParseResult()
        result.errors.append(
            TigerRowError(file=file, line=1, geoid="", reason="empty file")
        )
        return result
    return parse_rows(reader, layer, file)


def parse_csv_snapshot(
    snapshot: Snapshot, config: TigerConfig, layer_key: str
) -> TigerParseResult:
    result = parse_csv(
        snapshot.read_text(), config.layer(layer_key), snapshot.path.name
    )
    result.metadata = snapshot.metadata
    _log(result, snapshot.path.name)
    return result


def attribute_table(snapshot: Snapshot) -> bytes:
    """The ``.dbf`` bytes inside a TIGER/Line zip."""
    with zipfile.ZipFile(snapshot.path) as archive:
        members = [m for m in archive.namelist() if m.lower().endswith(".dbf")]
        if len(members) != 1:
            raise ValueError(
                f"expected one .dbf in {snapshot.path.name}, found {len(members)}"
            )
        return archive.read(members[0])


def parse_snapshot(
    snapshot: Snapshot, config: TigerConfig, layer_key: str
) -> TigerParseResult:
    """Parse the attribute table of a fetched TIGER/Line zip."""
    rows = read_dbf(attribute_table(snapshot))
    result = parse_rows(rows, config.layer(layer_key), snapshot.path.name, first_line=1)
    result.metadata = snapshot.metadata
    _log(result, snapshot.path.name)
    return result


def place_layer_key(record: TigerRecord) -> str:
    """The TIGERweb layer a PLACE row belongs to: CDPs are served separately."""
    if record.geography != "place":
        return record.layer
    if record.classfp in CDP_CLASS_CODES or record.lsad == CDP_LSAD:
        return "census_designated_place"
    return "place"


def geometry_url(config: TigerConfig, record: TigerRecord) -> str:
    """The GeoJSON query URL for a record's boundary."""
    return tigerweb_query_url(config, place_layer_key(record), record.geoid)


def _log(result: TigerParseResult, name: str) -> None:
    logger.info(
        "tiger attribute table parsed",
        extra={
            "snapshot_file": name,
            "records": len(result.records),
            "row_errors": len(result.errors),
        },
    )
