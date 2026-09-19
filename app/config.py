"""Configuration loading for the Conversation to GitHub Projects Translator."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OLLAMA_LOCAL_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_CLOUD_BASE_URL = "https://ollama.com"


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class AppConfig:
    """Application configuration loaded from environment variables."""

    openai_api_key: str
    openai_model: str
    github_token: str
    github_owner: str
    ollama_local_base_url: str
    ollama_cloud_base_url: str
    ollama_api_key: str


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(
            f"Missing required environment variable: {name}. "
            f"Add it to {ENV_FILE.name} or your shell environment."
        )
    return value


def load_config(
    *,
    require_openai_api_key: bool = True,
    require_github_token: bool = True,
    require_github_owner: bool = True,
) -> AppConfig:
    """Load application configuration from .env and the process environment."""

    load_dotenv(dotenv_path=ENV_FILE)

    if require_openai_api_key:
        openai_api_key = _require_env("OPENAI_API_KEY")
    else:
        openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if require_github_token:
        github_token = _require_env("GITHUB_TOKEN")
    else:
        github_token = os.getenv("GITHUB_TOKEN", "").strip()

    if require_github_owner:
        github_owner = _require_env("GITHUB_OWNER")
    else:
        github_owner = os.getenv("GITHUB_OWNER", "").strip()

    openai_model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
    ollama_local_base_url = (
        os.getenv("OLLAMA_LOCAL_BASE_URL", DEFAULT_OLLAMA_LOCAL_BASE_URL).strip()
        or DEFAULT_OLLAMA_LOCAL_BASE_URL
    )
    ollama_cloud_base_url = (
        os.getenv("OLLAMA_CLOUD_BASE_URL", DEFAULT_OLLAMA_CLOUD_BASE_URL).strip()
        or DEFAULT_OLLAMA_CLOUD_BASE_URL
    )
    ollama_api_key = os.getenv("OLLAMA_API_KEY", "").strip()

    return AppConfig(
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        github_token=github_token,
        github_owner=github_owner,
        ollama_local_base_url=ollama_local_base_url,
        ollama_cloud_base_url=ollama_cloud_base_url,
        ollama_api_key=ollama_api_key,
    )
