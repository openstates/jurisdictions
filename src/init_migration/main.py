"""
Main runs the initial ingestion pipeline that generates Divisions and
Jurisdiction objects from our source files and research.
"""

import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse

from downloader import DownloaderConfig, AsyncDownloader


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
        # To force a fresh re-download ignoring ETag/Last-Modified for a single URL:
        path, status = await d.download_to(
            urls[0], Path("downloads") / os.path.basename(urlparse(urls[0]).path), force=True
        )
        print("forced:", path, status)


if __name__ == "__main__":
    asyncio.run(main())
