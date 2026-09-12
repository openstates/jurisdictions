import yaml

from tests.golden.records import make_division, make_jurisdiction
from tests.golden.runner import FixtureRunner


def test_fixture_runner_writes_expected_files(tmp_path):
    result = FixtureRunner([make_division()], [make_jurisdiction()]).run(tmp_path)
    assert result.division_count == 1
    assert result.jurisdiction_count == 1
    assert result.division_paths[0].exists()
    assert result.jurisdiction_paths[0].exists()


def test_fixture_runner_writes_only_under_output_dir(tmp_path, monkeypatch):
    # Chdir into tmp_path so that any write to the models' relative default
    # base_dir ("divisions/", "jurisdictions/") would land under tmp_path,
    # not under the intended output directory.
    monkeypatch.chdir(tmp_path)

    # Run the runner into a separate output directory
    out = tmp_path / "out"
    FixtureRunner([make_division()], [make_jurisdiction()]).run(out)

    # Assert exactly 2 yaml files exist under the output directory
    assert len(list(out.rglob("*.yaml"))) == 2

    # Assert no leak to the models' relative defaults resolved against the cwd
    assert not (tmp_path / "divisions").exists()
    assert not (tmp_path / "jurisdictions").exists()


def test_fixture_runner_output_is_reparseable(tmp_path):
    result = FixtureRunner([make_division()], []).run(tmp_path)
    doc = yaml.safe_load(result.division_paths[0].read_text())
    assert doc["ocdid"].startswith("ocd-division/")
