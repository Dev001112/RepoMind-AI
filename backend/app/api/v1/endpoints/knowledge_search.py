"""Semantic Knowledge Index endpoints: search the knowledge, not the files.

  POST /repositories/{id}/search/semantic  -- vector search over knowledge chunks
  POST /repositories/{id}/search/hybrid    -- vector + keyword, RRF-fused
  POST /repositories/{id}/search/context   -- semantic search + related chunks
  GET  /repositories/{id}/chunks           -- page through the whole index
  GET  /repositories/{id}/chunks/{chunk_id} -- one chunk, with its edges
  GET  /repositories/{id}/knowledge/stats  -- explorer header numbers

All reads hit the vector index only -- nothing here re-parses the repository.
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.embeddings import Embeddings
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_embeddings
from app.core.config import Settings, get_settings
from app.core.exceptions import RepositoryNotFoundError
from app.models.orm.repository import Repository
from app.models.schemas.knowledge_chunks import (
    ChunkDetail,
    ChunkListResponse,
    KnowledgeStats,
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from app.services.knowledge.retriever import KnowledgeRetriever

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_repository_or_404(db: Session, repository_id: uuid.UUID) -> Repository:
    repository = db.get(Repository, repository_id)
    if repository is None:
        raise RepositoryNotFoundError(str(repository_id))
    return repository


def _retriever(embeddings: Embeddings) -> KnowledgeRetriever:
    return KnowledgeRetriever(get_settings(), embeddings=embeddings)


def _search(
    retriever: KnowledgeRetriever,
    repository_id: str,
    payload: SemanticSearchRequest,
    mode: str,
) -> SemanticSearchResponse:
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty.")
    try:
        if mode == "semantic":
            results = retriever.semantic_search(
                repository_id, payload.query, filters=payload.filters, limit=payload.limit
            )
        elif mode == "hybrid":
            results = retriever.hybrid_search(
                repository_id, payload.query, filters=payload.filters, limit=payload.limit
            )
        else:
            results = retriever.context_search(
                repository_id, payload.query, filters=payload.filters, limit=payload.limit
            )
    except HTTPException:
        raise
    except Exception as exc:
        # Embedding provider down (ollama not running, key expired, ...) or a
        # Qdrant problem -- better a clear 503 than an opaque 500.
        logger.warning("%s search failed for %s: %s", mode, repository_id, exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=(
                "Search is temporarily unavailable -- the embedding provider or "
                "vector index couldn't be reached. Check backend logs for details."
            ),
        ) from exc
    return SemanticSearchResponse(query=payload.query, results=results)


@router.post("/repositories/{repository_id}/search/semantic", response_model=SemanticSearchResponse)
def semantic_search(
    repository_id: uuid.UUID,
    payload: SemanticSearchRequest,
    db: Annotated[Session, Depends(get_db)],
    embeddings: Annotated[Embeddings, Depends(get_embeddings)],
) -> SemanticSearchResponse:
    _get_repository_or_404(db, repository_id)
    return _search(_retriever(embeddings), str(repository_id), payload, "semantic")


@router.post("/repositories/{repository_id}/search/hybrid", response_model=SemanticSearchResponse)
def hybrid_search(
    repository_id: uuid.UUID,
    payload: SemanticSearchRequest,
    db: Annotated[Session, Depends(get_db)],
    embeddings: Annotated[Embeddings, Depends(get_embeddings)],
) -> SemanticSearchResponse:
    _get_repository_or_404(db, repository_id)
    return _search(_retriever(embeddings), str(repository_id), payload, "hybrid")


@router.post("/repositories/{repository_id}/search/context", response_model=SemanticSearchResponse)
def context_search(
    repository_id: uuid.UUID,
    payload: SemanticSearchRequest,
    db: Annotated[Session, Depends(get_db)],
    embeddings: Annotated[Embeddings, Depends(get_embeddings)],
) -> SemanticSearchResponse:
    _get_repository_or_404(db, repository_id)
    return _search(_retriever(embeddings), str(repository_id), payload, "context")


@router.get("/repositories/{repository_id}/chunks", response_model=ChunkListResponse)
def list_chunks(
    repository_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    chunk_type: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> ChunkListResponse:
    _get_repository_or_404(db, repository_id)
    if page < 1 or page_size < 1 or page_size > 200:
        raise HTTPException(status_code=400, detail="page must be >= 1 and page_size between 1 and 200.")
    items, total = KnowledgeRetriever(get_settings()).list_chunks(
        str(repository_id), chunk_type=chunk_type, page=page, page_size=page_size
    )
    return ChunkListResponse(
        repository_id=repository_id, total=total, page=page, page_size=page_size, items=items
    )


@router.get("/repositories/{repository_id}/chunks/{chunk_id}", response_model=ChunkDetail)
def get_chunk(
    repository_id: uuid.UUID,
    chunk_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> ChunkDetail:
    _get_repository_or_404(db, repository_id)
    detail = KnowledgeRetriever(get_settings()).get_chunk(str(repository_id), chunk_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"chunk '{chunk_id}' not found for this repository.")
    return detail


@router.get("/repositories/{repository_id}/knowledge/stats", response_model=KnowledgeStats)
def knowledge_stats(
    repository_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> KnowledgeStats:
    _get_repository_or_404(db, repository_id)
    stats = KnowledgeRetriever(get_settings()).stats(str(repository_id))
    if stats is None:
        raise HTTPException(
            status_code=404,
            detail="No knowledge indexed yet -- analysis may still be running, or re-run it.",
        )
    return stats
