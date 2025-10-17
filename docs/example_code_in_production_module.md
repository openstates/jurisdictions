# Recommendation: Example Code in a Production Module

Summary
- downloader.py contains example/demo orchestration code (`main()` and `if __name__ == "__main__": asyncio.run(main())`).
- Keeping runnable examples in a production module is an anti-pattern that can hurt clarity, testing, and packaging.

Why move it
- Import side effects: Even with a __main__ guard, extra imports and module-level code can slow or complicate imports.
- Separation of concerns: The module should expose functionality; examples belong in examples/ or scripts/.
- Testability: Test discovery and coverage are cleaner when modules have no demo code.
- Packaging/CLI: Installing the package shouldn’t ship demo entry points unintentionally.
- Readability: Junior developers can more easily see the module’s single responsibility.

Recommended destinations
- examples/download_example.py for runnable examples.
- src/init_migration/__main__.py for “python -m src.init_migration” demos.
- scripts/ for project-local operational scripts (not packaged).

Proposed structure
- Move the example `main()` into a separate example file:
  - examples/download_example.py
  - Keep it minimal and focused on usage.

Example of extracted file (sketch)
````python
# examples/download_example.py
import asyncio
from pathlib import Path
from src.init_migration.downloader import AsyncDownloader, DownloaderConfig

async def main() -> None:
    urls = [
        "https://api.github.com/repos/opencivicdata/ocd-division-ids/contents/identifiers/country-us.csv?ref=master",
    ]
    cfg = DownloaderConfig(
        concurrency=12,
        max_retries=3,
        http2=True,
        use_github_auth=False,
        etag_cache_path=".etag_cache.json",
    )
    async with AsyncDownloader(cfg) as d:
        blobs = await d.fetch_many(urls)
        print("bytes fetched:", [len(b) if b else 0 for b in blobs])

        url_to_path = {u: Path("downloads") / Path(u).name for u in urls}
        results = await d.download_many(url_to_path)
        print("downloads:", results)

if __name__ == "__main__":
    asyncio.run(main())