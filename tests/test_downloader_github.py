"""GitHub API specific tests"""
import base64
import pytest
import respx
from httpx import Response

from src.init_migration.downloader import AsyncDownloader, DownloaderConfig
from src.errors import UnexpectedContentError


class TestGitHubAPIIntegration:
    """Test GitHub API specific functionality"""

    @pytest.mark.asyncio
    async def test_authorization_header_sent_when_enabled(self, respx_mock):
        url = "https://api.github.com/repos/owner/repo/contents/file.txt"
        seen_auth = {"val": None}

        @respx_mock.get(url)
        def handler(request):
            seen_auth["val"] = request.headers.get("Authorization")
            return Response(200, json={"content": base64.b64encode(b"abc").decode(), "encoding": "base64"})

        cfg = DownloaderConfig(use_github_auth=True, github_token="tok123")
        async with AsyncDownloader(cfg) as d:
            data = await d.fetch_bytes(url)
            assert data == b"abc"
        assert seen_auth["val"] == "Bearer tok123"

    @pytest.mark.asyncio
    async def test_base64_content_decoding(self, respx_mock):
        url = "https://api.github.com/repos/o/r/contents/a.bin"
        payload = {"content": base64.b64encode(b"hello").decode(), "encoding": "base64"}
        respx_mock.get(url).mock(return_value=Response(200, json=payload))
        async with AsyncDownloader() as d:
            b = await d.fetch_bytes(url)
            assert b == b"hello"

    @pytest.mark.asyncio
    async def test_download_url_fallback_and_html_guard(self, respx_mock):
        api_url = "https://api.github.com/repos/o/r/contents/a.csv"
        dl_url = "https://raw.githubusercontent.com/o/r/main/a.csv"
        # First, API returns a download_url without content. The downloader should request it.
        respx_mock.get(api_url).mock(return_value=Response(200, json={"download_url": dl_url}))
        respx_mock.get(dl_url).mock(return_value=Response(200, content=b"x,y\n1,2\n"))
        async with AsyncDownloader() as d:
            b = await d.fetch_bytes(api_url)
            assert b == b"x,y\n1,2\n"
        # Now verify that if download_url serves HTML, we raise UnexpectedContentError
        respx_mock.reset()
        respx_mock.get(api_url).mock(return_value=Response(200, json={"download_url": dl_url}))
        respx_mock.get(dl_url).mock(return_value=Response(200, content=b"<html></html>", headers={"content-type": "text/html"}))
        async with AsyncDownloader() as d:
            with pytest.raises(UnexpectedContentError):
                await d.fetch_bytes(api_url)
