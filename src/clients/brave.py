from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from src.clients.config import MissingAPIKeyError, get_settings

BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"
DEFAULT_MAX_RESULTS = 5
DEFAULT_TIMEOUT_SECONDS = 10.0

# Brave wraps matched query terms in <strong> highlight tags in the
# `description` field. Strip them so snippets fed into LLM prompts stay
# plain text.
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return _HTML_TAG_RE.sub("", text)


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


async def search(
    query: str,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> list[SearchResult]:
    """Search Brave and return clean text results.

    Uses Brave's standard `/res/v1/web/search` endpoint. Returns title,
    URL, and description per result — no HTML, no full page bodies —
    which keeps LLM token cost low.

    Free tier: 2000 queries/month, 1 QPS. Get a key at
    https://api-dashboard.search.brave.com/ and set `BRAVE_API_KEY` in
    `.env`.

    The result shape mirrors `src.clients.ddg.SearchResult`, so callers
    can treat Brave as a drop-in fallback for DDG.

    Args:
        query: The search query.
        max_results: Cap on results returned. Default 5.

    Returns:
        A list of `SearchResult` (empty if Brave returns nothing).

    Raises:
        MissingAPIKeyError: If BRAVE_API_KEY is not set.
        httpx.HTTPStatusError: On non-2xx responses (rate limits, bad
            queries, auth failures — inspect `.response.status_code`).
    """
    key = get_settings().brave_api_key
    if not key:
        raise MissingAPIKeyError("BRAVE_API_KEY")

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
        resp = await client.get(
            BRAVE_API_URL,
            params={"q": query, "count": max_results},
            headers={
                "X-Subscription-Token": key,
                "Accept": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    results = data.get("web", {}).get("results", [])
    return [
        SearchResult(
            title=_strip_html(r.get("title", "")),
            url=r.get("url", ""),
            snippet=_strip_html(r.get("description", "")),
        )
        for r in results[:max_results]
    ]


if __name__ == "__main__":
    # Run: uv run python -m src.clients.brave
    import asyncio

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
