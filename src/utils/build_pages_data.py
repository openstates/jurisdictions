"""Build the Pages site's data: one Parquet file per table, plus manifest.json.

Committed data/parquet/ is split by state so populate PRs for different states
don't clash. The site loads much faster from one file per table, so the deploy
job (deploy-pages.yml) combines them here. Row counts and columns come from the
files written, not from a pipeline DuckDB.

    uv run python -m src.utils.build_pages_data --src data/parquet --out pages/data
"""

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

import duckdb

logger = logging.getLogger(__name__)

DEFAULT_SRC = "data/parquet"
DEFAULT_OUT = "pages/data"
MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True)
class TablePlan:
    name: str
    sources: list[str]
    partitioned: bool


class Column(TypedDict):
    name: str
    type: str


class ManifestEntry(TypedDict):
    name: str
    file: str
    rows: int
    bytes: int
    columns: list[Column]


class Manifest(TypedDict):
    generated_at: str
    tables: list[ManifestEntry]


def plan_tables(paths: list[str]) -> list[TablePlan]:
    """Group paths relative to data/parquet/ into tables.

    `<table>.parquet` is a single-file table; `<table>/state=xx/<file>.parquet`
    is a state-partitioned one. Anything else (e.g. an old manifest.json) is ignored.
    """
    singles: dict[str, str] = {}
    partitioned: dict[str, list[str]] = {}
    for path in paths:
        parts = path.split("/")
        if len(parts) == 1 and path.endswith(".parquet"):
            singles[path.removesuffix(".parquet")] = path
        elif len(parts) == 3 and parts[1].startswith("state=") and parts[2].endswith(".parquet"):
            partitioned.setdefault(parts[0], []).append(path)

    both = sorted(singles.keys() & partitioned.keys())
    if both:
        raise ValueError(f"Stored both as a file and as a folder: {', '.join(both)}")

    plans = [TablePlan(name, [path], False) for name, path in singles.items()]
    plans += [TablePlan(name, sorted(group), True) for name, group in partitioned.items()]
    return sorted(plans, key=lambda plan: plan.name)


def manifest_document(entries: list[ManifestEntry], generated_at: datetime) -> Manifest:
    return Manifest(generated_at=generated_at.isoformat(), tables=entries)


def build_table(
    conn: duckdb.DuckDBPyConnection, src_dir: Path, out_dir: Path, plan: TablePlan
) -> ManifestEntry:
    file_name = f"{plan.name}.parquet"
    out_path = out_dir / file_name
    sources = ", ".join(f"'{src_dir / source}'" for source in plan.sources)
    # The state column lives in the folder names; read it back as text ('' stays '').
    options = ", hive_partitioning=true, hive_types_autocast=false, union_by_name=true"
    reader = f"read_parquet([{sources}]{options if plan.partitioned else ''})"

    conn.execute(f"COPY (SELECT * FROM {reader}) TO '{out_path}' (FORMAT PARQUET, COMPRESSION ZSTD)")

    written = f"read_parquet('{out_path}')"
    rows = conn.execute(f"SELECT COUNT(*) FROM {written}").fetchone()[0]
    columns = [
        Column(name=row[0], type=row[1])
        for row in conn.execute(f"DESCRIBE SELECT * FROM {written}").fetchall()
    ]
    return ManifestEntry(
        name=plan.name, file=file_name, rows=rows, bytes=out_path.stat().st_size, columns=columns
    )


def build_pages_data(src_dir: Path, out_dir: Path) -> Path:
    paths = sorted(str(p.relative_to(src_dir)) for p in src_dir.rglob("*") if p.is_file())
    plans = plan_tables(paths)
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect()
    try:
        entries = [build_table(conn, src_dir, out_dir, plan) for plan in plans]
    finally:
        conn.close()

    manifest_path = out_dir / MANIFEST_NAME
    manifest = manifest_document(entries, datetime.now(tz=UTC))
    manifest_path.write_text(json.dumps(manifest, indent=2))
    logger.info(
        "Built Pages data", extra={"tables": len(entries), "out_dir": str(out_dir)}
    )
    return manifest_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", default=DEFAULT_SRC, help="state-partitioned Parquet (committed)")
    parser.add_argument("--out", default=DEFAULT_OUT, help="site data folder")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    build_pages_data(Path(args.src), Path(args.out))


if __name__ == "__main__":
    main()
