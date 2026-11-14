import logging
from dataclasses import dataclass
from pathlib import Path

import duckdb
from duckdb.sqltypes import VARCHAR

from src.models.ocdid import OCDIdParsed

"""
Exports pipeline DuckDB tables to state-partitioned Parquet under data/parquet/.
A run writes only its own states' folders (plus the stateless `state=` folder),
so populate PRs for different states never change the same file. The site's
one-file-per-table copy and manifest.json are built at deploy time by
src/utils/build_pages_data.py.
"""

logger = logging.getLogger(__name__)

GENERATION_TRACKING_PREFIX = "generation_tracking"

STATELESS = ""
OCDID_STATE_SQL_FUNCTION = "ocdid_state"


def ocdid_state(raw_ocdid: str) -> str:
    """The parser's state code (DC and territories included); '' when there is none."""
    return OCDIdParsed.parse_ocdid(raw_ocdid).state or STATELESS


@dataclass(frozen=True)
class TableExportConfig:
    name: str
    sort_cols: list[str]
    select_expr: str = "*"
    partition_col: str = "state"


def with_state_from(id_col: str) -> str:
    return f"*, {OCDID_STATE_SQL_FUNCTION}({id_col}) AS state"


TABLE_CONFIG = [
    TableExportConfig(
        name="master_ocdids",
        sort_cols=["state", "id"],
        select_expr=with_state_from("id"),
    ),
    TableExportConfig(name="local_ocdids", sort_cols=["state", "id"]),
    TableExportConfig(name="ocdid_uuid_lookup", sort_cols=["state", "ocdid"]),
    TableExportConfig(name="local_orphans", sort_cols=["state", "id"]),
    TableExportConfig(
        name="master_orphans",
        sort_cols=["state", "id"],
        select_expr=with_state_from("id"),
    ),
]


def tracking_config(table: str) -> TableExportConfig:
    return TableExportConfig(
        name=table,
        sort_cols=["state", "original_id"],
        select_expr=with_state_from("original_id"),
    )


def sql_string_list(values: list[str]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


def export_partitioned(
    conn: duckdb.DuckDBPyConnection,
    cfg: TableExportConfig,
    out_dir: str,
    states: list[str],
) -> None:
    """Write `<out_dir>/<table>/state=xx/` for the run's states and the stateless rows.

    Folders for other states are left exactly as committed.
    """
    table_dir = Path(out_dir) / cfg.name
    order_by = ", ".join(cfg.sort_cols)
    wanted = sql_string_list([*states, STATELESS])

    conn.execute(
        f"COPY (SELECT * FROM (SELECT {cfg.select_expr} FROM {cfg.name}) "
        f"WHERE {cfg.partition_col} IN ({wanted}) ORDER BY {order_by}) "
        f"TO '{table_dir}' (FORMAT PARQUET, PARTITION_BY ({cfg.partition_col}), "
        f"FILENAME_PATTERN 'data_{{i}}', OVERWRITE_OR_IGNORE)"
    )
    logger.info(
        "Exported table to Parquet",
        extra={"table": cfg.name, "states": states, "out_dir": str(table_dir)},
    )


def export_to_parquet(duckdb_path: str, out_dir: str, states: list[str]) -> None:
    conn = duckdb.connect(duckdb_path, read_only=True)
    conn.create_function(OCDID_STATE_SQL_FUNCTION, ocdid_state, [VARCHAR], VARCHAR)
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }

        for cfg in TABLE_CONFIG:
            if cfg.name not in tables:
                logger.warning("Table not found, skipping", extra={"table": cfg.name})
                continue
            export_partitioned(conn, cfg, out_dir, states)

        tracking_tables = sorted(
            t for t in tables if t.startswith(GENERATION_TRACKING_PREFIX)
        )
        for table in tracking_tables:
            export_partitioned(conn, tracking_config(table), out_dir, states)
    finally:
        conn.close()
