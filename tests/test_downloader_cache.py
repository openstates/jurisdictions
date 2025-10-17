"""ETag cache functionality tests"""
import json
import pytest
from httpx import Response

from src.init_migration.downloader import AsyncDownloader, DownloaderConfig
from src.errors import CacheError


class TestETagCache:
    """Test ETag cache loading, saving, and usage"""

    @pytest.mark.asyncio
    async def test_cache_persist_and_304(self, respx_mock, tmp_cache_dir):
        cache_path = tmp_cache_dir / "etag.json"
        url = "https://example.com/cached.csv"
        # First session: 200 with validators
        respx_mock.get(url).mock(side_effect=[
            Response(200, content=b"abc", headers={"etag": "\"zz\"", "last-modified": "Fri, 01 Jan 2021 00:00:00 GMT"}),
            Response(304, content=b""),
        ])
        cfg = DownloaderConfig(etag_cache_path=cache_path)
        async with AsyncDownloader(cfg) as d:
            b1 = await d.fetch_bytes(url)
            assert b1 == b"abc"
        # After exit, cache file should be written
        assert cache_path.exists()
        # New downloader should load cache and send conditional; will get 304 -> None
        cfg2 = DownloaderConfig(etag_cache_path=cache_path)
        async with AsyncDownloader(cfg2) as d2:
            b2 = await d2.fetch_bytes(url)
            assert b2 is None


class TestCacheCorruption:
    """Test handling of corrupted cache files"""

    @pytest.mark.asyncio
    async def test_corrupted_cache_raises(self, tmp_cache_dir):
        cache_path = tmp_cache_dir / "etag_bad.json"
        cache_path.write_text("{not valid json}")
        cfg = DownloaderConfig(etag_cache_path=cache_path)
        with pytest.raises(CacheError):
            async with AsyncDownloader(cfg):
                pass
