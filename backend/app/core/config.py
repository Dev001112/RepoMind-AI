"""Application settings, loaded from environment variables / .env.

Single source of truth for configuration. Use `get_settings()` everywhere
(it's an lru_cache singleton) instead of instantiating `Settings()` directly.
"""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    app_name: str = "RepoMind AI"
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    # NoDecode: pydantic-settings otherwise tries to json.loads() this env var before our
    # validator ever sees it, which crashes on a plain comma-separated string.
    cors_origins: Annotated[list[str], NoDecode] = ["*"]
    log_level: str = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: str | list[str]) -> list[str]:
        """Allow a plain comma-separated string in .env, e.g. CORS_ORIGINS=http://a,http://b."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    # --- Database ---
    # SQLite for Phase 1 (zero setup). Swap to a Postgres DSN later just by
    # changing this one value, e.g. "postgresql+psycopg2://user:pass@host/db".
    database_url: str = "sqlite:///./repomind.db"

    # --- Qdrant ---
    # Empty (default) = embedded local mode, no server needed (qdrant-client writes to
    # `qdrant_local_path` directly). Set to a URL (e.g. http://localhost:6333, or the
    # docker-compose service) to use a real Qdrant server instead.
    qdrant_url: str = ""
    qdrant_api_key: str | None = None
    qdrant_collection_name: str = "repomind_chunks"
    qdrant_local_path: str = "qdrant_data"

    # --- LLM ---
    # `llm_provider`/`llm_model_name` select the PRIMARY model. get_chat_model()
    # wraps it with a LangChain `.with_fallbacks()` chain: OpenRouter (if
    # `openrouter_api_key` is set) then Ollama (if the primary isn't already
    # ollama) -- Ollama runs locally with no rate limit, so it's the fallback
    # that can never itself get rate-limited. See app/ai/llm/factory.py.
    llm_provider: Literal["gemini", "openrouter", "ollama"] = "gemini"
    llm_model_name: str = "gemini-2.5-flash"
    # Lower than any provider's own default (0.7-0.8) -- these are grounded RAG
    # answers about a specific codebase, not creative writing; consistency and
    # accuracy matter more than variety. Generous-but-bounded token cap so a
    # thorough answer (e.g. the security lens) isn't cut short, but rambling is.
    llm_temperature: float = 0.3
    # gemini-2.5-flash spends part of its output budget on reasoning tokens, so
    # a 1024 cap routinely truncated structured JSON (the enrichment chain
    # silently lost its judgment fields). 8192 leaves room for both the
    # reasoning and the full answer/JSON.
    llm_max_output_tokens: int = 8192
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Free-tier OpenRouter model IDs rotate frequently -- verify at
    # https://openrouter.ai/models?max_price=0 (or GET /api/v1/models) before relying on this.
    openrouter_model_name: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    # --- Embeddings ---
    # "ollama" runs a local model via `ollama pull nomic-embed-text` -- no API key needed.
    embedding_provider: Literal["gemini", "bge", "nomic", "ollama", "openai"] = "ollama"
    embedding_model_name: str = "nomic-embed-text"
    openai_api_key: str | None = None

    # --- Misc / integrations ---
    github_token: str | None = None

    # --- Storage ---
    repositories_dir: str = "repositories"
    uploads_dir: str = "uploads"
    generated_reports_dir: str = "generated_reports"


@lru_cache
def get_settings() -> Settings:
    return Settings()
