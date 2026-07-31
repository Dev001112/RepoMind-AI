"""Repository Q&A endpoint -- wires the retriever + LLM into the chat graph."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from langchain_qdrant import QdrantVectorStore
from sqlalchemy.orm import Session

from app.ai.langgraph.graph import build_graph
from app.ai.retriever.repository_retriever import get_repository_retriever
from app.api.deps import get_chat_model, get_db, get_vectorstore
from app.core.exceptions import RepositoryNotFoundError
from app.models.orm.knowledge import RepositoryKnowledge as RepositoryKnowledgeORM
from app.models.orm.repository import Repository
from app.models.schemas.chat import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def _build_known_facts(knowledge: RepositoryKnowledgeORM | None) -> str:
    """Compact summary of what's already been deterministically detected/summarized
    -- given to the general chat lens so it doesn't have to guess "what is this
    project for" purely from whatever a similarity search happens to retrieve."""
    if knowledge is None:
        return "No analysis summary available yet."
    return "\n".join(
        [
            f"Name: {knowledge.name or 'unknown'}",
            f"Description: {knowledge.description or 'none given'}",
            f"Type: {knowledge.repository_type or 'unknown'}",
            f"Languages: {', '.join(knowledge.languages or []) or 'none detected'}",
            f"Frameworks: {', '.join(knowledge.frameworks or []) or 'none detected'}",
            f"Use cases: {'; '.join(knowledge.use_cases or []) or 'none determined'}",
            "Potential applications: "
            + ("; ".join(knowledge.potential_applications or []) or "none determined"),
        ]
    )


@router.post("/repositories/{repository_id}/chat", response_model=ChatResponse)
def chat_with_repository(
    repository_id: uuid.UUID,
    payload: ChatRequest,
    db: Annotated[Session, Depends(get_db)],
    vectorstore: Annotated[QdrantVectorStore, Depends(get_vectorstore)],
    llm: Annotated[Runnable[LanguageModelInput, BaseMessage], Depends(get_chat_model)],
) -> ChatResponse:
    repository = db.get(Repository, repository_id)
    if repository is None:
        raise RepositoryNotFoundError(str(repository_id))

    knowledge = (
        db.query(RepositoryKnowledgeORM)
        .filter(RepositoryKnowledgeORM.repository_id == repository_id)
        .first()
    )

    retriever = get_repository_retriever(vectorstore, str(repository_id))
    graph = build_graph(retriever, llm)
    try:
        result = graph.invoke(
            {
                "question": payload.question,
                "known_facts": _build_known_facts(knowledge),
                "security_findings": (knowledge.security_findings if knowledge else None) or [],
                "architecture_summary": (knowledge.architecture_summary if knowledge else None)
                or "",
            }
        )
    except Exception as exc:
        # Nothing logged this before -- a provider outage/quota error (primary AND
        # fallback, `with_fallbacks` only surfaces the FIRST provider's exception,
        # so this won't show OpenRouter's specific failure reason if Gemini's is
        # what's re-raised) was previously an opaque 500 with zero trace in the logs.
        logger.exception(
            "Chat failed for repository %s (all configured LLM providers may have failed)",
            repository_id,
        )
        raise HTTPException(
            status_code=502,
            detail="Couldn't reach an LLM provider to answer that -- check backend logs for details.",
        ) from exc
    return ChatResponse(answer=result["answer"], sources=result.get("sources", []))
