"""Remove generated Division and Jurisdiction YAML, keeping ``examples/``.

    uv run python scripts/clear_generated_output.py           # dry run: list what would go
    uv run python scripts/clear_generated_output.py --write   # delete it

Everything under ``divisions/`` and ``jurisdictions/`` is pipeline output
except the ``examples/`` trees, which mirror ``tests/sample_output`` and are
maintained by ``src.utils.sync_examples``. The default is a dry run.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIRS = ("divisions", "jurisdictions")
KEEP = "examples"

logger = logging.getLogger(__name__)


def generated_paths(root: Path = REPO_ROOT) -> list[Path]:
    """Return the top-level entries under each output dir other than ``examples/``."""
    paths: list[Path] = []
    for name in OUTPUT_DIRS:
        output_dir = root / name
        if not output_dir.is_dir():
            continue
        paths.extend(p for p in sorted(output_dir.iterdir()) if p.name != KEEP)
    return paths


def clear(root: Path = REPO_ROOT, write: bool = False) -> list[Path]:
    """Delete generated output under ``root`` when ``write`` is set; return the targets."""
    paths = generated_paths(root)
    if write:
        for path in paths:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
    return paths


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Remove generated YAML under divisions/ and jurisdictions/, keeping "
            "examples/. Dry run by default; pass --write to delete."
        )
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="delete the files (default: only list them)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    paths = clear(write=args.write)
    for path in paths:
        print(path.relative_to(REPO_ROOT))
    logger.info(
        "generated output cleared" if args.write else "dry run; pass --write to delete",
        extra={"path_count": len(paths), "write": args.write},
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
