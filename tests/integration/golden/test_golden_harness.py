"""Tests for the harness helpers themselves.

The pure comparison helpers run with the unit suite. The tests that run the
generate stage or regenerate fixtures are marked ``integration``.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from src.init_migration.pipeline_models import Status
from src.utils.deterministic_id import generate_id
from tests.integration.golden.harness import (
    ABSENT,
    FILE_PATH_FIELD,
    GOLDEN_ROOT,
    compare_records,
    compare_trees,
    diff_structures,
    dump_golden_record,
    golden_relative_path,
    load_division_fixtures,
    load_jurisdiction_fixtures,
    load_roster,
    regenerate_from_fixtures,
    run_pipeline,
)

ASOF = datetime(2025, 10, 27, 1, 29, 51, tzinfo=timezone.utc)


def _write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data))
    return path


def _tree_digest(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


# ----------------------------------------------------------------- diff helpers


def test_diff_null_value_differs_from_absent_key():
    assert diff_structures({"a": None}, {}) == [("a", None, ABSENT)]
    assert diff_structures({}, {"a": None}) == [("a", ABSENT, None)]
    assert diff_structures({"a": None}, {"a": None}) == []


def test_diff_reports_dotted_paths_and_list_indexes():
    expected = {"sourcing": [{"source_url": {"url": "https://x/"}}], "id": "1"}
    actual = {"sourcing": [{"source_url": "https://x/"}], "id": "2"}
    assert diff_structures(expected, actual) == [
        ("id", "1", "2"),
        ("sourcing[0].source_url", {"url": "https://x/"}, "https://x/"),
    ]


def test_diff_reports_extra_list_items():
    assert diff_structures({"k": [1]}, {"k": [1, 2]}) == [("k[1]", ABSENT, 2)]
    assert diff_structures({"k": [1, 2]}, {"k": [1]}) == [("k[1]", 2, ABSENT)]


def test_diff_treats_type_change_as_difference():
    assert diff_structures({"sldlst": [48]}, {"sldlst": ["048"]}) == [
        ("sldlst[0]", 48, "048")
    ]
    assert diff_structures({"n": 1}, {"n": True}) == [("n", 1, True)]


def test_compare_records_ignores_only_named_top_level_keys(tmp_path):
    exp = _write(
        tmp_path / "e.yaml",
        {"ocdid": "x", "last_updated": "a", "m": {"last_updated": 1}},
    )
    act = _write(
        tmp_path / "a.yaml",
        {"ocdid": "x", "last_updated": "b", "m": {"last_updated": 2}},
    )
    diffs = compare_records(exp, act, label="e.yaml", ignore_fields=("last_updated",))
    assert [(d.field_path, d.expected, d.actual) for d in diffs] == [
        ("m.last_updated", 1, 2)
    ]


def test_compare_trees_pairs_by_ocdid_and_reports_renamed_path(tmp_path):
    ocdid = "ocd-division/country:us/state:wa/place:tacoma"
    _write(
        tmp_path / "exp/divisions/test/wa/local/tacoma_old.yaml",
        {"ocdid": ocdid, "id": "old"},
    )
    _write(
        tmp_path / "act/divisions/test/wa/local/tacoma_new.yaml",
        {"ocdid": ocdid, "id": "new"},
    )

    diffs = compare_trees(tmp_path / "exp", tmp_path / "act")

    assert [(d.file, d.field_path, d.expected, d.actual) for d in diffs] == [
        (
            "divisions/test/wa/local/tacoma_old.yaml",
            FILE_PATH_FIELD,
            "divisions/test/wa/local/tacoma_old.yaml",
            "divisions/test/wa/local/tacoma_new.yaml",
        ),
        ("divisions/test/wa/local/tacoma_old.yaml", "id", "old", "new"),
    ]


def test_compare_trees_reports_missing_and_unexpected_files(tmp_path):
    _write(
        tmp_path / "exp/divisions/a.yaml", {"ocdid": "ocd-division/country:us/state:a"}
    )
    _write(
        tmp_path / "act/divisions/b.yaml", {"ocdid": "ocd-division/country:us/state:b"}
    )

    diffs = compare_trees(tmp_path / "exp", tmp_path / "act")

    assert [(d.field_path, d.expected, d.actual) for d in diffs] == [
        (FILE_PATH_FIELD, "divisions/a.yaml", ABSENT),
        (FILE_PATH_FIELD, ABSENT, "divisions/b.yaml"),
    ]


def test_compare_trees_reports_duplicate_files_for_one_ocdid(tmp_path):
    ocdid = "ocd-division/country:us/state:tx/place:austin"
    _write(tmp_path / "exp/divisions/austin.yaml", {"ocdid": ocdid})
    _write(tmp_path / "act/divisions/tx/austin.yaml", {"ocdid": ocdid})
    _write(tmp_path / "act/divisions/tx/local/austin.yaml", {"ocdid": ocdid})

    diffs = compare_trees(tmp_path / "exp", tmp_path / "act")

    assert len(diffs) == 1
    assert diffs[0].field_path == FILE_PATH_FIELD
    assert diffs[0].actual == [
        "divisions/tx/austin.yaml",
        "divisions/tx/local/austin.yaml",
    ]


# --------------------------------------------------------------- golden layout


def test_golden_relative_path_reproduces_checked_in_layout():
    by_ocdid = {d.ocdid: d for d in load_division_fixtures()}
    by_ocdid.update({j.ocdid: j for j in load_jurisdiction_fixtures()})

    sausalito = by_ocdid["ocd-division/country:us/state:ca/place:sausalito"]
    assert golden_relative_path(sausalito) == Path(
        f"divisions/test/ca/local/sausalito_{generate_id(sausalito.ocdid)}.yaml"
    )

    anc = by_ocdid["ocd-division/country:us/district:dc/anc:1a/council_district:1"]
    assert golden_relative_path(anc).parts[:4] == ("divisions", "test", "dc", "local")

    austin = by_ocdid["ocd-jurisdiction/country:us/state:tx/place:austin/government"]
    assert golden_relative_path(austin) == Path(
        f"jurisdictions/test/tx/local/city_of_austin_{generate_id(austin.ocdid)}.yaml"
    )


def test_dump_golden_record_refuses_sample_output_root(tmp_path):
    record = load_division_fixtures()[0]
    with pytest.raises(ValueError, match="refusing to write"):
        dump_golden_record(record, GOLDEN_ROOT)
    with pytest.raises(ValueError, match="refusing to write"):
        dump_golden_record(record, GOLDEN_ROOT / "divisions")
    assert dump_golden_record(record, tmp_path).exists()


def test_dump_golden_record_round_trips_the_model_dump(tmp_path):
    record = load_division_fixtures()[0]
    path = dump_golden_record(record, tmp_path)
    assert yaml.safe_load(path.read_text()) == record.model_dump(
        mode="json", exclude_none=False
    )


def test_jurisdiction_fixtures_recover_every_constructible_object():
    names = sorted(j.name for j in load_jurisdiction_fixtures())
    assert names == [
        "ANC 1A Government",
        "City of Austin",
        "Sausalito City Government",
        "Seattle City Government",
        "Tacoma City Government",
    ]


# --------------------------------------------------------------------- runner


@pytest.mark.integration
def test_regenerate_from_fixtures_writes_eleven_files_and_nothing_under_golden(
    tmp_path,
):
    before = _tree_digest(GOLDEN_ROOT)

    written = regenerate_from_fixtures(tmp_path)

    assert len(written) == 11
    assert all(tmp_path in p.parents for p in written)
    assert _tree_digest(GOLDEN_ROOT) == before


@pytest.mark.integration
def test_run_pipeline_over_roster_writes_only_under_given_root(tmp_path):
    before = _tree_digest(GOLDEN_ROOT)

    runs = run_pipeline(load_roster(), tmp_path, ASOF)

    assert _tree_digest(GOLDEN_ROOT) == before
    assert list(tmp_path.rglob("*.yaml")), "pipeline wrote nothing"
    for run in runs:
        for path in (run.response.division_path, run.response.jurisdiction_path):
            if path:
                assert tmp_path in Path(path).parents, path


@pytest.mark.integration
def test_run_pipeline_roster_statuses(tmp_path):
    runs = {r.ocdid: r for r in run_pipeline(load_roster(), tmp_path, ASOF)}

    quarantined = {
        "ocd-division/country:us/state:ca/county:marin/cdp:marin_city",
        "ocd-division/country:us/district:dc/anc:1a/council_district:1",
    }
    for ocdid, run in runs.items():
        if ocdid in quarantined:
            assert run.response.status.status == Status.PARTIAL, ocdid
            assert run.quarantine == [
                {"ocdid": ocdid, "reason": "no_validation_match", "matched_records": []}
            ]
        else:
            assert run.response.status.status == Status.SUCCESS, ocdid
            assert run.quarantine == []
            assert run.response.jurisdiction_path is not None
