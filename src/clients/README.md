# `src/clients/`

Thin async wrappers around the external services the pipeline calls out to. Each module has an `if __name__ == "__main__"` block for smoke-testing.

## Client roster

| Module | Purpose | Key needed |
|---|---|---|
| `gemini.py` | Google Gemini LLM (`generate`, grounded-search opt-in) | `GEMINI_API_KEY` |
| `openai.py` | OpenAI LLM (`generate`, hosted web_search opt-in) | `OPENAI_API_KEY` |
| `ollama.py` | Local model via Ollama (`generate`) | none (daemon must run; requires `local` extra) |
| `ddg.py` | DuckDuckGo search (`search`) | none |
| `brave.py` | Brave Search (`search`, DDG fallback) | `BRAVE_API_KEY` |

## Keys

Keys live in `.env` at the repo root (gitignored). Copy `.env.sample` and fill in what you need — none of the keys are required for import; each factory raises `MissingAPIKeyError` only if you actually call it without the corresponding key set.

## Optional extras

Local-model runtimes are opt-in to keep the base install lean. Install the `local` extra if you plan to call `src.clients.ollama.generate()`:

```bash
uv sync --extra local
# or
pip install '.[local]'
```

Without the extra, importing `src.clients.ollama` still works, but calling `make_ollama_client()` or `generate()` raises `ImportError` with an install hint.

## Smoke tests

```bash
uv run python -m src.clients.gemini
uv run python -m src.clients.openai
uv run python -m src.clients.ollama
uv run python -m src.clients.ddg
uv run python -m src.clients.brave
```

Use `-m` (not `python src/clients/openai.py`) — running the OpenAI file directly puts `src/clients/` on `sys.path`, which shadows the third-party `openai` package.
