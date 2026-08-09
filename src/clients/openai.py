from __future__ import annotations

from functools import lru_cache

from openai import AsyncOpenAI

from src.clients.config import MissingAPIKeyError, get_settings

DEFAULT_MODEL = "gpt-4o-mini"


@lru_cache(maxsize=1)
def make_openai_client() -> AsyncOpenAI:
    """Return an AsyncOpenAI client authenticated from OPENAI_API_KEY.

    Setting the key locally:
        1. Get a key at https://platform.openai.com/api-keys
        2. Add `OPENAI_API_KEY=sk-...` to `.env` at the repo root (preferred),
           or `export OPENAI_API_KEY=sk-...` in your shell.
        3. `.env` is gitignored; see `.env.sample` for the template.
    """
    key = get_settings().openai_api_key
    if not key:
        raise MissingAPIKeyError("OPENAI_API_KEY")
    return AsyncOpenAI(api_key=key)


async def generate(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    use_search: bool = False,
) -> str:
    """Send a prompt to OpenAI and return the text response.

    Args:
        prompt: The user prompt.
        model: OpenAI model id. Defaults to `gpt-4o-mini`.
        use_search: When True, enables the hosted `web_search` tool so the
            model can fetch live web results. Use for tasks where the answer
            is not in the model's parametric knowledge.

    Returns:
        The model's text response.
    """
    client = make_openai_client()
    kwargs: dict = {"model": model, "input": prompt}
    if use_search:
        kwargs["tools"] = [{"type": "web_search"}]
    resp = await client.responses.create(**kwargs)
    return resp.output_text or ""


if __name__ == "__main__":
    # Run: uv run python -m src.clients.openai
    # NOTE: use `-m`, not `python src/clients/openai.py`. Running the file
    # directly puts `src/clients/` on sys.path, so `from openai import
    # AsyncOpenAI` at the top would resolve to this file instead of the
    # third-party package and blow up with ImportError.
    import asyncio

    async def _smoke_test() -> None:
        prompt = (
            "What is the official government website for King County, Washington? "
            "Respond with only the URL."
        )
        print(f"model: {DEFAULT_MODEL}")
        print(f"prompt: {prompt}\n")
        text = await generate(prompt, use_search=True)
        print(f"response:\n{text}")

    asyncio.run(_smoke_test())
