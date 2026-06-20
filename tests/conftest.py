"""Shared test fixtures and configuration for downloader tests"""

import pytest
import respx
from pathlib import Path
import json
import sys
import asyncio
import inspect
import duckdb

from src.init_migration.ocdid_matcher import DEFAULT_DB_PATH

# Ensure project root is on sys.path so `import src` works without installation
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# Register asyncio marker to avoid strict-markers failure and provide a simple async runner
pytest.register_assert_rewrite(__name__)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark test as async and run in event loop"
    )


def pytest_pyfunc_call(pyfuncitem):
    marker = pyfuncitem.get_closest_marker("asyncio")
    if marker:
        func = pyfuncitem.obj
        if inspect.iscoroutinefunction(func):
            loop = asyncio.new_event_loop()
            try:
                # Only pass arguments that the test function actually declares
                argnames = getattr(pyfuncitem, "_fixtureinfo").argnames
                kwargs = {k: v for k, v in pyfuncitem.funcargs.items() if k in argnames}
                loop.run_until_complete(func(**kwargs))
            finally:
                loop.close()
            return True
    # Let pytest handle non-async tests
    return None


@pytest.fixture
def respx_mock():
    """Fixture for mocking HTTP requests"""
    with respx.mock(assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def tmp_cache_dir(tmp_path):
    """Fixture for temporary cache directory"""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def sample_csv_content():
    """Sample CSV data for testing"""
    return b"id,name,value\n1,test1,100\n2,test2,200"


@pytest.fixture
def sample_json_content():
    """Sample JSON data for testing"""
    data = {"key": "value", "items": [1, 2, 3]}
    return json.dumps(data).encode()


@pytest.fixture
def github_api_response():
    """Sample GitHub API response"""
    import base64

    content = b"Hello, World!"
    return {
        "name": "file.txt",
        "content": base64.b64encode(content).decode("utf-8"),
        "encoding": "base64",
        "download_url": "https://raw.githubusercontent.com/test/repo/main/file.txt",
    }

# NOTE:
# The Stage 1 pipeline writes into persistent DuckDB tables using append-style
# inserts. Without clearing tables between integration tests, data from prior
# test runs can accumulate and inflate match/orphan counts unexpectedly.
#
# This fixture resets pipeline tables before each test to ensure deterministic
# integration test behavior and isolated test state.
#
# Maintainers may want to revisit whether the pipeline itself should enforce
# idempotent ingestion semantics (e.g. per-state replacement, deduplication,
# or transactional rebuilds) rather than relying on test-level cleanup.

@pytest.fixture
def clean_duckdb():

    # NOTE:
    # Tests currently reset the default pipeline DuckDB database directly.
    # We cannot yet inject a dedicated test DB path cleanly because the
    # main.py orchestration flow does not consistently support passing a
    # custom db_path through all pipeline components.
    db_path = DEFAULT_DB_PATH

    conn = duckdb.connect(db_path)

    tables = [
        "local_ocdids",
        "master_ocdids",
        "ocdid_uuid_lookup",
        "local_orphans",
        "master_orphans",
    ]

    for table in tables:
        conn.execute(f"DROP TABLE IF EXISTS {table}")

    conn.close()

    yield