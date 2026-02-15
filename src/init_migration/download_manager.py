"""
Business logic for downloading OCD ID CSVs and loading them into DuckDB.

Responsibilities:
- Build URL lists for master and per-state local CSVs
- Load CSV bytes into DuckDB persistent tables
- Orchestrate async downloads with progress display (see run_downloads())
"""

import tempfile
from pathlib import Path

import duckdb
from loguru import logger

RAW_BASE = "https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/master/identifiers"
MASTER_PATH = "country-us.csv"
LOCAL_TEMPLATE = "country-us/state-{state}-local_gov.csv"

DEFAULT_DB_PATH = "data/ocdid_pipeline.duckdb"


class DownloadManager:
    """Builds URLs, fetches CSVs via AsyncDownloader, loads into DuckDB."""

    def __init__(
        self,
        states: list[str],
        db_path: str = DEFAULT_DB_PATH,
    ) -> None:
        self.states = [s.lower() for s in states]
        self.db_path = db_path

    def master_url(self) -> str:
        """Return the URL for the national master CSV."""
        return f"{RAW_BASE}/{MASTER_PATH}"

    def local_urls(self) -> list[str]:
        """Return URLs for each state's local government CSV."""
        return [
            f"{RAW_BASE}/{LOCAL_TEMPLATE.format(state=s)}"
            for s in self.states
        ]

    def all_urls(self) -> list[str]:
        """Return master URL + all local URLs."""
        return [self.master_url()] + self.local_urls()

    def _load_csv_bytes(self, conn: duckdb.DuckDBPyConnection, csv_bytes: bytes, query: str, params: list | None = None) -> None:
        """Write CSV bytes to a temp file, then load via DuckDB read_csv_auto."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp.write(csv_bytes)
            tmp_path = tmp.name
        try:
            if params:
                conn.execute(query.replace("?csv_path?", f"'{tmp_path}'"), params)
            else:
                conn.execute(query.replace("?csv_path?", f"'{tmp_path}'"))
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def load_master_csv(self, csv_bytes: bytes) -> int:
        """Load master CSV bytes into DuckDB master_ocdids table.

        Returns:
            Number of rows loaded.
        """
        conn = duckdb.connect(self.db_path)
        try:
            self._load_csv_bytes(
                conn, csv_bytes,
                "CREATE OR REPLACE TABLE master_ocdids AS "
                "SELECT * FROM read_csv_auto(?csv_path?, ignore_errors=true)"
            )
            count = conn.execute("SELECT COUNT(*) FROM master_ocdids").fetchone()[0]
            logger.info(f"Loaded {count} rows into master_ocdids")
            return count
        finally:
            conn.close()

    def load_local_csv(self, csv_bytes: bytes, state: str) -> int:
        """Load a state's local CSV bytes into DuckDB local_ocdids table.

        Appends rows with a `state` column. Creates the table on first call.

        Returns:
            Number of rows loaded for this state.
        """
        state = state.lower()
        conn = duckdb.connect(self.db_path)
        try:
            # Write bytes to temp file for DuckDB to read
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
                tmp.write(csv_bytes)
                tmp_path = tmp.name
            try:
                # Create table if it doesn't exist
                tables = [row[0] for row in conn.execute("SHOW TABLES").fetchall()]
                if "local_ocdids" not in tables:
                    conn.execute(
                        f"CREATE TABLE local_ocdids AS "
                        f"SELECT *, '{state}' AS state FROM read_csv_auto('{tmp_path}', ignore_errors=true) WHERE 1=0"
                    )

                conn.execute(
                    f"INSERT INTO local_ocdids "
                    f"SELECT *, '{state}' AS state FROM read_csv_auto('{tmp_path}', ignore_errors=true)"
                )
            finally:
                Path(tmp_path).unlink(missing_ok=True)

            count = conn.execute(
                "SELECT COUNT(*) FROM local_ocdids WHERE state = ?", [state]
            ).fetchone()[0]
            logger.info(f"Loaded {count} rows for state '{state}' into local_ocdids")
            return count
        finally:
            conn.close()
