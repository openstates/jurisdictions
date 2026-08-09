from __future__ import annotations

from functools import lru_cache

from google import genai
from google.genai import types

from src.clients.config import MissingAPIKeyError, get_settings

DEFAULT_MODEL = "gemini-flash-latest"


@lru_cache(maxsize=1)
def make_gemini_client() -> genai.Client:
    """Return a google-genai Client authenticated from GEMINI_API_KEY.

    The returned client exposes both sync (`client.models.generate_content`)
    and async (`client.aio.models.generate_content`) surfaces; call sites
    should prefer the `.aio` surface for pipeline use.

    Setting the key locally:
        1. Get a key at https://aistudio.google.com/apikey
        2. Add `GEMINI_API_KEY=...` to `.env` at the repo root (preferred),
           or `export GEMINI_API_KEY=...` in your shell.
        3. `.env` is gitignored; see `.env.sample` for the template.
    """
    key = get_settings().gemini_api_key
    if not key:
        raise MissingAPIKeyError("GEMINI_API_KEY")
    return genai.Client(api_key=key)


async def generate(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    use_search: bool = False,
) -> str:
    """Send a prompt to Gemini and return the text response.

    Args:
        prompt: The user prompt.
        model: Gemini model id. Defaults to `gemini-2.5-flash`.
        use_search: When True, enables Google Search grounding — the model
            can look up live web results and cite them. Use for tasks like
            "find the official .gov URL for jurisdiction X" where the answer
            is not in the model's parametric knowledge.

    Returns:
        The model's text response.
    """
    client = make_gemini_client()
    config = None
    if use_search:
        config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        )
    resp = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )
    return resp.text or ""


if __name__ == "__main__":
    # Run: uv run python -m src.clients.gemini
    # (running the file directly — `python src/clients/gemini.py` — also works
    # here since `gemini` doesn't shadow a real package, but -m is safer.)
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
