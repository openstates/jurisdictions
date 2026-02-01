"""Error handling tests for AsyncDownloader"""
import pytest
from httpx import Response

from src.init_migration.downloader import AsyncDownloader, DownloaderConfig
from src.errors import (
    APIRetryError,
    UnexpectedContentError
)


class TestErrorHandling:
    """Test error handling for various failure scenarios"""

    @pytest.mark.asyncio
    async def test_retry_exhaustion_raises_api_retry_error(self, respx_mock):
        url = "https://example.com/flaky.csv"
        # Always return 500 -> should eventually raise APIRetryError after retries
        respx_mock.get(url).mock(return_value=Response(500))
        cfg = DownloaderConfig(max_retries=2)
        async with AsyncDownloader(cfg) as d:
            with pytest.raises(APIRetryError):
                await d.fetch_bytes(url)


class TestHTMLDetection:
    """Test HTML response detection"""

    @pytest.mark.asyncio
    async def test_html_content_type_raises(self, respx_mock):
        url = "https://example.com/page"
        respx_mock.get(url).mock(return_value=Response(200, content=b"<html><body>oops</body></html>", headers={"content-type": "text/html"}))
        async with AsyncDownloader() as d:
            with pytest.raises(UnexpectedContentError):
                await d.fetch_bytes(url)

    @pytest.mark.asyncio
    async def test_html_sniffing_raises(self, respx_mock):
        url = "https://example.com/page2"
        # No content-type but HTML-looking body
        respx_mock.get(url).mock(return_value=Response(200, content=b"<!doctype html><title>t</title>"))
        async with AsyncDownloader() as d:
            with pytest.raises(UnexpectedContentError):
                await d.fetch_bytes(url)
