import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "clear_generated_output.py"
_spec = importlib.util.spec_from_file_location("clear_generated_output", _SCRIPT)
assert _spec is not None and _spec.loader is not None
clear_generated_output = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(clear_generated_output)


def _seed(root: Path) -> None:
    for kind in ("divisions", "jurisdictions"):
        (root / kind / "examples" / "wa" / "local").mkdir(parents=True)
        (root / kind / "examples" / "wa" / "local" / "x.yaml").write_text("a: 1\n")
        (root / kind / "wa" / "regional").mkdir(parents=True)
        (root / kind / "wa" / "regional" / "y.yaml").write_text("b: 2\n")
        (root / kind / "stray.yaml").write_text("c: 3\n")


def test_dry_run_lists_generated_output_without_deleting(tmp_path: Path) -> None:
    _seed(tmp_path)

    paths = clear_generated_output.clear(tmp_path, write=False)

    assert paths == [
        tmp_path / "divisions" / "stray.yaml",
        tmp_path / "divisions" / "wa",
        tmp_path / "jurisdictions" / "stray.yaml",
        tmp_path / "jurisdictions" / "wa",
    ]
    assert all(p.exists() for p in paths)


def test_write_deletes_generated_output_and_keeps_examples(tmp_path: Path) -> None:
    _seed(tmp_path)

    clear_generated_output.clear(tmp_path, write=True)

    for kind in ("divisions", "jurisdictions"):
        assert sorted(p.name for p in (tmp_path / kind).iterdir()) == ["examples"]
        assert (tmp_path / kind / "examples" / "wa" / "local" / "x.yaml").exists()


def test_missing_output_dirs_are_skipped(tmp_path: Path) -> None:
    assert clear_generated_output.clear(tmp_path, write=True) == []
