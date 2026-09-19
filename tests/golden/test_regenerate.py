import yaml

from tests.golden.records import make_division
from tests.golden.regenerate import regenerate
from tests.golden.runner import FixtureRunner


def _golden(tmp_path):
    golden = tmp_path / "golden"
    (golden / "divisions").mkdir(parents=True)
    (golden / "divisions" / "old.yaml").write_text(yaml.safe_dump({"a": 1}))
    return golden


def test_dry_run_does_not_touch_golden(tmp_path):
    golden = _golden(tmp_path)
    before = (golden / "divisions" / "old.yaml").read_text()
    rc = regenerate(golden, FixtureRunner([make_division()], []), apply=False)
    assert rc == 0
    assert (golden / "divisions" / "old.yaml").read_text() == before


def test_apply_replaces_golden(tmp_path):
    golden = _golden(tmp_path)
    rc = regenerate(golden, FixtureRunner([make_division()], []), apply=True)
    assert rc == 0
    assert not (golden / "divisions" / "old.yaml").exists()
    assert list(golden.rglob("*.yaml"))  # runner output is present
