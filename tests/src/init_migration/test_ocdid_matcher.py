"""Tests for OCDidMatcher — join logic, UUID generation, lookup table."""
import pytest
import duckdb
from pathlib import Path

from src.init_migration.ocdid_matcher import OCDidMatcher
from src.init_migration.pipeline_models import OCDidIngestResp


@pytest.fixture
def populated_db(tmp_path):
    """Create a DuckDB with master and local tables for testing."""
    db_path = str(tmp_path / "test.duckdb")
    conn = duckdb.connect(db_path)

    conn.execute("""
        CREATE TABLE master_ocdids AS SELECT * FROM (VALUES
            ('ocd-division/country:us/state:wa/place:seattle', 'Seattle'),
            ('ocd-division/country:us/state:wa/place:tacoma', 'Tacoma'),
            ('ocd-division/country:us/state:tx/place:austin', 'Austin')
        ) AS t(id, name)
    """)

    conn.execute("""
        CREATE TABLE local_ocdids AS SELECT * FROM (VALUES
            ('ocd-division/country:us/state:wa/place:seattle', 'Seattle', 'wa'),
            ('ocd-division/country:us/state:wa/place:tacoma', 'Tacoma', 'wa'),
            ('ocd-division/country:us/state:wa/place:olympia', 'Olympia', 'wa'),
            ('ocd-division/country:us/state:tx/place:austin', 'Austin', 'tx')
        ) AS t(id, name, state)
    """)

    conn.close()
    return db_path


def test_match_finds_matching_records(populated_db):
    """Records in both master and local should be classified as matches."""
    matcher = OCDidMatcher(db_path=populated_db, states=["wa"])
    results = matcher.run_matching()
    matched_ocdids = {r.ocdid.raw_ocdid for r in results.matched}
    assert "ocd-division/country:us/state:wa/place:seattle" in matched_ocdids
    assert "ocd-division/country:us/state:wa/place:tacoma" in matched_ocdids


def test_match_detects_local_orphans(populated_db):
    """Records in local but not master should be local orphans."""
    matcher = OCDidMatcher(db_path=populated_db, states=["wa"])
    results = matcher.run_matching()
    orphan_ids = {r["id"] for r in results.local_orphans}
    assert "ocd-division/country:us/state:wa/place:olympia" in orphan_ids


def test_match_returns_ocdid_ingest_resp(populated_db):
    """Each matched record should produce a valid OCDidIngestResp."""
    matcher = OCDidMatcher(db_path=populated_db, states=["wa"])
    results = matcher.run_matching()
    for resp in results.matched:
        assert isinstance(resp, OCDidIngestResp)
        assert resp.uuid is not None
        assert resp.ocdid.raw_ocdid.startswith("ocd-division/")
        assert resp.ocdid.state == "wa"


def test_raw_record_contains_master_data(populated_db):
    """raw_record should contain master list columns, not local columns."""
    matcher = OCDidMatcher(db_path=populated_db, states=["wa"])
    results = matcher.run_matching()
    for resp in results.matched:
        assert "id" in resp.raw_record
        assert "name" in resp.raw_record
        assert "_local_state" not in resp.raw_record


def test_match_generates_deterministic_uuids(populated_db):
    """Same OCD ID should produce the same UUID across runs."""
    matcher1 = OCDidMatcher(db_path=populated_db, states=["wa"])
    results1 = matcher1.run_matching()

    matcher2 = OCDidMatcher(db_path=populated_db, states=["wa"])
    results2 = matcher2.run_matching()

    uuids1 = {r.ocdid.raw_ocdid: str(r.uuid) for r in results1.matched}
    uuids2 = {r.ocdid.raw_ocdid: str(r.uuid) for r in results2.matched}
    assert uuids1 == uuids2


def test_lookup_table_created_in_duckdb(populated_db):
    """run_matching() should create an ocdid_uuid_lookup table."""
    matcher = OCDidMatcher(db_path=populated_db, states=["wa"])
    matcher.run_matching()

    conn = duckdb.connect(populated_db)
    count = conn.execute("SELECT COUNT(*) FROM ocdid_uuid_lookup").fetchone()[0]
    conn.close()
    assert count >= 2  # seattle + tacoma


def test_lookup_csv_backup_created(populated_db, tmp_path):
    """run_matching() should export a CSV backup of the lookup table."""
    csv_path = str(tmp_path / "lookup.csv")
    matcher = OCDidMatcher(
        db_path=populated_db, states=["wa"], csv_backup_path=csv_path
    )
    matcher.run_matching()
    assert Path(csv_path).exists()
    content = Path(csv_path).read_text()
    assert "seattle" in content


def test_orphan_tables_created_in_duckdb(populated_db):
    """run_matching() should create local_orphans and master_orphans tables."""
    matcher = OCDidMatcher(db_path=populated_db, states=["wa"])
    matcher.run_matching()

    conn = duckdb.connect(populated_db)
    local_orphan_count = conn.execute(
        "SELECT COUNT(*) FROM local_orphans"
    ).fetchone()[0]
    conn.close()
    assert local_orphan_count >= 1  # olympia
