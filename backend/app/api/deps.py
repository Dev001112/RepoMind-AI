"""FastAPI dependency providers.

Plain factory functions used with `Depends(...)` -- this is our DI system,
no container library needed.
"""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from langchain_qdrant import QdrantVectorStore
from sqlalchemy.orm import Session

from app.ai.embeddings.factory import get_embeddings as _get_embeddings
from app.ai.llm.factory import get_chat_model as _get_chat_model
from app.ai.vectorstore.qdrant_store import get_vectorstore as _get_vectorstore
from app.core.config import Settings, get_settings
from app.database.session import get_db as _get_db


def get_db() -> Generator[Session, None, None]:
    yield from _get_db()


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_chat_model(settings: SettingsDep) -> Runnable[LanguageModelInput, BaseMessage]:
    return _get_chat_model(settings)


def get_embeddings(settings: SettingsDep) -> Embeddings:
    return _get_embeddings(settings)


def get_vectorstore(
    settings: SettingsDep,
    embeddings: Annotated[Embeddings, Depends(get_embeddings)],
) -> QdrantVectorStore:
    return _get_vectorstore(settings, embeddings)
