"""Integration tests for AsyncDownloader"""
import pytest
import base64
from httpx import Response

from src.init_migration.downloader import AsyncDownloader, DownloaderConfig


@pytest.mark.integration
class TestDownloaderIntegration:
    """End-to-end integration tests"""

    @pytest.mark.asyncio
    async def test_end_to_end_fetch_and_download(self, respx_mock, tmp_path):
        # Simulate a mix of raw and GitHub API URLs
        raw1 = "https://raw.githubusercontent.com/o/r/main/a.csv"
        api1 = "https://api.github.com/repos/o/r/contents/b.txt"
        respx_mock.get(raw1).mock(return_value=Response(200, content=b"c1\nc2\n", headers={"etag": '"e1"'}))
        respx_mock.get(api1).mock(return_value=Response(200, json={"content": base64.b64encode(b"hello").decode(), "encoding": "base64"}))

        cfg = DownloaderConfig(etag_cache_path=tmp_path / ".etag.json")
        async with AsyncDownloader(cfg) as d:
            blobs = await d.fetch_many([raw1, api1])
            assert blobs[0] == b"c1\nc2\n"
            assert blobs[1] == b"hello"
            # Download them
            mapping = {raw1: tmp_path / "a.csv", api1: tmp_path / "b.txt"}
            results = await d.download_many(mapping)
            assert {s for _, s in results} == {"downloaded"}
            assert (tmp_path / "a.csv").read_bytes() == b"c1\nc2\n"
            assert (tmp_path / "b.txt").read_bytes() == b"hello"


@pytest.mark.integration
@pytest.mark.slow
class TestConcurrencyLimits:
    """Test concurrency behavior"""

    @pytest.mark.asyncio
    async def test_basic_concurrency_does_not_deadlock(self, respx_mock):
        # Minimal sanity: many URLs should complete successfully with low concurrency
        urls = [f"https://example.com/u{i}" for i in range(10)]
        for u in urls:
            respx_mock.get(u).mock(return_value=Response(200, content=b"ok"))
        cfg = DownloaderConfig(concurrency=2, max_retries=1)
        async with AsyncDownloader(cfg) as d:
            blobs = await d.fetch_many(urls)
            assert all(b == b"ok" for b in blobs)
