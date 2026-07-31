from app.core.config import get_settings


def test_settings_load_with_defaults() -> None:
    settings = get_settings()
    assert settings.app_name == "RepoMind AI"
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.llm_provider in ("gemini", "openrouter", "ollama")
    assert settings.database_url.startswith("sqlite:///")


def test_settings_is_cached_singleton() -> None:
    assert get_settings() is get_settings()
