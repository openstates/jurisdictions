"""
Stage 1 OCDid Pipeline — Orchestrator

Entry point for the init_migration pipeline. Parses CLI arguments,
loads state list, calls DownloadManager and OCDidMatcher in sequence,
and reports summary stats.

Usage:
    uv run python src/init_migration/main.py
    uv run python src/init_migration/main.py --state wa
    uv run python src/init_migration/main.py --state wa,tx,oh --force
    uv run python src/init_migration/main.py --log-dir /tmp/logs
"""

import argparse
import asyncio
import logging
import logging.handlers
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from src.utils.state_lookup import load_state_code_lookup
from src.init_migration.download_manager import DownloadManager
from src.init_migration.ocdid_matcher import OCDidMatcher, MatchResults

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Stage 1 OCDid Pipeline — fetch, match, and generate lookup table"
    )
    parser.add_argument(
        "--state",
        type=str,
        default=None,
        help="Comma-separated state codes to process (e.g., wa,tx,oh). "
             "Default: all states from state_lookup.json.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Bypass ETag cache and force re-download of all files.",
    )
    parser.add_argument(
        "--log-dir",
        type=str,
        default="logs",
        help="Directory for log files (default: logs/).",
    )
    return parser.parse_args(argv)


def resolve_states(state_arg: str | None) -> list[str]:
    """Resolve state list from CLI argument or state_lookup.json.

    Args:
        state_arg: Comma-separated state codes, or None for all states.

    Returns:
        List of lowercase two-letter state codes.
    """
    if state_arg:
        return [s.strip().lower() for s in state_arg.split(",")]

    lookup = load_state_code_lookup()
    return [entry["stusps"].lower() for entry in lookup]


def configure_logging(log_dir: str) -> None:
    """Configure stdlib logging for console and rotating file output."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Reset handlers so repeated invocations do not duplicate log output.
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    file_handler = logging.handlers.RotatingFileHandler(
        log_path / "pipeline.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    root.addHandler(console_handler)
    root.addHandler(file_handler)


def print_summary(
    console: Console,
    download_stats: dict,
    match_results,
) -> None:
    """Print a summary table using rich."""
    table = Table(title="Pipeline Summary")
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")

    table.add_row("Files downloaded", str(download_stats.get("files_downloaded", 0)))
    table.add_row("Files cached (ETag)", str(download_stats.get("files_cached", 0)))
    table.add_row("Files failed", str(download_stats.get("files_failed", 0)))
    table.add_row("Master rows loaded", str(download_stats.get("master_rows", 0)))
    table.add_row("Local rows loaded", str(download_stats.get("local_rows", 0)))
    table.add_row("Matched records", str(len(match_results.matched)))
    table.add_row("Local orphans", str(len(match_results.local_orphans)))
    table.add_row("Master orphans", str(len(match_results.master_orphans)))

    console.print(table)


async def run_pipeline(args: argparse.Namespace) -> MatchResults:
    """Run the full Stage 1 pipeline.

    Returns:
        MatchResults containing matched, local_orphan, and master_orphan records
        for Stage 2 consumption.
    """
    console = Console()
    states = resolve_states(args.state)

    logger.info("Starting pipeline", extra={"state_count": len(states)})
    console.print(f"Processing {len(states)} state(s): {', '.join(states)}")

    # Phase 1: Download and load
    dm = DownloadManager(states=states)
    download_stats = await dm.run_downloads(force=args.force)

    # Phase 2: Match and build
    matcher = OCDidMatcher(states=states)
    match_results = matcher.run_matching(show_progress=True)

    # Summary
    print_summary(console, download_stats, match_results)
    logger.info("Pipeline complete")

    return match_results


def main() -> MatchResults | None:
    """CLI entry point.

    Returns:
        MatchResults when called programmatically, None is not returned
        but asyncio.run returns the coroutine result.
    """
    args = parse_args()
    configure_logging(args.log_dir)
    return asyncio.run(run_pipeline(args))


if __name__ == "__main__":
    main()
