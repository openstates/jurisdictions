"""Regenerate the golden YAML under tests/sample_output/ from the fixture objects.

    uv run python scripts/regenerate_sample_output.py            # dry run: print the diff
    uv run python scripts/regenerate_sample_output.py --write    # rewrite tests/sample_output/
    uv run python scripts/regenerate_sample_output.py --write --output-dir /tmp/out

The default is a dry run: the fixture objects are regenerated into a
temporary directory, compared field by field against the checked-in files,
and the differences are printed. Nothing is written. The exit status is 1
when differences exist so the command doubles as a drift check.

``--write`` writes the regenerated files to ``--output-dir`` (default
``tests/sample_output/``) and removes any file there that describes the same
record under a different filename. This is a maintainer action: review the
dry-run diff first, and never run it from a test.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.integration.golden.harness import (  # noqa: E402
    GOLDEN_ROOT,
    compare_trees,
    format_differences,
    load_yaml_tree,
    regenerate_from_fixtures,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Regenerate tests/sample_output/ from tests/fixtures/. Dry run by "
            "default; pass --write to write files."
        )
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="write the regenerated files (default: only print the diff)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=GOLDEN_ROOT,
        help="directory to write into with --write (default: tests/sample_output)",
    )
    return parser.parse_args(argv)


def dry_run() -> int:
    with tempfile.TemporaryDirectory(prefix="sample_output_regen_") as tmp:
        root = Path(tmp)
        written = regenerate_from_fixtures(root)
        differences = compare_trees(GOLDEN_ROOT, root)
    print(f"regenerated {len(written)} files into a temporary directory")
    if not differences:
        print(f"no differences against {GOLDEN_ROOT}")
        return 0
    print(format_differences(differences))
    files = {d.file for d in differences}
    print(
        f"\n{len(differences)} differences in {len(files)} files against "
        f"{GOLDEN_ROOT}. Nothing written; pass --write to regenerate."
    )
    return 1


def write(output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    existing = load_yaml_tree(output_dir) if output_dir.exists() else {}

    with tempfile.TemporaryDirectory(prefix="sample_output_regen_") as tmp:
        staged_root = Path(tmp)
        regenerate_from_fixtures(staged_root)
        staged = load_yaml_tree(staged_root)
        for entries in staged.values():
            for relative, _ in entries:
                target = output_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((staged_root / relative).read_bytes())
                print(f"wrote   {target}")

    # A record whose id changed gets a new filename; drop the file it replaces.
    for key, entries in existing.items():
        if key not in staged:
            continue
        regenerated_paths = {relative for relative, _ in staged[key]}
        for relative, _ in entries:
            if relative not in regenerated_paths:
                (output_dir / relative).unlink()
                print(f"removed {output_dir / relative}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if "PYTEST_CURRENT_TEST" in os.environ:
        raise RuntimeError(
            "this command regenerates golden files; do not run it from a test"
        )
    args = parse_args(argv)
    if not args.write:
        return dry_run()
    return write(args.output_dir)


if __name__ == "__main__":
    sys.exit(main())
