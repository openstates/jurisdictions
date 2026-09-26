"""Mirror the golden sample output into the public ``examples/`` directories.

``README.md`` points application builders at ``divisions/examples``. Those
files are a copy of ``tests/sample_output`` rather than a hand-maintained
set, so they cannot drift from what the models actually emit.

The mirror is exact: files missing from the source are removed from the
destination. The ``test/`` path segment the fixtures write under is dropped,
so ``tests/sample_output/divisions/test/wa/local/x.yaml`` lands at
``divisions/examples/wa/local/x.yaml``.

Run with ``uv run python -m src.utils.sync_examples``; ``--check`` reports
drift without writing, which is what CI uses.
"""

import argparse
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

SAMPLE_ROOT = Path("tests/sample_output")
FIXTURE_SEGMENT = "test"
KINDS = ("divisions", "jurisdictions")


def _destination(source: Path, sample_dir: Path, examples_dir: Path) -> Path:
    relative = source.relative_to(sample_dir)
    if relative.parts and relative.parts[0] == FIXTURE_SEGMENT:
        relative = Path(*relative.parts[1:])
    return examples_dir / relative


def plan_sync(
    kind: str, root: Path = Path(".")
) -> tuple[list[tuple[Path, Path]], list[Path]]:
    """Return the (source, destination) copies and the stale files to delete."""
    sample_dir = root / SAMPLE_ROOT / kind
    examples_dir = root / kind / "examples"

    copies: list[tuple[Path, Path]] = []
    expected: set[Path] = set()
    if sample_dir.is_dir():
        for source in sorted(sample_dir.rglob("*.yaml")):
            destination = _destination(source, sample_dir, examples_dir)
            copies.append((source, destination))
            expected.add(destination)

    stale = []
    if examples_dir.is_dir():
        stale = sorted(p for p in examples_dir.rglob("*.yaml") if p not in expected)

    return copies, stale


def sync(kind: str, root: Path = Path("."), write: bool = True) -> list[Path]:
    """Mirror one kind. Returns the destination paths whose content changed."""
    copies, stale = plan_sync(kind, root)
    changed: list[Path] = []

    for source, destination in copies:
        payload = source.read_bytes()
        if destination.is_file() and destination.read_bytes() == payload:
            continue
        changed.append(destination)
        if write:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)

    for path in stale:
        changed.append(path)
        if write:
            path.unlink()

    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report drift and exit non-zero instead of writing",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    drifted: list[Path] = []
    for kind in KINDS:
        changed = sync(kind, write=not args.check)
        drifted.extend(changed)
        for path in changed:
            logger.info(
                "drift: %s" if args.check else "synced: %s",
                path,
                extra={"kind": kind, "path": str(path)},
            )

    if not drifted:
        logger.info("examples already match %s", SAMPLE_ROOT)
        return 0

    if args.check:
        logger.info(
            "%d file(s) differ; run: uv run python -m src.utils.sync_examples",
            len(drifted),
        )
        return 1

    logger.info("synced %d file(s)", len(drifted))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
