from pathlib import Path

import pytest
import yaml

from tests.golden.compare import compare_trees


def _write(root: Path, rel: str, data) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data))


def test_identical_trees_have_no_diffs(tmp_path):
    exp, act = tmp_path / "exp", tmp_path / "act"
    _write(exp, "a/x.yaml", {"k": 1, "n": {"a": "01"}})
    _write(act, "a/x.yaml", {"n": {"a": "01"}, "k": 1})  # key order differs
    assert compare_trees(exp, act) == []


def test_value_mismatch_reports_field_path(tmp_path):
    exp, act = tmp_path / "exp", tmp_path / "act"
    _write(exp, "x.yaml", {"geoid": "0645820"})
    _write(act, "x.yaml", {"geoid": "645820"})
    diffs = compare_trees(exp, act)
    assert len(diffs) == 1
    d = diffs[0]
    assert (d.file, d.path, d.kind) == ("x.yaml", "geoid", "VALUE_MISMATCH")
    assert d.expected == "0645820" and d.actual == "645820"


def test_missing_and_extra_keys(tmp_path):
    exp, act = tmp_path / "exp", tmp_path / "act"
    _write(exp, "x.yaml", {"a": 1, "b": 2})
    _write(act, "x.yaml", {"a": 1, "c": 3})
    seen = {(d.kind, d.path) for d in compare_trees(exp, act)}
    assert ("MISSING_KEY", "b") in seen
    assert ("EXTRA_KEY", "c") in seen


def test_missing_and_extra_files(tmp_path):
    exp, act = tmp_path / "exp", tmp_path / "act"
    _write(exp, "only_expected.yaml", {"a": 1})
    _write(act, "only_actual.yaml", {"a": 1})
    seen = {(d.kind, d.file) for d in compare_trees(exp, act)}
    assert ("MISSING_FILE", "only_expected.yaml") in seen
    assert ("EXTRA_FILE", "only_actual.yaml") in seen


def test_list_order_is_significant(tmp_path):
    exp, act = tmp_path / "exp", tmp_path / "act"
    _write(exp, "x.yaml", {"xs": [1, 2, 3]})
    _write(act, "x.yaml", {"xs": [1, 3, 2]})
    assert any(d.kind == "VALUE_MISMATCH" for d in compare_trees(exp, act))


def test_nested_value_mismatch_with_dotted_path(tmp_path):
    exp, act = tmp_path / "exp", tmp_path / "act"
    _write(exp, "x.yaml", {"n": {"a": 1}})
    _write(act, "x.yaml", {"n": {"a": 2}})
    diffs = compare_trees(exp, act)
    assert len(diffs) == 1
    d = diffs[0]
    assert (d.file, d.path, d.kind) == ("x.yaml", "n.a", "VALUE_MISMATCH")
    assert d.expected == 1 and d.actual == 2


def test_type_mismatch(tmp_path):
    exp, act = tmp_path / "exp", tmp_path / "act"
    _write(exp, "x.yaml", {"a": 1})
    _write(act, "x.yaml", {"a": "1"})
    diffs = compare_trees(exp, act)
    assert len(diffs) == 1
    d = diffs[0]
    assert (d.file, d.path, d.kind) == ("x.yaml", "a", "TYPE_MISMATCH")
    assert d.expected == 1 and d.actual == "1"


def test_missing_directory_raises_error(tmp_path):
    exp = tmp_path / "nonexistent"
    act = tmp_path / "actual"
    act.mkdir()
    with pytest.raises(FileNotFoundError):
        compare_trees(exp, act)
