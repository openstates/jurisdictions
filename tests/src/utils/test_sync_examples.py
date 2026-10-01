"""The examples mirror is exact, so it cannot drift from sample output."""

from pathlib import Path

from src.utils.sync_examples import plan_sync, sync


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _sample(root: Path, kind: str, relative: str, text: str) -> Path:
    return _write(root / "tests/sample_output" / kind / relative, text)


def test_sync_copies_sample_output_into_examples(tmp_path) -> None:
    """A sample file lands in examples with the fixture segment stripped."""
    _sample(tmp_path, "divisions", "test/wa/local/tacoma_abc.yaml", "ocdid: tacoma\n")

    sync("divisions", root=tmp_path)

    copied = tmp_path / "divisions/examples/wa/local/tacoma_abc.yaml"
    assert copied.read_text() == "ocdid: tacoma\n"


def test_sync_drops_only_the_fixture_segment(tmp_path) -> None:
    """State and locale directories survive; the ``test/`` wrapper does not."""
    _sample(tmp_path, "jurisdictions", "test/ca/local/sausalito.yaml", "name: x\n")

    copies, _ = plan_sync("jurisdictions", root=tmp_path)
    _, destination = copies[0]

    assert destination == tmp_path / "jurisdictions/examples/ca/local/sausalito.yaml"


def test_sync_overwrites_stale_example_content(tmp_path) -> None:
    """An example that no longer matches its source is refreshed."""
    _sample(tmp_path, "divisions", "test/wa/local/tacoma_abc.yaml", "ocdid: new\n")
    _write(tmp_path / "divisions/examples/wa/local/tacoma_abc.yaml", "ocdid: old\n")

    changed = sync("divisions", root=tmp_path)

    assert (tmp_path / "divisions/examples/wa/local/tacoma_abc.yaml").read_text() == (
        "ocdid: new\n"
    )
    assert len(changed) == 1


def test_sync_removes_examples_with_no_source(tmp_path) -> None:
    """The mirror is exact: a dropped fixture drops its example too."""
    _sample(tmp_path, "divisions", "test/wa/local/keep.yaml", "ocdid: keep\n")
    orphan = _write(tmp_path / "divisions/examples/oh/local/stale.yaml", "ocdid: x\n")

    sync("divisions", root=tmp_path)

    assert not orphan.exists()
    assert (tmp_path / "divisions/examples/wa/local/keep.yaml").is_file()


def test_sync_reports_no_change_when_already_mirrored(tmp_path) -> None:
    """A second run is a no-op, so CI stays quiet when nothing moved."""
    _sample(tmp_path, "divisions", "test/wa/local/tacoma_abc.yaml", "ocdid: tacoma\n")
    sync("divisions", root=tmp_path)

    assert sync("divisions", root=tmp_path) == []


def test_check_mode_reports_drift_without_writing(tmp_path) -> None:
    """``--check`` is read-only so CI can fail without mutating the tree."""
    _sample(tmp_path, "divisions", "test/wa/local/tacoma_abc.yaml", "ocdid: new\n")

    changed = sync("divisions", root=tmp_path, write=False)

    assert changed == [tmp_path / "divisions/examples/wa/local/tacoma_abc.yaml"]
    assert not (tmp_path / "divisions/examples").exists()
