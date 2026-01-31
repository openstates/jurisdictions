from pathlib import Path
from typing import Iterable
from loguru import logger
import polars as pl

from .downloader import AsyncDownloader, DownloaderConfig
from .parsers import csv_bytes_to_df, vstack_locals

RAW = "https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/master/{path}"
API = "https://api.github.com/repos/opencivicdata/ocd-division-ids/contents/{path}?ref=master"

def master_url(use_api: bool) -> str:
    path = "identifiers/country-us.csv"
    return (API if use_api else RAW).format(path=path)

def local_urls(states: Iterable[str], *, use_api: bool) -> list[str]:
    tmpl = "identifiers/country-us/state-{st}-local_gov.csv"
    base = API if use_api else RAW
    return [base.format(path=tmpl.format(st=s.lower())) for s in states]

async def fetch_master_and_locals(states: list[str], *, use_api: bool,
                                  force: bool = False, cfg: DownloaderConfig | None = None) -> tuple[pl.DataFrame, list[pl.DataFrame]]:
    cfg = cfg or DownloaderConfig(etag_cache_path=".etag_cache.json")
    async with AsyncDownloader(cfg) as d:
        # master
        m_bytes = await d.fetch_bytes(master_url(use_api), force=force)
        if m_bytes is None:
            logger.warning("Master 304 (unchanged) but no persisted bytes; consider disk cache.")
            raise RuntimeError("Master unchanged without a persisted copy")
        master = csv_bytes_to_df(m_bytes)

        # locals
        urls = local_urls(states, use_api=use_api)
        blobs = await d.fetch_many(urls)
        locals_dfs = [csv_bytes_to_df(b) for b in blobs if b]  # skip 304/None
        return master, locals_dfs

def merge(master: pl.DataFrame, locals_dfs: list[pl.DataFrame], *, on: str = "id") -> pl.DataFrame:
    if not locals_dfs:
        return master
    local_stack = vstack_locals(locals_dfs)
    # Ensure join key dtype alignment if needed:
    # master = master.with_columns(pl.col(on).cast(pl.Utf8))
    # local_stack = local_stack.with_columns(pl.col(on).cast(pl.Utf8))
    return master.join(local_stack, on=on, how="left")