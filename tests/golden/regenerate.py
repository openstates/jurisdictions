from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from tests.golden.compare import compare_trees
from tests.golden.records import make_division, make_jurisdiction
from tests.golden.runner import FixtureRunner, GoldenRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO_ROOT / "tests" / "sample_output"

BANNER = (
    "=" * 72
    + "\nGOLDEN REGENERATION — overwrites tests/sample_output/.\n"
    + "Maintainer-approved change-control step only (AGENTS.md).\n"
    + "=" * 72
)


def default_runner() -> GoldenRunner:
    return FixtureRunner([make_division()], [make_jurisdiction()])


def regenerate(
    golden_dir: Path, runner: GoldenRunner, apply: bool, out=sys.stdout
) -> int:
    print(BANNER, file=out)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        runner.run(tmp_path)
        diffs = compare_trees(Path(golden_dir), tmp_path)
        print(f"{len(diffs)} difference(s) vs golden:", file=out)
        for d in diffs:
            print(f"  {d.kind:14} {d.file}:{d.path}", file=out)
        if not apply:
            print("\nDry run. No files written.", file=out)
            return 0
        golden_dir = Path(golden_dir)
        if golden_dir.exists():
            shutil.rmtree(golden_dir)
        shutil.copytree(tmp_path, golden_dir)
        print(f"\nGolden regenerated at {golden_dir}.", file=out)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tests.golden.regenerate")
    parser.add_argument(
        "--yes", action="store_true", help="Overwrite golden (disabled until Phase 10)."
    )
    args = parser.parse_args(argv)
    if args.yes:
        print(
            "Refusing to overwrite golden: the deterministic renderer (Phase 10) "
            "is not implemented, so regenerated layout is not final. "
            "Showing drift only.",
            file=sys.stderr,
        )
    return regenerate(GOLDEN_DIR, default_runner(), apply=False)


if __name__ == "__main__":
    raise SystemExit(main())
