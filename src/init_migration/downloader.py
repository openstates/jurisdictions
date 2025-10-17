from __future__ import annotations
import asyncio
import base64
import importlib.util
import json
import os
import random
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable, Mapping, Optional, Literal

import httpx
from loguru import logger

# Import custom errors from parent package
from src.errors import (
    APIRetryError,
    UnexpectedContentError,
    DownloaderNotInitializedError,
    CacheError,
)

# Provide an optional helper to configure logging externally (no import-time side effects)

def configure_downloader_logging(
    *,
    sink: str | os.PathLike = "downloader.log",
    level: str = "DEBUG",
    rotation: str = "1 MB",
    retention: int | str = 10,
) -> None:
    """Optionally configure Loguru logging for the downloader module.

    This avoids adding handlers at import-time. Call from application code if desired.
    """
    logger.add(
        str(sink),
        rotation=rotation,
        retention=retention,
        enqueue=True,
        backtrace=True,
        diagnose=True,
        level=level,
    )


# -----------------------------
# Config
# -----------------------------
class DownloaderConfig:
    """
    Configuration settings for AsyncDownloader.

    Attributes:
        concurrency: Maximum number of concurrent downloads (default: 12)
        max_retries: Number of retry attempts for failed requests (default: 3)
        timeout: HTTP timeout settings for connect/read/write/pool operations
        http2: Enable HTTP/2 protocol (auto-disabled if h2 package not installed)
        use_github_auth: Whether to authenticate with GitHub API
        github_token: GitHub personal access token (reads from GITHUB_TOKEN env var if not provided)
        etag_cache_path: Path to JSON file for caching ETag/Last-Modified headers
        user_agent: User-Agent header value for HTTP requests
    """

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
        initial_backoff: float = 0.5,
        max_backoff: float = 8.0,
    ) -> None:
        self.concurrency = concurrency
        self.max_retries = max_retries
        self.timeout = timeout
        self.http2 = http2
        self.use_github_auth = use_github_auth
        self.github_token = (
            (github_token or os.getenv("GITHUB_TOKEN")) if use_github_auth else None
        )
        self.etag_cache_path = Path(etag_cache_path) if etag_cache_path else None
        self.user_agent = user_agent
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff


DEFAULT_HEADERS = {"Accept": "*/*"}

from urllib.parse import urlparse

from typing import Literal as _LiteralForAlias
DownloadStatus = _LiteralForAlias["downloaded", "unchanged", "skipped"]

def _is_github_host(host: str | None) -> bool:
    return host in {"api.github.com", "raw.githubusercontent.com"}


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
      - retries with exponential backoff and jitter
      - ETag/Last-Modified conditional requests via a JSON cache

    Intentionally does NOT know which URLs to fetch or how to parse them.
    """

    def __init__(self, config: DownloaderConfig | None = None) -> None:
        self.cfg = config or DownloaderConfig()
        self._client: Optional[httpx.AsyncClient] = None
        self._sem = asyncio.Semaphore(self.cfg.concurrency)
        self._etag_cache: dict[str, dict[str, str]] = {}

    async def __aenter__(self) -> "AsyncDownloader":
        headers = dict(DEFAULT_HEADERS)
        headers["User-Agent"] = self.cfg.user_agent

        use_http2 = self.cfg.http2 and _http2_available()
        limits = httpx.Limits(
            max_connections=self.cfg.concurrency,
            max_keepalive_connections=min(10, self.cfg.concurrency),
        )
        self._client = httpx.AsyncClient(
            headers=headers,
            timeout=self.cfg.timeout,
            http2=use_http2,
            follow_redirects=True,
            limits=limits,
        )

        if self.cfg.etag_cache_path and self.cfg.etag_cache_path.is_file():
            try:
                cache_content = self.cfg.etag_cache_path.read_text("utf-8")
                self._etag_cache = json.loads(cache_content)
                logger.debug(
                    f"Loaded ETag cache from {self.cfg.etag_cache_path} ({len(self._etag_cache)} entries)"
                )
            except json.JSONDecodeError as e:
                # Corrupted cache file - this is a problem we should raise
                raise CacheError(
                    f"ETag cache file is corrupted and cannot be parsed as JSON: {e}",
                    cache_path=str(self.cfg.etag_cache_path),
                ) from e
            except (OSError, IOError) as e:
                # File read error - warn but continue with empty cache
                logger.warning(
                    f"Failed to read ETag cache from {self.cfg.etag_cache_path}: {e}. "
                    "Starting with empty cache."
                )
                self._etag_cache = {}
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()

        if self.cfg.etag_cache_path:
            try:
                # Ensure parent directory exists
                self.cfg.etag_cache_path.parent.mkdir(parents=True, exist_ok=True)

                # Atomic write: write to a temp file, then replace
                cache_json = json.dumps(self._etag_cache, separators=(",", ":"))
                tmp_path = self.cfg.etag_cache_path.with_suffix(
                    self.cfg.etag_cache_path.suffix + ".tmp"
                )
                tmp_path.write_text(cache_json, encoding="utf-8")
                os.replace(tmp_path, self.cfg.etag_cache_path)
                logger.debug(
                    f"Saved ETag cache to {self.cfg.etag_cache_path} ({len(self._etag_cache)} entries)"
                )
            except (OSError, IOError) as e:
                # File write error during cleanup
                # Log as error but don't raise - we're in cleanup phase
                logger.error(
                    f"Failed to save ETag cache to {self.cfg.etag_cache_path}: {e}. "
                    "Cache will not be persisted for next run."
                )
            except Exception as e:
                # Unexpected error (e.g., serialization issue)
                logger.error(
                    f"Unexpected error while saving ETag cache: {type(e).__name__}: {e}. "
                    "Cache will not be persisted for next run."
                )

    async def fetch_bytes(self, url: str, *, force: bool = False) -> Optional[bytes]:
        """
        Return response bytes, or None if 304 due to conditional request.

        Args:
        url: The URL to fetch.
        force: If True, ignore cached ETag/Last-Modified values and always fetch fresh content,
               even if the file hasn't changed on the server. Use this when you need to ensure
               the latest data regardless of cache state.

        Raises:
        DownloaderNotInitializedError: If called outside async context manager.
        UnexpectedContentError: If HTML is returned when data was expected.
        APIRetryError: If max retries exhausted for retryable errors.
        httpx.HTTPStatusError: For non-retryable HTTP errors (4xx except 429).
        """
        if self._client is None:
            raise DownloaderNotInitializedError()

        backoff = float(self.cfg.initial_backoff)
        req_headers: dict[str, str] = {}
        cache = self._etag_cache.get(url)
        if cache and not force:
            if etag := cache.get("etag"):
                req_headers["If-None-Match"] = etag
            if lm := cache.get("last_modified"):
                req_headers["If-Modified-Since"] = lm

        for attempt in range(self.cfg.max_retries + 1):
            try:
                # Add GitHub Authorization per-request only for GitHub hosts
                if self.cfg.use_github_auth and self.cfg.github_token:
                    host = urlparse(url).hostname
                    if _is_github_host(host):
                        req_headers["Authorization"] = f"Bearer {self.cfg.github_token}"
                async with self._sem:
                    resp = await self._client.get(url, headers=req_headers)

                # Handle HTTP 304 response
                if resp.status_code == 304:
                    logger.info(f"HTTP 304 for {url}; no new content to download.")
                    return None  # Gracefully return None for 304 response

                resp.raise_for_status()

                # Guard accidental HTML
                if self._is_html_response(
                    resp.content, resp.headers.get("content-type", "")
                ):
                    raise UnexpectedContentError(
                        f"Expected data but received HTML from {url}",
                        url=url,
                        content_type=resp.headers.get("content-type", ""),
                    )

                # Save validators
                etag = resp.headers.get("etag")
                last_mod = resp.headers.get("last-modified")
                if etag or last_mod:
                    self._etag_cache[url] = {
                        "etag": etag or "",
                        "last_modified": last_mod or "",
                    }

                # Decode GitHub API responses or return raw bytes
                content = await self._decode_github_response(resp, url)
                logger.success(f"Downloaded {url} ({len(content)} bytes)")
                return content

            except (
                httpx.ConnectError,
                httpx.ReadTimeout,
                httpx.RemoteProtocolError,
                httpx.PoolTimeout,
            ) as e:
                if attempt >= self.cfg.max_retries:
                    logger.error(
                        f"Network error for {url} after {attempt + 1} attempt(s); giving up: {type(e).__name__}: {e}"
                    )
                    raise APIRetryError(
                        f"Failed to fetch {url} after {self.cfg.max_retries + 1} attempts: {type(e).__name__}: {e}"
                    ) from e
                logger.warning(
                    f"Transient network error for {url} on attempt {attempt + 1}; will retry: {type(e).__name__}: {e}"
                )
                await asyncio.sleep(backoff + random.random() * 0.25)
                backoff = min(float(self.cfg.max_backoff), backoff * 2)
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                # Determine retry-eligible statuses and compute delay
                retry = False
                delay = backoff

                # Standard retryable statuses
                if status == 429 or 500 <= status < 600:
                    retry = True

                # GitHub-specific 403 rate limiting
                hdrs = {k.lower(): v for k, v in e.response.headers.items()}
                if status == 403 and hdrs.get("x-ratelimit-remaining") == "0":
                    retry = True
                    reset = hdrs.get("x-ratelimit-reset")
                    if reset and reset.isdigit():
                        now = int(time.time())
                        delay = max(0, int(reset) - now)

                # Retry-After header parsing (seconds or HTTP-date)
                if retry:
                    ra = e.response.headers.get("Retry-After")
                    if ra:
                        if ra.isdigit():
                            delay = max(delay, int(ra))
                        else:
                            try:
                                dt = parsedate_to_datetime(ra)
                                if dt is not None:
                                    now_ts = time.time()
                                    delay = max(delay, max(0.0, dt.timestamp() - now_ts))
                            except Exception:
                                pass

                if retry and attempt < self.cfg.max_retries:
                    logger.warning(
                        f"HTTP {status} for {url} on attempt {attempt + 1}; retrying after {delay:.2f}s"
                    )
                    await asyncio.sleep(delay + random.random() * 0.25)
                    backoff = min(float(self.cfg.max_backoff), backoff * 2)
                    continue
                elif retry:
                    logger.error(
                        f"HTTP {status} for {url} after {attempt + 1} attempt(s); giving up"
                    )
                    raise APIRetryError(
                        f"HTTP {status} error for {url} after {self.cfg.max_retries + 1} attempts"
                    ) from e
                else:
                    logger.error(f"HTTP {status} for {url}; not retryable: {e}")
                    raise

        # This line should never be reached, but satisfies type checker
        # All code paths above either return or raise an exception
        raise APIRetryError(
            f"Unexpected: exhausted retries without returning or raising for {url}"
        )

    DownloadStatus = Literal["downloaded", "unchanged", "skipped"]

    async def download_to(
        self,
        url: str,
        dest: os.PathLike | str,
        *,
        overwrite: bool = True,
        force: bool = False,
    ) -> tuple[Path, DownloadStatus]:
        """
        Download content from URL to a file on disk.

        Returns:
            A tuple of (destination_path, status) where status indicates:
            - 'downloaded': New content was written to disk
            - 'unchanged': File matches cached ETag/Last-Modified (304 response)
            - 'skipped': File already exists and overwrite=False
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

    async def download_many(
        self, url_to_path: Mapping[str, os.PathLike | str]
    ) -> list[tuple[Path, str]]:
        coros = [self.download_to(u, p) for u, p in url_to_path.items()]
        return await asyncio.gather(*coros)

    @staticmethod
    def _is_html_response(content: bytes, content_type: str) -> bool:
        """
        Detect if response content is HTML (to guard against unexpected GitHub 404 pages).

        GitHub may return HTML error pages even for raw file URLs when files don't exist.
        This method checks both the Content-Type header and common HTML markers in the content.

        Args:
            content: Response body bytes (first 128 bytes are checked)
            content_type: Content-Type header value

        Returns:
            True if the response appears to be HTML, False otherwise

        Example:
            .. code-block:: python
            AsyncDownloader._is_html_response(b"<!DOCTYPE html><html>", "text/html")
            # True
            AsyncDownloader._is_html_response(b"division_id,name", "text/csv")
            # False
        """
        ctype = content_type.lower()
        if "html" in ctype:
            return True

        # Check first 128 bytes for common HTML markers
        head = content[:128].lstrip().lower()
        html_markers = (
            b"<!doctype html",
            b"<html",
            b"<head",
            b"<body",
            b"<title",
        )
        return any(head.startswith(marker) for marker in html_markers)

    async def _decode_github_response(self, resp: httpx.Response, url: str) -> bytes:
        """
        Decode GitHub API JSON responses (base64 content or download_url fallback).

        GitHub's API returns file content as base64-encoded JSON. This method:
        1. Tries to decode base64 content if present
        2. Falls back to download_url if available
        3. Returns raw bytes for non-API responses

        Args:
            resp: The httpx Response object
            url: Original request URL (for logging)

        Returns:
            Decoded file content as bytes
        """
        try:
            content_type = resp.headers.get("content-type", "").lower()
            is_api_json = ("application/json" in content_type) or (
                "api.github.com" in url
            )

            if not is_api_json:
                return resp.content

            data = resp.json()
            if not isinstance(data, dict):
                return resp.content

            # Try base64 content field
            if (content_field := data.get("content")) and data.get(
                "encoding"
            ) == "base64":
                return base64.b64decode(
                    str(content_field).encode("utf-8"), validate=False
                )

            # Fallback to download_url
            if dl_url := data.get("download_url"):
                async with self._sem:
                    dl_resp = await self._client.get(dl_url)
                dl_resp.raise_for_status()

                if self._is_html_response(
                    dl_resp.content, dl_resp.headers.get("content-type", "")
                ):
                    raise UnexpectedContentError(
                        f"Expected data but received HTML from download_url {dl_url}",
                        url=dl_url,
                        content_type=dl_resp.headers.get("content-type", ""),
                    )
                # Persist validators from the download_url response under the original URL key
                etag = dl_resp.headers.get("etag")
                last_mod = dl_resp.headers.get("last-modified")
                if etag or last_mod:
                    self._etag_cache[url] = {
                        "etag": etag or "",
                        "last_modified": last_mod or "",
                    }
                return dl_resp.content

        except (ValueError, json.JSONDecodeError) as e:
            logger.debug(f"JSON decode failed for {url}, using raw content: {e}")

        return resp.content


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
        http2=True,  # auto-disables if 'h2' not installed
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
        path, status = await d.download_to(
            urls[0], Path("downloads") / Path(urls[0]).name, force=True
        )
        print("forced:", path, status)


if __name__ == "__main__":
    asyncio.run(main())
