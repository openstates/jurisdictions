"""Tests for OCDidMatcher — master row selection, UUID generation, lookup table."""

from pathlib import Path

import duckdb
import pytest

from src.init_migration.ocdid_matcher import OCDidMatcher
from src.init_migration.pipeline_models import OCDidIngestResp


@pytest.fixture
def populated_db(tmp_path):
    """Create a DuckDB with a master table for testing."""
    db_path = str(tmp_path / "test.duckdb")
    conn = duckdb.connect(db_path)

    conn.execute("""
        CREATE TABLE master_ocdids AS SELECT * FROM (VALUES
            ('ocd-division/country:us/state:wa', 'Washington'),
            ('ocd-division/country:us/state:wa/place:seattle', 'Seattle'),
            ('ocd-division/country:us/state:wa/place:tacoma', 'Tacoma'),
            ('ocd-division/country:us/state:wa/county:king/precinct:1', 'King Precinct 1'),
            ('ocd-division/country:us/state:wv/place:charleston', 'Charleston'),
            ('ocd-division/country:us/state:tx/place:austin', 'Austin'),
            ('ocd-division/country:us/district:dc', 'District of Columbia'),
            ('ocd-division/country:us/district:dc/ward:1', 'Ward 1')
        ) AS t(id, name)
    """)

    conn.close()
    return db_path


def _selected_ids(db_path: str, states: list[str]) -> set[str]:
    matcher = OCDidMatcher(db_path=db_path, states=states, csv_backup_path="")
    return {r.ocdid.raw_ocdid for r in matcher.run_matching().matched}


def test_selects_every_master_row_for_state(populated_db):
    """All master rows for the state, including the state row itself, are selected."""
    assert _selected_ids(populated_db, ["wa"]) == {
        "ocd-division/country:us/state:wa",
        "ocd-division/country:us/state:wa/place:seattle",
        "ocd-division/country:us/state:wa/place:tacoma",
    }


def test_skips_precincts(populated_db):
    """Precinct rows are not selected and are counted as skipped."""
    matcher = OCDidMatcher(db_path=populated_db, states=["wa"], csv_backup_path="")
    results = matcher.run_matching()
    selected = {r.ocdid.raw_ocdid for r in results.matched}
    assert (
        "ocd-division/country:us/state:wa/county:king/precinct:1" not in selected
    )
    assert results.skipped_precincts == 1


def test_excludes_other_states(populated_db):
    """A state code must not select rows from a state sharing its prefix."""
    selected = _selected_ids(populated_db, ["wa"])
    assert not any("state:wv" in i or "state:tx" in i for i in selected)


def test_selects_district_of_columbia(populated_db):
    """DC uses the district: segment rather than state:."""
    assert _selected_ids(populated_db, ["dc"]) == {
        "ocd-division/country:us/district:dc",
        "ocd-division/country:us/district:dc/ward:1",
    }


def test_selects_all_rows_without_state_filter(populated_db):
    """With no states given, every non-precinct master row is selected."""
    assert len(_selected_ids(populated_db, [])) == 7


def test_match_returns_ocdid_ingest_resp(populated_db):
    """Each selected record should produce a valid OCDidIngestResp."""
    matcher = OCDidMatcher(db_path=populated_db, states=["wa"], csv_backup_path="")
    results = matcher.run_matching()
    for resp in results.matched:
        assert isinstance(resp, OCDidIngestResp)
        assert resp.uuid is not None
        assert resp.ocdid.raw_ocdid.startswith("ocd-division/")
        assert resp.ocdid.state == "wa"


def test_raw_record_contains_master_data(populated_db):
    """raw_record should contain the master list columns."""
    matcher = OCDidMatcher(db_path=populated_db, states=["wa"], csv_backup_path="")
    results = matcher.run_matching()
    for resp in results.matched:
        assert "id" in resp.raw_record
        assert "name" in resp.raw_record


def test_match_generates_deterministic_uuids(populated_db):
    """Same OCD ID should produce the same UUID across runs."""
    matcher1 = OCDidMatcher(db_path=populated_db, states=["wa"], csv_backup_path="")
    results1 = matcher1.run_matching()

    matcher2 = OCDidMatcher(db_path=populated_db, states=["wa"], csv_backup_path="")
    results2 = matcher2.run_matching()

    uuids1 = {r.ocdid.raw_ocdid: str(r.uuid) for r in results1.matched}
    uuids2 = {r.ocdid.raw_ocdid: str(r.uuid) for r in results2.matched}
    assert uuids1 == uuids2


def test_lookup_table_created_in_duckdb(populated_db):
    """run_matching() should create an ocdid_uuid_lookup table."""
    matcher = OCDidMatcher(db_path=populated_db, states=["wa"], csv_backup_path="")
    matcher.run_matching()

    conn = duckdb.connect(populated_db)
    count = conn.execute("SELECT COUNT(*) FROM ocdid_uuid_lookup").fetchone()[0]
    conn.close()
    assert count == 3  # washington + seattle + tacoma


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


def test_no_orphan_tables_created(populated_db):
    """run_matching() should no longer create orphan tables."""
    matcher = OCDidMatcher(db_path=populated_db, states=["wa"], csv_backup_path="")
    matcher.run_matching()

    conn = duckdb.connect(populated_db)
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    conn.close()
    assert "local_orphans" not in tables
    assert "master_orphans" not in tables
