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
import sys
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

import httpx
from rich.console import Console
from rich.table import Table

from src.utils.state_lookup import load_state_code_lookup
from src.init_migration.download_manager import DownloadManager
from src.init_migration.ocdid_matcher import OCDidMatcher, MatchResults
from src.init_migration.generate_pipeline import GeneratePipeline
from src.init_migration.pipeline_models import DIVISIONS_SHEET_CSV_URL, GeneratorReq

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None ) -> argparse.Namespace:
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
    """Configure standard Python logging with console and file output."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Get root logger and clear existing handlers
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler (INFO and above)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (DEBUG and above, with rotation at 10 MB, keep 5 backups)
    log_file = str(log_path / "pipeline.log")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)


def print_summary(
    console: Console,
    download_stats: dict,
    match_results,
    phase3_stats: dict | None = None,
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

    if phase3_stats:
        table.add_section()
        table.add_row("YAML generated", str(phase3_stats.get("success", 0)))
        table.add_row("YAML skipped",   str(phase3_stats.get("skipped", 0)))
        table.add_row("YAML partial",   str(phase3_stats.get("partial", 0)))
        table.add_row("YAML failed",    str(phase3_stats.get("failed", 0)))

    console.print(table)


def _cache_validation_csv() -> Path:
    """Download the validation CSV once and cache it to a tmp file.

    Without this, GeneratePipeline re-downloads the full sheet for every record.
    """
    cache_path = Path(tempfile.gettempdir()) / "phase3_validation.csv"
    logger.info(f"Caching validation CSV from {DIVISIONS_SHEET_CSV_URL}")
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        resp = client.get(DIVISIONS_SHEET_CSV_URL)
        resp.raise_for_status()
    cache_path.write_bytes(resp.content)
    logger.info(f"Validation CSV cached at {cache_path} ({len(resp.content)} bytes)")
    return cache_path


async def run_pipeline(args: argparse.Namespace) -> MatchResults:
    """Run the full Stage 1 pipeline.

    Returns:
        MatchResults containing matched, local_orphan, and master_orphan records
        for Stage 2 consumption.
    """
    console = Console()
    states = resolve_states(args.state)

    logger.info(f"Starting pipeline for {len(states)} state(s)")
    console.print(f"Processing {len(states)} state(s): {', '.join(states)}")

    # Phase 1: Download and load
    dm = DownloadManager(states=states)
    download_stats = await dm.run_downloads(force=args.force)

    # Phase 2: Match and build
    matcher = OCDidMatcher(states=states)
    match_results = matcher.run_matching(show_progress=True)

    # Phase 3: Generate Division and Jurisdiction YAML for every matched record
    phase3_stats = {"success": 0, "skipped": 0, "partial": 0, "failed": 0}
    if match_results.matched:
        validation_csv_path = _cache_validation_csv()
        for ingest_resp in match_results.matched:
            req = GeneratorReq(
                data=ingest_resp,
                validation_data_filepath=str(validation_csv_path),
            )
            pipeline = GeneratePipeline(req)
            try:
                response = await pipeline.run()
                phase3_stats[response.status.status.value] += 1
            except Exception:
                logger.exception(f"Phase 3 failed for {ingest_resp.ocdid.raw_ocdid}")
                phase3_stats["failed"] += 1

    # Summary
    print_summary(console, download_stats, match_results, phase3_stats)
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
