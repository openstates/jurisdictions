from __future__ import annotations
import asyncio
import json
import os
import random
from pathlib import Path
from typing import Iterable, Optional, Mapping


import httpx
import importlib.util

from loguru import logger

# Configure Loguru
logger.add(
    "downloader.log",
    rotation="1 MB",          # rotate logs when they reach 1MB
    retention=10,             #  keep up to 10 files
    enqueue=True,             # allow async logging
    backtrace=True,           # include tracebacks in logs
    diagnose=True,            # log errors when they happen
    level="DEBUG",
)

# Optionally load environment variables from a .env file if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()  # This will load variables from a .env file into os.environ
except ImportError:
    # If python-dotenv is not installed, continue silently
    pass

# -----------------------------
# Config
# -----------------------------
class DownloaderConfig:
    def __init__(
        self,
        *,
        concurrency: int = 12,
        max_retries: int = 3,
        timeout: httpx.Timeout = httpx.Timeout(connect=10, read=30, write=10, pool=10),
        http2: bool = True,
        use_github_auth: bool = False,
        github_token: Optional[str] = None,
        etag_cache_path: str | os.PathLike | None = None,
        user_agent: str = "ocd-downloader/1.0 (+https://yourdomain.example)",
    ) -> None:
        self.concurrency = concurrency
        self.max_retries = max_retries
        self.timeout = timeout
        self.http2 = http2
        self.use_github_auth = use_github_auth
        self.github_token = (github_token or os.getenv("GITHUB_TOKEN")) if use_github_auth else None
        self.etag_cache_path = Path(etag_cache_path) if etag_cache_path else None
        self.user_agent = user_agent

_DEF_HEADERS = {"Accept": "*/*"}

def _http2_available() -> bool:
    return importlib.util.find_spec("h2") is not None

# -----------------------------
# Core: a downloader-only async client
# -----------------------------
class AsyncDownloader:
    """
    Async HTTP downloader with:
      - connection pooling, optional HTTP/2 (auto-disabled if h2 not installed)
      - bounded concurrency
      - retries with exponential backoff + jitter
      - ETag/Last-Modified conditional requests via a JSON cache

    Intentionally does NOT know which URLs to fetch or how to parse them.
    """

    def __init__(self, config: DownloaderConfig | None = None) -> None:
        self.cfg = config or DownloaderConfig()
        self._client: Optional[httpx.AsyncClient] = None
        self._sem = asyncio.Semaphore(self.cfg.concurrency)
        self._etag_cache: dict[str, dict[str, str]] = {}

    async def __aenter__(self) -> "AsyncDownloader":
        headers = dict(_DEF_HEADERS)
        headers["User-Agent"] = self.cfg.user_agent
        if self.cfg.use_github_auth and self.cfg.github_token:
            # GitHub raw may ignore Authorization; harmless if set.
            headers["Authorization"] = f"Bearer {self.cfg.github_token}"

        use_http2 = self.cfg.http2 and _http2_available()
        self._client = httpx.AsyncClient(
            headers=headers,
            timeout=self.cfg.timeout,
            http2=use_http2,
            follow_redirects=True,
        )

        if self.cfg.etag_cache_path and self.cfg.etag_cache_path.is_file():
            try:
                self._etag_cache = json.loads(self.cfg.etag_cache_path.read_text("utf-8"))
            except Exception:
                self._etag_cache = {}
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()
        if self.cfg.etag_cache_path:
            try:
                self.cfg.etag_cache_path.write_text(json.dumps(self._etag_cache), encoding="utf-8")
            except Exception:
                pass

    async def fetch_bytes(self, url: str, *, force: bool = False) -> Optional[bytes]:
        """
        Return response bytes, or None if 304 due to conditional request.

        Args:
        url: The URL to fetch.
        force: If True, bypass ETag/Last-Modified conditional headers and force a fresh fetch.
        """
        assert self._client is not None, "Use 'async with AsyncDownloader(...)'"

        backoff = 0.5
        req_headers: dict[str, str] = {}
        cache = self._etag_cache.get(url)
        if cache and not force:
            if etag := cache.get("etag"):
                req_headers["If-None-Match"] = etag
            if lm := cache.get("last_modified"):
                req_headers["If-Modified-Since"] = lm

        for attempt in range(self.cfg.max_retries + 1):
            try:
                async with self._sem:
                    resp = await self._client.get(url, headers=req_headers)
                if resp.status_code == 304:
                    logger.info(f"Unchanged (304) for {url}")
                    return None
                resp.raise_for_status()

                # Guard accidental HTML
                ctype = resp.headers.get("content-type", "").lower()
                head = resp.content[:64].lstrip().lower()
                if (
                    "html" in ctype
                    or head.startswith(b"<!doctype html")
                    or head.startswith(b"<html")
                ):
                    raise ValueError(f"Unexpected HTML from {url}")

                # Save validators (works for both raw and API endpoints)
                etag = resp.headers.get("etag")
                last_mod = resp.headers.get("last-modified")
                if etag or last_mod:
                    self._etag_cache[url] = {
                        "etag": etag or "",
                        "last_modified": last_mod or "",
                    }

                # If this is the GitHub API (JSON envelope), decode base64 content
                # or fall back to the provided download_url if present
                try:
                    is_api_json = ("application/json" in ctype) or (
                        "api.github.com" in url
                    )
                    if is_api_json:
                        data = resp.json()
                        if isinstance(data, dict):
                            # Decode base64 content if provided
                            content_field = data.get("content")
                            encoding = data.get("encoding")
                            if content_field is not None and encoding == "base64":
                                import base64

                                # GitHub may insert newlines in base64; remove whitespace before decoding
                                b = base64.b64decode(
                                    str(content_field).encode("utf-8"), validate=False
                                )
                                return b
                            # Else try download_url as a fallback (one extra request)
                            dl = data.get("download_url")
                            if dl:
                                async with self._sem:
                                    dl_resp = await self._client.get(dl)
                                dl_resp.raise_for_status()
                                dl_ctype = dl_resp.headers.get(
                                    "content-type", ""
                                ).lower()
                                dl_head = dl_resp.content[:64].lstrip().lower()
                                if (
                                    "html" in dl_ctype
                                    or dl_head.startswith(b"<!doctype html")
                                    or dl_head.startswith(b"<html")
                                ):
                                    raise ValueError(f"Unexpected HTML from {dl}")
                                return dl_resp.content
                except (ValueError, json.JSONDecodeError) as e:
                    # Not JSON or unexpected payload; fall through to raw content
                    logger.debug(f'Falling back to raw content for {url} ({type(e).__name__}: {e})')

                # Default: return raw bytes (raw.githubusercontent.com, etc.)
                logger.success(f"Downloaded {url} ({len(resp.content)} bytes)")
                return resp.content

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.PoolTimeout) as e:
                if attempt >= self.cfg.max_retries:
                    logger.error(
                        f"Network error for {url} after {attempt + 1} attempt(s); giving up: {type(e).__name__}: {e}"
                    )
                    raise
                logger.warning(
                    f"Transient network error for {url} on attempt {attempt + 1}; will retry: {type(e).__name__}: {e}"
                )
                await asyncio.sleep(backoff + random.random() * 0.25)
                backoff = min(4.0, backoff * 2)
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status in (429,) or 500 <= status < 600:
                    retry_after = e.response.headers.get("Retry-After")
                    delay = (int(retry_after) if retry_after and retry_after.isdigit() else backoff)
                    if attempt < self.cfg.max_retries:
                        logger.warning(
                            f"HTTP {status} for {url} on attempt {attempt + 1}; retrying after {delay:.2f}s"
                        )
                        await asyncio.sleep(delay + random.random() * 0.25)
                        backoff = min(8.0, backoff * 2)
                        continue
                    logger.error(
                        f"HTTP {status} for {url} after {attempt + 1} attempt(s); giving up"
                    )
                else:
                    logger.error(f"HTTP {status} for {url}; not retryable: {e}")
                raise

    async def download_to(self, url: str, dest: os.PathLike | str, *, overwrite: bool = True, force: bool = False) -> tuple[Path, str]:
        """
        Write to dest path.

        Returns (path, status) where status is 'downloaded'|'unchanged'|'skipped'.

        Args:
            url: The URL to download.
            dest: Destination path on disk.
            overwrite: If False and dest exists, skip writing.
            force: If True, bypass conditional requests and force a fresh fetch.
        """
        path = Path(dest)
        if path.exists() and not overwrite:
            return path, "skipped"
        content = await self.fetch_bytes(url, force=force)
        if content is None:
            return path, "unchanged"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path, "downloaded"

    async def fetch_many(self, urls: Iterable[str]) -> list[Optional[bytes]]:
        return await asyncio.gather(*(self.fetch_bytes(u) for u in urls))

    async def download_many(self, url_to_path: Mapping[str, os.PathLike | str]) -> list[tuple[Path, str]]:
        coros = [self.download_to(u, p) for u, p in url_to_path.items()]
        return await asyncio.gather(*coros)


# -----------------------------
# Example orchestration
# -----------------------------
async def main() -> None:
    # Build *your* list of URLs here (outside the downloader).
    # urls = [
    #     "https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/master/identifiers/country-us.csv",
    # ]
    urls = [
        "https://api.github.com/repos/opencivicdata/ocd-division-ids/contents/identifiers/country-us.csv?ref=master",
    ]

    cfg = DownloaderConfig(
        concurrency=12,
        max_retries=3,
        http2=True,                      # auto-disables if 'h2' not installed
        use_github_auth=False,
        etag_cache_path=".etag_cache.json",
    )

    async with AsyncDownloader(cfg) as d:
        blobs = await d.fetch_many(urls)
        sizes = [len(b) if b else 0 for b in blobs]
        print("bytes fetched:", sizes)

        url_to_path = {u: Path("downloads") / Path(u).name for u in urls}
        results = await d.download_many(url_to_path)
        print("downloads:", results)
        # To force a fresh re-download ignoring ETag/Last-Modified for a single URL:
        path, status = await d.download_to(urls[0], Path("downloads") / Path(urls[0]).name, force=True)
        print("forced:", path, status)


if __name__ == "__main__":
    asyncio.run(main())