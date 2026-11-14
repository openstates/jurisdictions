"""Tests for src/utils/parquet.py: a run exports only its own states' files."""

from pathlib import Path

import duckdb

from src.utils.parquet import export_to_parquet

TRACKING_TABLE = "generation_tracking_2026_11_14"

MASTER_IDS = [
    "ocd-division/country:us/state:gu/place:hagatna",
    "ocd-division/country:us/state:vi/place:charlotte_amalie",
    "ocd-division/country:us/district:dc/ward:1",
    "ocd-division/country:us/territory:pr/municipio:ponce",
    "ocd-division/country:us/court_of_appeals:9",
]


def make_db(path: Path, tracking_ids: list[str]) -> str:
    conn = duckdb.connect(str(path))
    try:
        conn.execute("CREATE TABLE master_ocdids (id TEXT, name TEXT)")
        conn.executemany(
            "INSERT INTO master_ocdids VALUES (?, ?)",
            [(ocdid, ocdid.rsplit(":", 1)[-1]) for ocdid in MASTER_IDS],
        )
        conn.execute(
            f"CREATE TABLE {TRACKING_TABLE} (original_id TEXT, status TEXT, "
            "error TEXT, division_path TEXT, jurisdiction_path TEXT)"
        )
        for ocdid in tracking_ids:
            conn.execute(
                f"INSERT INTO {TRACKING_TABLE} VALUES (?, 'success', NULL, NULL, NULL)",
                [ocdid],
            )
    finally:
        conn.close()
    return str(path)


def files_under(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


def read_ids(path: Path) -> list[str]:
    rows = duckdb.sql(f"SELECT id FROM read_parquet('{path}') ORDER BY id").fetchall()
    return [row[0] for row in rows]


def test_master_ocdids_writes_only_run_states_and_stateless(tmp_path):
    db = make_db(tmp_path / "p.duckdb", [])
    out = tmp_path / "parquet"

    export_to_parquet(db, str(out), states=["gu"])

    assert files_under(out / "master_ocdids") == [
        "state=/data_0.parquet",
        "state=gu/data_0.parquet",
    ]


def test_master_ocdids_leaves_other_states_files_untouched(tmp_path):
    db = make_db(tmp_path / "p.duckdb", [])
    out = tmp_path / "parquet"
    wy_file = out / "master_ocdids" / "state=wy" / "data_0.parquet"
    wy_file.parent.mkdir(parents=True)
    wy_file.write_bytes(b"committed wy partition")

    export_to_parquet(db, str(out), states=["gu"])

    assert wy_file.read_bytes() == b"committed wy partition"


def test_master_ocdids_gives_district_and_territories_their_own_folder(tmp_path):
    db = make_db(tmp_path / "p.duckdb", [])
    out = tmp_path / "parquet"

    export_to_parquet(db, str(out), states=["dc", "pr"])

    master = out / "master_ocdids"
    assert read_ids(master / "state=dc" / "data_0.parquet") == [MASTER_IDS[2]]
    assert read_ids(master / "state=pr" / "data_0.parquet") == [MASTER_IDS[3]]
    assert read_ids(master / "state=" / "data_0.parquet") == [MASTER_IDS[4]]


def test_generation_tracking_gives_district_and_territories_their_own_folder(tmp_path):
    db = make_db(tmp_path / "p.duckdb", [MASTER_IDS[2], MASTER_IDS[3]])
    out = tmp_path / "parquet"

    export_to_parquet(db, str(out), states=["dc", "pr"])

    assert files_under(out / TRACKING_TABLE) == [
        "state=dc/data_0.parquet",
        "state=pr/data_0.parquet",
    ]


def test_generation_tracking_same_day_runs_write_separate_files(tmp_path):
    out = tmp_path / "parquet"
    tracking = out / TRACKING_TABLE

    gu_db = make_db(tmp_path / "gu.duckdb", [MASTER_IDS[0]])
    export_to_parquet(gu_db, str(out), states=["gu"])
    gu_bytes = (tracking / "state=gu" / "data_0.parquet").read_bytes()

    vi_db = make_db(tmp_path / "vi.duckdb", [MASTER_IDS[1]])
    export_to_parquet(vi_db, str(out), states=["vi"])

    assert files_under(tracking) == ["state=gu/data_0.parquet", "state=vi/data_0.parquet"]
    assert (tracking / "state=gu" / "data_0.parquet").read_bytes() == gu_bytes
    assert not (out / f"{TRACKING_TABLE}.parquet").exists()


def test_export_writes_no_manifest(tmp_path):
    db = make_db(tmp_path / "p.duckdb", [MASTER_IDS[0]])
    out = tmp_path / "parquet"

    export_to_parquet(db, str(out), states=["gu"])

    assert not (out / "manifest.json").exists()
