import logging
import json
import duckdb
from pathlib import Path
from datetime import UTC, datetime
from dataclasses import dataclass
# from src.init_migration.main import GENERATION_TRACKING_PREFIX  # "generation_tracking"

"""
Takes a duckdb file and partitions the files out to parquet files
for GitHub Pages consumption.
"""

logger = logging.getLogger(__name__)

GENERATION_TRACKING_PREFIX = "generation_tracking"

@dataclass(frozen=True)
class TableExportConfig:
    name: str
    partition_col: str | None
    sort_cols: list[str]
    select_expr: str = "*"

TABLE_CONFIG = [
    TableExportConfig(name="local_ocdids", partition_col="state", sort_cols=["state", "id"]),
    TableExportConfig(
        name="master_ocdids", partition_col="state", sort_cols=["state"],
        select_expr="*, regexp_extract(id, 'state:([a-z]{2})', 1) AS state",
    ),
    TableExportConfig(name="ocdid_uuid_lookup", partition_col="state", sort_cols=["state", "ocdid"]),
    TableExportConfig(name="local_orphans", partition_col="state", sort_cols=["state", "id"]),
    TableExportConfig(name="master_orphans", partition_col=None, sort_cols=["id"]),
]

def export_single(conn: duckdb.DuckDBPyConnection, cfg: TableExportConfig, out_dir: str) -> dict:
    file_name = f"{cfg.name}.parquet"
    file_path = Path(out_dir) / file_name
    order_by = ", ".join(cfg.sort_cols)

    conn.execute(
        f"COPY (SELECT {cfg.select_expr} FROM {cfg.name} ORDER BY {order_by}) "
        f"TO '{file_path}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )

    row_count = conn.execute(f"SELECT COUNT(*) FROM {cfg.name}").fetchone()[0]
    return {
        "name": cfg.name,
        "file": file_name,
        "rows": row_count,
        "bytes": file_path.stat().st_size,
    }

def export_partitioned(conn: duckdb.DuckDBPyConnection, cfg: TableExportConfig, out_dir: str) -> dict:
    table_dir = Path(out_dir) / cfg.name
    order_by = ", ".join(cfg.sort_cols)

    conn.execute(
        f"COPY (SELECT {cfg.select_expr} FROM {cfg.name} ORDER BY {order_by}) "
        f"TO '{table_dir}' (FORMAT PARQUET, PARTITION_BY ({cfg.partition_col}), "
        f"FILENAME_PATTERN 'data_{{i}}', OVERWRITE_OR_IGNORE)"
    )

    files = {}
    total_bytes = 0
    for parquet_file in sorted(table_dir.rglob("*.parquet")):
        partition_value = parquet_file.parent.name.split("=", 1)[1]
        files[partition_value] = str(parquet_file.relative_to(out_dir))
        total_bytes += parquet_file.stat().st_size

    row_count = conn.execute(f"SELECT COUNT(*) FROM {cfg.name}").fetchone()[0]
    return {
        "name": cfg.name,
        "partitioned_by": cfg.partition_col,
        "rows": row_count,
        "bytes": total_bytes,
        "files": files,
    }

def write_manifest(out_dir: str, entries: list[dict]) -> Path:
    manifest = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "tables": entries,
    }
    manifest_path = Path(out_dir) / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    logger.info(f"Wrote manifest with {len(entries)} table(s) to {manifest_path}")
    return manifest_path

def export_to_parquet(duckdb_path, out_dir):
    conn = duckdb.connect(duckdb_path, read_only=True)
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    try:
        tables = {r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()}

        manifest_tables = []
        for cfg in TABLE_CONFIG:
            if cfg.name not in tables:
                logger.warning(f"Table {cfg.name} not found, skipping")
                continue
            entry = (
                export_partitioned(conn, cfg, out_dir)
                if cfg.partition_col
                else export_single(conn, cfg, out_dir)
            )

            manifest_tables.append(entry)
        tracking_tables = sorted(t for t in tables if t.startswith(GENERATION_TRACKING_PREFIX))
        for table in tracking_tables:
            cfg = TableExportConfig(name=table, partition_col=None, sort_cols=["original_id"])
            entry = export_single(conn, cfg, out_dir)
            manifest_tables.append(entry)
    finally:
        conn.close()

    write_manifest(out_dir, manifest_tables)

if __name__ == "__main__":
    generate_parquet_files()