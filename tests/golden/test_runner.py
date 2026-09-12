import yaml

from tests.golden.records import make_division, make_jurisdiction
from tests.golden.runner import FixtureRunner


def test_fixture_runner_writes_expected_files(tmp_path):
    result = FixtureRunner([make_division()], [make_jurisdiction()]).run(tmp_path)
    assert result.division_count == 1
    assert result.jurisdiction_count == 1
    assert result.division_paths[0].exists()
    assert result.jurisdiction_paths[0].exists()


def test_fixture_runner_writes_only_under_output_dir(tmp_path):
    FixtureRunner([make_division()], [make_jurisdiction()]).run(tmp_path)
    written = list(tmp_path.rglob("*.yaml"))
    assert len(written) == 2
    assert all(str(p).startswith(str(tmp_path)) for p in written)


def test_fixture_runner_output_is_reparseable(tmp_path):
    result = FixtureRunner([make_division()], []).run(tmp_path)
    doc = yaml.safe_load(result.division_paths[0].read_text())
    assert doc["ocdid"].startswith("ocd-division/")
