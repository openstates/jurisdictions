from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

from src.errors import Error

load_dotenv()


class MissingAPIKeyError(Error):
    """Raised when a required API key is not set in the environment."""

    def __init__(self, key_name: str):
        message = (
            f"{key_name} is not set. Add it to .env (see .env.sample) or export it."
        )
        super().__init__(message)
        self.message = message
        self.key_name = key_name


DEFAULT_OLLAMA_HOST = "http://localhost:11434"


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    openai_api_key: str | None
    brave_api_key: str | None
    github_token: str | None
    ollama_host: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        brave_api_key=os.getenv("BRAVE_API_KEY") or None,
        github_token=os.getenv("GITHUB_TOKEN") or None,
        ollama_host=os.getenv("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST,
    )
