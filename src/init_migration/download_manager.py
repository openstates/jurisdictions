"""
Business logic for downloading the OCD ID master CSV and loading it into DuckDB.

Responsibilities:
- Build the master CSV URL
- Load CSV bytes into DuckDB persistent tables
- Orchestrate the async download with progress display (see run_downloads())
"""

import tempfile
from logging import getLogger
from pathlib import Path

import duckdb
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from src.init_migration.downloader import AsyncDownloader, DownloaderConfig

logger = getLogger(__name__)

RAW_BASE = "https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/master/identifiers"
MASTER_PATH = "country-us.csv"

DEFAULT_DB_PATH = "data/ocdid_pipeline.duckdb"


class DownloadManager:
    """Fetches the master CSV via AsyncDownloader and loads it into DuckDB."""

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

    def _load_csv_bytes(
        self,
        conn: duckdb.DuckDBPyConnection,
        csv_bytes: bytes,
        query: str,
        params: list | None = None,
    ) -> None:
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
                conn,
                csv_bytes,
                "CREATE OR REPLACE TABLE master_ocdids AS "
                "SELECT * FROM read_csv_auto(?csv_path?, ignore_errors=true)",
            )
            count = conn.execute("SELECT COUNT(*) FROM master_ocdids").fetchone()[0]
            logger.info(f"Loaded {count} rows into master_ocdids")
            return count
        finally:
            conn.close()

    async def run_downloads(
        self,
        force: bool = False,
        show_progress: bool = True,
        downloader_config: DownloaderConfig | None = None,
    ) -> dict:
        """Fetch the master CSV and load it into DuckDB.

        Args:
            force: Bypass ETag cache and re-download everything.
            show_progress: Show rich progress bars (disable for testing).
            downloader_config: Optional custom downloader config.

        Returns:
            dict with stats: files_downloaded, files_cached, files_failed,
            master_rows.
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
        }

        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            disable=not show_progress,
        )
        download_task = progress.add_task("Downloading", total=1)
        load_task = progress.add_task("Loading to DuckDB", total=1)

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
                except Exception as e:  # noqa: BLE001
                    logger.error(f"Failed to download master CSV: {e}")
                    stats["files_failed"] += 1
                progress.advance(download_task)

            # --- Load into DuckDB ---
            if master_bytes:
                stats["master_rows"] = self.load_master_csv(master_bytes)
            progress.advance(load_task)


        return stats
