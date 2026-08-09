from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ddgs import DDGS

DEFAULT_MAX_RESULTS = 5


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


def _search_sync(query: str, max_results: int) -> list[SearchResult]:
    with DDGS() as d:
        raw = d.text(query, max_results=max_results)
    return [
        SearchResult(
            title=r.get("title", ""),
            url=r.get("href", ""),
            snippet=r.get("body", ""),
        )
        for r in raw
    ]


async def search(
    query: str,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> list[SearchResult]:
    """Search DuckDuckGo and return a list of clean text results.

    DDG returns title/URL/snippet only — no HTML, no full page content —
    which keeps LLM token cost near zero. Free, no API key.

    `ddgs` is sync-only, so this wraps it via `asyncio.to_thread` to fit
    the async call shape used by the other clients in this package.

    Args:
        query: The search query.
        max_results: Cap on results returned. Default 5.

    Returns:
        A list of `SearchResult` (empty if DDG returns nothing).
    """
    return await asyncio.to_thread(_search_sync, query, max_results)


if __name__ == "__main__":
    # Run: uv run python -m src.clients.ddg

    async def _smoke_test() -> None:
        query = "King County Washington official government website"
        print(f"query: {query}\n")
        results = await search(query, max_results=3)
        for i, r in enumerate(results, 1):
            print(f"[{i}] {r.title}")
            print(f"    {r.url}")
            snippet = r.snippet[:120] + ("..." if len(r.snippet) > 120 else "")
            print(f"    {snippet}\n")

    asyncio.run(_smoke_test())
