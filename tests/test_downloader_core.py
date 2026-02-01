"""Core functionality tests for AsyncDownloader"""
import pytest
from httpx import Response
from pathlib import Path

from src.init_migration.downloader import AsyncDownloader
from src.errors import DownloaderNotInitializedError


class TestAsyncDownloaderContextManager:
    """Test async context manager lifecycle"""

    @pytest.mark.asyncio
    async def test_raises_if_not_initialized(self):
        d = AsyncDownloader()
        with pytest.raises(DownloaderNotInitializedError):
            await d.fetch_bytes("https://example.com/x.csv")


class TestBasicDownloads:
    """Test basic download functionality"""

    @pytest.mark.asyncio
    async def test_fetch_and_download(self, respx_mock, tmp_path, sample_csv_content):
        url = "https://example.com/file.csv"
        route = respx_mock.get(url).mock(return_value=Response(200, content=sample_csv_content, headers={"etag": "W/\"123\""}))
        async with AsyncDownloader() as d:
            data = await d.fetch_bytes(url)
            assert data == sample_csv_content
            # Ensure route called
            assert route.called
            # download_to writes file
            dest = tmp_path / "file.csv"
            p, status = await d.download_to(url, dest)
            assert p == dest and status == "downloaded"
            assert dest.read_bytes() == sample_csv_content

    @pytest.mark.asyncio
    async def test_fetch_many_and_download_many(self, respx_mock, tmp_path):
        urls = [f"https://example.com/f{i}.bin" for i in range(3)]
        for i, u in enumerate(urls):
            respx_mock.get(u).mock(return_value=Response(200, content=f"X{i}".encode()))
        async with AsyncDownloader() as d:
            blobs = await d.fetch_many(urls)
            assert [b.decode() for b in blobs] == ["X0", "X1", "X2"]
            url_to_path = {u: tmp_path / Path(u).name for u in urls}
            results = await d.download_many(url_to_path)
            assert all(s == "downloaded" for _, s in results)
            for u in urls:
                assert (tmp_path / Path(u).name).exists()


class TestConditionalRequests:
    """Test ETag/Last-Modified conditional requests"""

    @pytest.mark.asyncio
    async def test_etag_304_handling(self, respx_mock, sample_csv_content):
        url = "https://example.com/etag.csv"
        # First call returns 200 with etag
        respx_mock.get(url).mock(side_effect=[
            Response(200, content=sample_csv_content, headers={"etag": "\"abc\""}),
            Response(304, content=b""),
        ])
        async with AsyncDownloader() as d:
            b1 = await d.fetch_bytes(url)
            assert b1 == sample_csv_content
            # second should be 304 -> None
            b2 = await d.fetch_bytes(url)
            assert b2 is None
