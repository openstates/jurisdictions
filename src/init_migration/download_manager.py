"""
Business logic for downloading OCD ID CSVs and loading them into DuckDB.

Responsibilities:
- Build URL lists for master and per-state local CSVs
- Load CSV bytes into DuckDB persistent tables
- Orchestrate async downloads with progress display (see run_downloads())
"""

import asyncio
import tempfile
from pathlib import Path

import duckdb
from loguru import logger
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

from src.init_migration.downloader import AsyncDownloader, DownloaderConfig

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

    async def run_downloads(
        self,
        force: bool = False,
        show_progress: bool = True,
        downloader_config: DownloaderConfig | None = None,
    ) -> dict:
        """Fetch all CSVs concurrently and load into DuckDB.

        Args:
            force: Bypass ETag cache and re-download everything.
            show_progress: Show rich progress bars (disable for testing).
            downloader_config: Optional custom downloader config.

        Returns:
            dict with stats: files_downloaded, files_cached, files_failed,
            master_rows, local_rows.
        """
        cfg = downloader_config or DownloaderConfig(
            concurrency=12,
            max_retries=3,
            http2=True,
            etag_cache_path=".etag_cache.json",
        )

        stats = {
            "files_downloaded": 0,
            "files_cached": 0,
            "files_failed": 0,
            "master_rows": 0,
            "local_rows": 0,
        }

        total_files = 1 + len(self.states)
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            disable=not show_progress,
        )
        download_task = progress.add_task("Downloading", total=total_files)
        load_task = progress.add_task("Loading to DuckDB", total=total_files)

        with progress:
            async with AsyncDownloader(cfg) as downloader:
                # --- Download master ---
                master_bytes = None
                try:
                    master_bytes = await downloader.fetch_bytes(
                        self.master_url(), force=force
                    )
                    if master_bytes is None:
                        logger.info("Master CSV unchanged (ETag cache hit)")
                        stats["files_cached"] += 1
                    else:
                        stats["files_downloaded"] += 1
                except Exception as e:
                    logger.error(f"Failed to download master CSV: {e}")
                    stats["files_failed"] += 1
                progress.advance(download_task)

                # --- Download locals concurrently ---
                local_results: dict[str, bytes | None] = {}
                local_urls = self.local_urls()

                async def fetch_local(state: str, url: str):
                    try:
                        data = await downloader.fetch_bytes(url, force=force)
                        if data is None:
                            logger.info(f"Local CSV for {state} unchanged (cache hit)")
                            stats["files_cached"] += 1
                        else:
                            stats["files_downloaded"] += 1
                        local_results[state] = data
                    except Exception as e:
                        logger.warning(f"Failed to download local CSV for {state}: {e}")
                        stats["files_failed"] += 1
                        local_results[state] = None
                    progress.advance(download_task)

                await asyncio.gather(
                    *(fetch_local(s, u) for s, u in zip(self.states, local_urls))
                )

            # --- Load into DuckDB ---
            if master_bytes:
                stats["master_rows"] = self.load_master_csv(master_bytes)
            progress.advance(load_task)

            for state in self.states:
                csv_bytes = local_results.get(state)
                if csv_bytes:
                    rows = self.load_local_csv(csv_bytes, state)
                    stats["local_rows"] += rows
                progress.advance(load_task)

        return stats
