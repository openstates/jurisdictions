"""Tests for src/utils/build_pages_data.py: one Parquet file per table for the site."""

import json
from pathlib import Path

import duckdb
import pytest

from src.utils.build_pages_data import TablePlan, build_pages_data, plan_tables


def test_plan_tables_reads_single_files_and_state_folders():
    paths = [
        "manifest.json",
        "master_ocdids/state=wy/data_0.parquet",
        "generation_tracking_2026_11_14/state=vi/data_0.parquet",
        "generation_tracking_2026_10_31.parquet",
        "master_ocdids/state=/data_0.parquet",
        "generation_tracking_2026_11_14/state=gu/data_0.parquet",
    ]

    assert plan_tables(paths) == [
        TablePlan(
            name="generation_tracking_2026_10_31",
            sources=["generation_tracking_2026_10_31.parquet"],
            partitioned=False,
        ),
        TablePlan(
            name="generation_tracking_2026_11_14",
            sources=[
                "generation_tracking_2026_11_14/state=gu/data_0.parquet",
                "generation_tracking_2026_11_14/state=vi/data_0.parquet",
            ],
            partitioned=True,
        ),
        TablePlan(
            name="master_ocdids",
            sources=[
                "master_ocdids/state=/data_0.parquet",
                "master_ocdids/state=wy/data_0.parquet",
            ],
            partitioned=True,
        ),
    ]


def test_plan_tables_rejects_a_file_and_a_folder_with_the_same_name():
    with pytest.raises(ValueError, match="master_ocdids"):
        plan_tables(["master_ocdids.parquet", "master_ocdids/state=gu/data_0.parquet"])


def write_fixture(src: Path) -> None:
    src.mkdir()
    conn = duckdb.connect()
    try:
        conn.execute(
            "CREATE TABLE m AS SELECT * FROM (VALUES "
            "('ocd-division/country:us/state:gu/place:a', 'gu'), "
            "('ocd-division/country:us/state:gu/place:b', 'gu'), "
            "('ocd-division/country:us/state:vi/place:c', 'vi'), "
            "('ocd-division/country:us/court_of_appeals:9', '')) v(id, state)"
        )
        conn.execute(
            f"COPY m TO '{src / 'master_ocdids'}' (FORMAT PARQUET, PARTITION_BY (state), "
            "FILENAME_PATTERN 'data_{i}')"
        )
        conn.execute(
            "COPY (SELECT 'ocd-division/country:us/state:wy' AS original_id, 'success' AS status) "
            f"TO '{src / 'generation_tracking_2026_10_31.parquet'}' (FORMAT PARQUET)"
        )
    finally:
        conn.close()
    (src / "manifest.json").write_text('{"stale": true}')


def test_build_writes_one_file_per_table_and_a_manifest_counted_from_files(tmp_path):
    src, out = tmp_path / "parquet", tmp_path / "site"
    write_fixture(src)

    build_pages_data(src, out)

    assert sorted(p.name for p in out.iterdir()) == [
        "generation_tracking_2026_10_31.parquet",
        "manifest.json",
        "master_ocdids.parquet",
    ]
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["generated_at"]
    tables = {t["name"]: t for t in manifest["tables"]}
    assert set(tables) == {"generation_tracking_2026_10_31", "master_ocdids"}
    for name, entry in tables.items():
        assert entry["file"] == f"{name}.parquet"
        file_rows = duckdb.sql(
            f"SELECT COUNT(*) FROM read_parquet('{out / entry['file']}')"
        ).fetchone()[0]
        assert entry["rows"] == file_rows
        assert entry["bytes"] == (out / entry["file"]).stat().st_size
    assert tables["master_ocdids"]["rows"] == 4
    assert {"name": "state", "type": "VARCHAR"} in tables["master_ocdids"]["columns"]


def test_build_keeps_the_state_column_from_folder_names(tmp_path):
    src, out = tmp_path / "parquet", tmp_path / "site"
    write_fixture(src)

    build_pages_data(src, out)

    rows = duckdb.sql(
        f"SELECT state, COUNT(*) FROM read_parquet('{out / 'master_ocdids.parquet'}') "
        "GROUP BY state ORDER BY state"
    ).fetchall()
    assert rows == [("", 1), ("gu", 2), ("vi", 1)]
