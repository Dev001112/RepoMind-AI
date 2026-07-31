"""Chat model factory: builds the primary model, with an OpenRouter fallback.

LangChain's `BaseChatModel` is already the right abstraction here -- we don't
need our own interface, just a function that returns the right concrete class.
Primary/fallback composition reuses LangChain's own `Runnable.with_fallbacks()`
rather than hand-rolling retry logic.
"""

from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable

from app.core.config import Settings
from app.core.exceptions import UnsupportedProviderError


# Both SDKs default to several internal retries with backoff (Gemini's client
# defaults to max_retries=6) before ever raising -- fine for a transient blip,
# but a quota error (especially a DAILY quota, which won't recover within the
# request) still burns through all of them first. That delays the exception
# `.with_fallbacks()` is waiting for by anywhere from seconds to minutes, which
# from the outside just looks like "the fallback isn't working". One retry is
# enough headroom for a genuine transient hiccup while still failing fast.
_MAX_PROVIDER_RETRIES = 1


def _build_chat_model(provider: str, model_name: str, settings: Settings) -> BaseChatModel:
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model_name,
            api_key=settings.gemini_api_key,
            max_retries=_MAX_PROVIDER_RETRIES,
            temperature=settings.llm_temperature,
            max_output_tokens=settings.llm_max_output_tokens,
        )

    if provider == "openrouter":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name,
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            max_retries=_MAX_PROVIDER_RETRIES,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_output_tokens,
        )

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model_name,
            base_url=settings.ollama_base_url,
            temperature=settings.llm_temperature,
            num_predict=settings.llm_max_output_tokens,
        )

    raise UnsupportedProviderError(provider)


def get_chat_model(settings: Settings) -> Runnable[LanguageModelInput, BaseMessage]:
    """Return the primary chat model, with a two-tier fallback chain: OpenRouter
    first (if configured), then Ollama (local, no rate limit -- the one option
    that can't itself get rate-limited, so it's the last resort, not the first).

    `Runnable.with_fallbacks()` tries each fallback in order until one
    succeeds, so listing both means Gemini -> OpenRouter -> Ollama with a
    single call.

    Return type is the LangChain `Runnable` this actually is, not
    `BaseChatModel` -- with fallbacks active this is a `RunnableWithFallbacks`,
    which isn't a `BaseChatModel` subclass (no `.bind_tools()`/
    `.with_structured_output()`/etc.), even though it composes fine into an
    LCEL chain via `|`.
    """
    primary = _build_chat_model(settings.llm_provider, settings.llm_model_name, settings)

    fallbacks: list[BaseChatModel] = []
    if settings.openrouter_api_key and settings.llm_provider != "openrouter":
        fallbacks.append(_build_chat_model("openrouter", settings.openrouter_model_name, settings))
    if settings.llm_provider != "ollama":
        fallbacks.append(_build_chat_model("ollama", settings.ollama_model, settings))

    return primary.with_fallbacks(fallbacks) if fallbacks else primary
