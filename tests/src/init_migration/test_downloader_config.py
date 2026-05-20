"""Tests for DownloaderConfig"""
from httpx import Timeout

from src.init_migration.downloader import DownloaderConfig, _http2_available


class TestDownloaderConfig:
    """Test configuration object initialization and defaults"""
    
    def test_default_config(self):
        """Test default configuration values"""
        cfg = DownloaderConfig()
        assert cfg.concurrency == 12
        assert cfg.max_retries == 3
        assert isinstance(cfg.timeout, Timeout)
        assert cfg.http2 is True
        assert cfg.use_github_auth is False
        assert cfg.github_token is None
        assert cfg.etag_cache_path is None
        assert isinstance(cfg.user_agent, str)

    def test_http2_available_function(self):
        assert isinstance(_http2_available(), bool)

    def test_overrides_and_env_token(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GITHUB_TOKEN", "envtok")
        cache_path = tmp_path / "cache.json"
        cfg = DownloaderConfig(
            concurrency=5,
            max_retries=7,
            http2=False,
            use_github_auth=True,
            etag_cache_path=str(cache_path),
            user_agent="ua/1.0",
        )
        assert cfg.concurrency == 5
        assert cfg.max_retries == 7
        assert cfg.http2 is False
        assert cfg.use_github_auth is True
        # When use_github_auth True, token should be pulled from env if not provided
        assert cfg.github_token == "envtok"
        assert cfg.etag_cache_path == cache_path
        assert cfg.user_agent == "ua/1.0"

    def test_explicit_token_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "envtok")
        cfg = DownloaderConfig(use_github_auth=True, github_token="explicit")
        assert cfg.github_token == "explicit"
