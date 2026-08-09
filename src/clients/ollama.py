from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from src.clients.config import get_settings

if TYPE_CHECKING:
    from ollama import AsyncClient

DEFAULT_MODEL = "llama3.1:8b"

_INSTALL_HINT = (
    "The `ollama` package is not installed. It's an optional dependency; "
    "install with `uv sync --extra local` (or `pip install '.[local]'`)."
)


@lru_cache(maxsize=1)
def make_ollama_client() -> "AsyncClient":
    """Return an ollama.AsyncClient pointed at the local Ollama daemon.

    Reads `OLLAMA_HOST` from the environment (defaults to
    http://localhost:11434). No API key — the daemon runs on the host.

    Requires the optional `local` extra:
        uv sync --extra local

    Setting up the daemon:
        1. Install: `brew install ollama` (or see https://ollama.com/download)
        2. Start the daemon: `ollama serve` (or launch the Ollama app)
        3. Pull a model: `ollama pull llama3.1:8b`
        4. List what you have: `ollama list`
    """
    try:
        from ollama import AsyncClient
    except ImportError as e:
        raise ImportError(_INSTALL_HINT) from e
    return AsyncClient(host=get_settings().ollama_host)


async def generate(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
) -> str:
    """Send a prompt to a local Ollama model and return the text response.

    Local models don't have hosted search; if you want search grounding,
    call `src.clients.ddg.search()` first and include the results in
    `prompt` yourself.

    Args:
        prompt: The user prompt.
        model: Ollama model tag (see `ollama list`). Defaults to
            `llama3.1:8b`.

    Returns:
        The model's text response.
    """
    client = make_ollama_client()
    resp = await client.generate(model=model, prompt=prompt)
    return resp.response or ""


if __name__ == "__main__":
    # Run: uv run python -m src.clients.ollama
    # Requires the Ollama daemon to be running and the model to be pulled.
    import asyncio

    async def _smoke_test() -> None:
        prompt = (
            "What is the official government website for King County, Washington? "
            "Respond with only the URL."
        )
        print(f"model: {DEFAULT_MODEL}")
        print(f"prompt: {prompt}\n")
        text = await generate(prompt)
        print(f"response:\n{text}")

    asyncio.run(_smoke_test())
