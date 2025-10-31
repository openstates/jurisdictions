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

    Valid rows are loaded into the main table. Rows with errors (e.g., too many columns)
    are loaded into a quarantine table for later analysis.

    Args:
        csv_path: Path to the CSV file to load
        table_name: Name for the DuckDB table (will be sanitized)
        db_path: Path to the DuckDB database file

    Returns:
        dict with keys: table_name, row_count, column_count, columns, file_path,
        quarantine_table, quarantine_count

    Raises:
        FileNotFoundError: If CSV file doesn't exist
        ValueError: If table_name contains invalid characters
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    # Sanitize table name (alphanumeric and underscore only)
    sanitized_name = "".join(c if c.isalnum() or c == "_" else "_" for c in table_name)

    # Ensure table name is not empty and doesn't start with a number
    if not sanitized_name or not sanitized_name.replace("_", ""):
        raise ValueError(f"Invalid table name: {table_name}")

    # Prepend 't_' if name starts with a digit (SQL requirement)
    if sanitized_name[0].isdigit():
        sanitized_name = "t_" + sanitized_name

    quarantine_name = f"{sanitized_name}_quarantine"

    conn = duckdb.connect(db_path)

    try:
        # First, load all valid rows with ignore_errors=true
        conn.execute(f"""
            CREATE OR REPLACE TABLE {sanitized_name} AS
            SELECT * FROM read_csv_auto('{csv_path}', ignore_errors=true)
        """)

        # Gather statistics for main table
        row_count = conn.execute(f"SELECT COUNT(*) FROM {sanitized_name}").fetchone()[0]
        columns_info = conn.execute(f"DESCRIBE {sanitized_name}").fetchall()
        column_names = [col[0] for col in columns_info]

        # Read the CSV as all text columns to capture problematic rows
        # We'll read with maximum columns to catch rows with extra data
        conn.execute(f"""
            CREATE OR REPLACE TABLE {quarantine_name} AS
            SELECT * FROM read_csv(
                '{csv_path}',
                ALL_VARCHAR=true,
                ignore_errors=false,
                max_line_size=1048576
            )
            EXCEPT
            SELECT * FROM read_csv(
                '{csv_path}',
                ALL_VARCHAR=true,
                ignore_errors=true,
                max_line_size=1048576
            )
        """)

        quarantine_count = conn.execute(f"SELECT COUNT(*) FROM {quarantine_name}").fetchone()[0]

        return {
            "table_name": sanitized_name,
            "row_count": row_count,
            "column_count": len(column_names),
            "columns": column_names,
            "file_path": str(csv_path),
            "quarantine_table": quarantine_name,
            "quarantine_count": quarantine_count
        }
    except Exception as e:
        # If the quarantine approach fails, fall back to basic ignore_errors
        try:
            conn.execute(f"""
                CREATE OR REPLACE TABLE {sanitized_name} AS
                SELECT * FROM read_csv_auto('{csv_path}', ignore_errors=true)
            """)

            row_count = conn.execute(f"SELECT COUNT(*) FROM {sanitized_name}").fetchone()[0]
            columns_info = conn.execute(f"DESCRIBE {sanitized_name}").fetchall()
            column_names = [col[0] for col in columns_info]

            return {
                "table_name": sanitized_name,
                "row_count": row_count,
                "column_count": len(column_names),
                "columns": column_names,
                "file_path": str(csv_path),
                "quarantine_table": None,
                "quarantine_count": 0,
                "error": str(e)
            }
        except Exception as fallback_error:
            raise Exception(f"Failed to load CSV even with error handling: {fallback_error}") from e
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

                # Report on quarantined rows
                if stats.get('quarantine_count', 0) > 0:
                    print(f"  ⚠️  {stats['quarantine_count']:,} problematic rows saved to '{stats['quarantine_table']}'")
                elif stats.get('error'):
                    print(f"  ⚠️  Warning: {stats['error']}")
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
