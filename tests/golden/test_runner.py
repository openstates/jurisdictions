import yaml

from tests.golden.records import make_division, make_jurisdiction
from tests.golden.runner import FixtureRunner


def test_fixture_runner_writes_expected_files(tmp_path):
    result = FixtureRunner([make_division()], [make_jurisdiction()]).run(tmp_path)
    assert result.division_count == 1
    assert result.jurisdiction_count == 1
    assert result.division_paths[0].exists()
    assert result.jurisdiction_paths[0].exists()


def test_fixture_runner_writes_only_under_output_dir(monkeypatch, tmp_path):
    # Redirect the models' default base_dir to a sentinel directory to detect leaks
    sentinel = tmp_path / "sentinel"
    monkeypatch.setattr("src.models.division.PROJECT_PATH", str(sentinel))
    monkeypatch.setattr("src.models.jurisdiction.PROJECT_PATH", str(sentinel))

    # Run the runner into a separate output directory
    out = tmp_path / "out"
    FixtureRunner([make_division()], [make_jurisdiction()]).run(out)

    # Assert exactly 2 yaml files exist under the output directory
    assert len(list(out.rglob("*.yaml"))) == 2

    # Assert no yaml files leaked to the sentinel directory
    assert not sentinel.exists() or not list(sentinel.rglob("*.yaml"))


def test_fixture_runner_output_is_reparseable(tmp_path):
    result = FixtureRunner([make_division()], []).run(tmp_path)
    doc = yaml.safe_load(result.division_paths[0].read_text())
    assert doc["ocdid"].startswith("ocd-division/")
