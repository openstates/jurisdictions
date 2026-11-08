"""
Selecting OCD IDs from the master table, UUID generation, and lookup table
management.

Responsibilities:
- Select every master_ocdids row for the requested states, skipping precincts
- Generate UUID5 values from OCD IDs
- Store UUID-OCD-ID lookup table in DuckDB + CSV backup
- Support idempotent re-runs
"""

from dataclasses import dataclass, field
from logging import getLogger
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import duckdb

from src.init_migration.pipeline_models import OCDidIngestResp
from src.models.ocdid import OCDIdParsed
from src.utils.ocdid import ocdid_parser

logger = getLogger(__name__)

DEFAULT_PARQUET_PATH = "data/parquet"
DEFAULT_DB_PATH = "data/ocdid_pipeline.duckdb"
DEFAULT_CSV_BACKUP = "data/ocdid_uuid_lookup.csv"

# States use `state:`, DC uses `district:`, and territories use `territory:`.
STATE_SEGMENTS = ("state", "district", "territory")


@dataclass
class MatchResults:
    """Container for selection results."""

    matched: list[OCDidIngestResp] = field(default_factory=list)
    skipped_precincts: int = 0


class OCDidMatcher:
    """Selects master OCD IDs per state, generates UUIDs, stores lookup."""

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        states: list[str] | None = None,
        csv_backup_path: str = DEFAULT_CSV_BACKUP,
    ) -> None:
        self.db_path = db_path
        self.states = [s.lower() for s in states] if states else []
        self.csv_backup_path = csv_backup_path

    def _state_filter(self) -> tuple[str, list[str]]:
        """Build a WHERE clause matching each state's own row and its children."""
        clauses = []
        params = []
        for state in self.states:
            for segment in STATE_SEGMENTS:
                prefix = f"ocd-division/country:us/{segment}:{state}"
                clauses.append("(id = ? OR id LIKE ?)")
                params.extend([prefix, f"{prefix}/%"])
        if not clauses:
            return "", []
        return "WHERE " + " OR ".join(clauses), params

    def run_matching(self, show_progress: bool = False) -> MatchResults:
        """Select the master rows to generate and store the UUID lookup.

        Args:
            show_progress: Show rich progress bar for matching phase.

        Returns:
            MatchResults with the selected OCDidIngestResp list.
        """
        results = MatchResults()
        conn = duckdb.connect(self.db_path)

        try:
            # The master list is the source of truth; select every row for
            # the requested states.
            where, params = self._state_filter()
            cursor = conn.execute(f"SELECT * FROM master_ocdids {where}", params)
            col_names = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

            for row in rows:
                row_dict = dict(zip(col_names, row))
                ocdid_str = row_dict["id"]

                # Parse OCD ID
                parsed_dict = ocdid_parser(ocdid_str)

                # Voting precincts are not governments; skip them.
                if "precinct" in parsed_dict:
                    results.skipped_precincts += 1
                    continue

                parsed = OCDIdParsed(
                    base_ocdid=ocdid_str,
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

            logger.info(
                "Selected master records",
                extra={
                    "selected": len(results.matched),
                    "skipped_precincts": results.skipped_precincts,
                    "states": self.states,
                },
            )

            # --- Store lookup table ---
            self._store_lookup_table(conn, results)

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
