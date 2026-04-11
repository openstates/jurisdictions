"""
Matching OCD IDs between local and master tables, UUID generation, and
lookup table management.

Responsibilities:
- Exact join of local_ocdids against master_ocdids on `id` column
- Classify records: match, local orphan, master orphan
- Generate UUID5 values from OCD IDs
- Store UUID-OCD-ID lookup table in DuckDB + CSV backup
- Support idempotent re-runs
"""

from dataclasses import dataclass, field
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import duckdb
from loguru import logger

from src.init_migration.pipeline_models import OCDidIngestResp
from src.models.ocdid import OCDidParsed
from src.utils.ocdid import ocdid_parser

DEFAULT_DB_PATH = "data/ocdid_pipeline.duckdb"
DEFAULT_CSV_BACKUP = "data/ocdid_uuid_lookup.csv"


@dataclass
class MatchResults:
    """Container for matching results."""
    matched: list[OCDidIngestResp] = field(default_factory=list)
    local_orphans: list[dict] = field(default_factory=list)
    master_orphans: list[dict] = field(default_factory=list)


class OCDidMatcher:
    """Matches local OCD IDs against master, generates UUIDs, stores lookup."""

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        states: list[str] | None = None,
        csv_backup_path: str = DEFAULT_CSV_BACKUP,
    ) -> None:
        self.db_path = db_path
        self.states = [s.lower() for s in states] if states else []
        self.csv_backup_path = csv_backup_path

    def run_matching(self, show_progress: bool = False) -> MatchResults:
        """Run the full matching pipeline.

        Args:
            show_progress: Show rich progress bar for matching phase.

        Returns:
            MatchResults with matched OCDidIngestResp list and orphan lists.
        """
        results = MatchResults()
        conn = duckdb.connect(self.db_path)

        try:
            # Build state filter clause
            if self.states:
                placeholders = ", ".join(f"'{s}'" for s in self.states)
                state_filter = f"WHERE l.state IN ({placeholders})"
            else:
                state_filter = ""

            # --- Matched records: inner join ---
            # Select all master columns (m.*) because the master list is the
            # source of truth. Local state files are only used to cross-check
            # that the national list has all state OIDs and to detect drift.
            # l.state is included for filtering/grouping but not in raw_record.
            cursor = conn.execute(f"""
                SELECT m.*, l.state AS _local_state
                FROM local_ocdids l
                INNER JOIN master_ocdids m ON l.id = m.id
                {state_filter}
            """)
            col_names = [desc[0] for desc in cursor.description]
            matched_rows = cursor.fetchall()

            for row in matched_rows:
                row_dict = dict(zip(col_names, row))
                row_dict.pop("_local_state", None)
                ocdid_str = row_dict["id"]

                # Parse OCD ID
                parsed_dict = ocdid_parser(ocdid_str)
                parsed = OCDidParsed(
                    raw_ocdid=ocdid_str,
                    country=parsed_dict.get("country", "us"),
                    state=parsed_dict.get("state"),
                    county=parsed_dict.get("county"),
                    place=parsed_dict.get("place"),
                )

                # Generate UUID5 from OCD ID
                det_id = uuid5(NAMESPACE_URL, ocdid_str)

                resp = OCDidIngestResp(
                    uuid=det_id,
                    ocdid=parsed,
                    raw_record=row_dict,
                )
                results.matched.append(resp)

            logger.info(f"Matched {len(results.matched)} records")

            # --- Local orphans: left anti-join ---
            local_orphan_rows = conn.execute(f"""
                SELECT l.id, l.name, l.state
                FROM local_ocdids l
                LEFT JOIN master_ocdids m ON l.id = m.id
                WHERE m.id IS NULL
                {"AND l.state IN (" + placeholders + ")" if self.states else ""}
            """).fetchall()

            orphan_cols = ["id", "name", "state"]
            results.local_orphans = [
                dict(zip(orphan_cols, row)) for row in local_orphan_rows
            ]
            if results.local_orphans:
                logger.warning(f"Found {len(results.local_orphans)} local orphan(s)")

            # --- Master orphans: right anti-join (for selected states) ---
            if self.states:
                state_patterns = " OR ".join(
                    f"m.id LIKE '%/state:{s}/%'" for s in self.states
                )
                master_orphan_rows = conn.execute(f"""
                    SELECT m.id, m.name
                    FROM master_ocdids m
                    LEFT JOIN local_ocdids l ON m.id = l.id
                    WHERE l.id IS NULL AND ({state_patterns})
                """).fetchall()
            else:
                master_orphan_rows = conn.execute("""
                    SELECT m.id, m.name
                    FROM master_ocdids m
                    LEFT JOIN local_ocdids l ON m.id = l.id
                    WHERE l.id IS NULL
                """).fetchall()

            master_orphan_cols = ["id", "name"]
            results.master_orphans = [
                dict(zip(master_orphan_cols, row)) for row in master_orphan_rows
            ]
            if results.master_orphans:
                logger.warning(
                    f"Found {len(results.master_orphans)} master orphan(s)"
                )

            # --- Store lookup table ---
            self._store_lookup_table(conn, results)

            # --- Store orphan tables ---
            self._store_orphan_tables(conn, results)

        finally:
            conn.close()

        return results

    def _store_lookup_table(
        self, conn: duckdb.DuckDBPyConnection, results: MatchResults
    ) -> None:
        """Create/update UUID-OCD-ID lookup table in DuckDB and CSV backup."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ocdid_uuid_lookup (
                uuid TEXT,
                ocdid TEXT,
                state TEXT,
                name TEXT
            )
        """)

        for resp in results.matched:
            conn.execute(
                """
                INSERT INTO ocdid_uuid_lookup (uuid, ocdid, state, name)
                SELECT ?, ?, ?, ?
                WHERE NOT EXISTS (
                    SELECT 1 FROM ocdid_uuid_lookup WHERE ocdid = ?
                )
                """,
                [
                    str(resp.uuid),
                    resp.ocdid.raw_ocdid,
                    resp.ocdid.state or "",
                    resp.raw_record.get("name", ""),
                    resp.ocdid.raw_ocdid,
                ],
            )

        # CSV backup
        if self.csv_backup_path:
            Path(self.csv_backup_path).parent.mkdir(parents=True, exist_ok=True)
            conn.execute(
                f"COPY ocdid_uuid_lookup TO '{self.csv_backup_path}' (HEADER, DELIMITER ',')"
            )
            logger.info(f"CSV backup written to {self.csv_backup_path}")

    def _store_orphan_tables(
        self, conn: duckdb.DuckDBPyConnection, results: MatchResults
    ) -> None:
        """Store orphan records in DuckDB quarantine tables."""
        # Local orphans
        conn.execute("""
            CREATE TABLE IF NOT EXISTS local_orphans (
                id TEXT, name TEXT, state TEXT
            )
        """)
        for orphan in results.local_orphans:
            conn.execute(
                "INSERT INTO local_orphans VALUES (?, ?, ?)",
                [orphan["id"], orphan.get("name", ""), orphan.get("state", "")],
            )

        # Master orphans
        conn.execute("""
            CREATE TABLE IF NOT EXISTS master_orphans (
                id TEXT, name TEXT
            )
        """)
        for orphan in results.master_orphans:
            conn.execute(
                "INSERT INTO master_orphans VALUES (?, ?)",
                [orphan["id"], orphan.get("name", "")],
            )
