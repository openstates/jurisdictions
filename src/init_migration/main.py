"""
Main runs the initial ingestion pipeline that generates Divisions and
Jurisdiction objects from our source files and research.
"""

import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse
import duckdb

from downloader import DownloaderConfig, AsyncDownloader


def load_csv_to_duckdb(
    csv_path: Path,
    table_name: str,
    db_path: str = "data.duckdb"
) -> dict:
    """Load CSV into DuckDB and return summary stats

    Args:
        csv_path: Path to the CSV file to load
        table_name: Name for the DuckDB table (will be sanitized)
        db_path: Path to the DuckDB database file

    Returns:
        dict with keys: table_name, row_count, column_count, columns, file_path

    Raises:
        FileNotFoundError: If CSV file doesn't exist
        ValueError: If table_name contains invalid characters
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    # Sanitize table name (alphanumeric and underscore only)
    sanitized_name = "".join(c if c.isalnum() or c == "_" else "_" for c in table_name)
    if not sanitized_name:
        raise ValueError(f"Invalid table name: {table_name}")

    conn = duckdb.connect(db_path)

    try:
        # Create table from CSV using DuckDB's efficient CSV reader
        conn.execute(f"""
            CREATE OR REPLACE TABLE {sanitized_name} AS
            SELECT * FROM read_csv_auto('{csv_path}')
        """)

        # Gather statistics
        row_count = conn.execute(f"SELECT COUNT(*) FROM {sanitized_name}").fetchone()[0]
        columns_info = conn.execute(f"DESCRIBE {sanitized_name}").fetchall()
        column_names = [col[0] for col in columns_info]

        return {
            "table_name": sanitized_name,
            "row_count": row_count,
            "column_count": len(column_names),
            "columns": column_names,
            "file_path": str(csv_path)
        }
    finally:
        conn.close()

async def main() -> None:
    # Build *your* list of URLs here (outside the downloader).
    urls = [
        "https://api.github.com/repos/opencivicdata/ocd-division-ids/contents/identifiers/country-us.csv?ref=master",
    ]

    cfg = DownloaderConfig(
        concurrency=12,
        max_retries=3,
        http2=True,  # auto-disables if 'h2' not installed
        use_github_auth=False,
        etag_cache_path=".etag_cache.json",
    )

    async with AsyncDownloader(cfg) as d:
        blobs = await d.fetch_many(urls)
        sizes = [len(b) if b else 0 for b in blobs]
        print("bytes fetched:", sizes)

        # Updated: strip query params from filename
        url_to_path = {
            u: Path("downloads") / os.path.basename(urlparse(u).path)
            for u in urls
        }
        results = await d.download_many(url_to_path)
        print("downloads:", results)

        # Load each downloaded CSV into DuckDB
        for url, csv_path in url_to_path.items():
            # Use stem of filename as table name (e.g., "country-us" from "country-us.csv")
            table_name = csv_path.stem

            try:
                stats = load_csv_to_duckdb(csv_path, table_name)
                print(f"\n✓ Loaded {stats['row_count']:,} rows into table '{stats['table_name']}'")
                print(f"  Columns ({stats['column_count']}): {', '.join(stats['columns'][:5])}", end="")
                if stats['column_count'] > 5:
                    print(f", ... +{stats['column_count'] - 5} more")
                else:
                    print()
            except Exception as e:
                print(f"\n✗ Failed to load {csv_path}: {e}")
# async def main() -> None:
#     # Build *your* list of URLs here (outside the downloader).
#     urls = [
#         "https://api.github.com/repos/opencivicdata/ocd-division-ids/contents/identifiers/country-us.csv?ref=master",
#     ]
#
#     cfg = DownloaderConfig(
#         concurrency=12,
#         max_retries=3,
#         http2=True,  # auto-disables if 'h2' not installed
#         use_github_auth=False,
#         etag_cache_path=".etag_cache.json",
#     )
#
#     async with AsyncDownloader(cfg) as d:
#         blobs = await d.fetch_many(urls)
#         sizes = [len(b) if b else 0 for b in blobs]
#         print("bytes fetched:", sizes)
#
#         # Updated: strip query params from filename
#         url_to_path = {
#             u: Path("downloads") / os.path.basename(urlparse(u).path)
#             for u in urls
#         }
#         results = await d.download_many(url_to_path)
#         print("downloads:", results)
#         # To force a fresh re-download ignoring ETag/Last-Modified for a single URL:
#         path, status = await d.download_to(
#             urls[0], Path("downloads") / os.path.basename(urlparse(urls[0]).path), force=True
#         )
#         print("forced:", path, status)


if __name__ == "__main__":
    asyncio.run(main())
