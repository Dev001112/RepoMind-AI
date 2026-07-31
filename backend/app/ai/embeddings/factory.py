"""Embeddings factory: dispatches on settings.embedding_provider.

LangChain's `Embeddings` abstract class is already the right interface --
we just return the correct concrete implementation.
"""

from langchain_core.embeddings import Embeddings

from app.core.config import Settings
from app.core.exceptions import UnsupportedProviderError


def get_embeddings(settings: Settings) -> Embeddings:
    if settings.embedding_provider == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(
            model=settings.embedding_model_name,
            google_api_key=settings.gemini_api_key,
        )

    if settings.embedding_provider == "bge":
        from langchain_huggingface import HuggingFaceEmbeddings

        return HuggingFaceEmbeddings(model_name=settings.embedding_model_name)

    if settings.embedding_provider == "nomic":
        try:
            from langchain_nomic import NomicEmbeddings
        except ImportError as exc:
            raise ImportError(
                "embedding_provider='nomic' requires the optional 'langchain-nomic' "
                "package. Install it with: pip install langchain-nomic"
            ) from exc

        return NomicEmbeddings(model=settings.embedding_model_name)

    if settings.embedding_provider == "ollama":
        # Local, no API key: `ollama pull nomic-embed-text` then leave this as default.
        from langchain_ollama import OllamaEmbeddings

        return OllamaEmbeddings(
            model=settings.embedding_model_name,
            base_url=settings.ollama_base_url,
        )

    if settings.embedding_provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=settings.embedding_model_name,
            api_key=settings.openai_api_key,
        )

    raise UnsupportedProviderError(settings.embedding_provider)
