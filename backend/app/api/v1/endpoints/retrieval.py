"""Intelligent Retrieval endpoints (Phase 3.3): the search-first API.

  POST /repositories/{id}/retrieve      -- full pipeline -> RetrievalContext
  POST /repositories/{id}/search        -- search-first response (context)
  POST /repositories/{id}/lookup        -- exact file/function/class/symbol
  GET  /repositories/{id}/suggestions   -- query suggestions for the input box
  GET  /repositories/{id}/history       -- past retrieval runs
  GET  /repositories/{id}/retrieval/metrics -- latency/cache/intent aggregates

Retrieval is deterministic and LLM-free; failures degrade to a clear 503 when
the index/embedding provider is unreachable (same contract as knowledge
search), and history writes are best-effort (never block the response).
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from langchain_core.embeddings import Embeddings
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_embeddings
from app.core.config import get_settings
from app.core.exceptions import RepositoryNotFoundError
from app.models.orm.repository import Repository
from app.models.orm.retrieval import RetrievalQueryRecord
from app.models.schemas.retrieval import (
    LookupRequest,
    LookupResponse,
    QueryHistoryResponse,
    QueryHistoryRecord,
    RetrievalMetricsResponse,
    RetrieveRequest,
    RetrieveResponse,
    SearchResponse,
    SuggestionResponse,
)
from app.services.knowledge.retriever import KnowledgeRetriever
from app.services.retrieval.engine import IntelligentRetriever

logger = logging.getLogger(__name__)

router = APIRouter()

_ENGINES: dict[str, IntelligentRetriever] = {}


def _get_repository_or_404(db: Session, repository_id: uuid.UUID) -> Repository:
    repository = db.get(Repository, repository_id)
    if repository is None:
        raise RepositoryNotFoundError(str(repository_id))
    return repository


def _engine(embeddings: Embeddings) -> IntelligentRetriever:
    key = str(embeddings.__class__.__name__)
    engine = _ENGINES.get(key)
    if engine is None:
        retriever = KnowledgeRetriever(get_settings(), embeddings=embeddings)
        engine = IntelligentRetriever(retriever)
        _ENGINES[key] = engine
    return engine


def _record_history(
    db: Session,
    repository_id: uuid.UUID,
    context,
    latency_ms: float,
    cache_hit: bool,
    mode: str = "auto",
) -> None:
    try:
        db.add(
            RetrievalQueryRecord(
                repository_id=repository_id,
                query=context.query,
                rewritten_query=context.rewritten_query,
                intent=context.intent.value,
                mode=mode,
                latency_ms=latency_ms,
                chunk_count=len(context.chunks),
                cache_hit=cache_hit,
                quality_score=context.confidence,
            )
        )
        db.commit()
    except Exception as exc:  # history must never break retrieval
        db.rollback()
        logger.warning("failed to record retrieval history: %s", exc)


@router.post("/repositories/{repository_id}/retrieve", response_model=RetrieveResponse)
def retrieve(
    repository_id: uuid.UUID,
    payload: RetrieveRequest,
    db: Annotated[Session, Depends(get_db)],
    embeddings: Annotated[Embeddings, Depends(get_embeddings)],
) -> RetrieveResponse:
    _get_repository_or_404(db, repository_id)
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty.")
    if payload.limit < 1 or payload.limit > 50:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 50.")
    try:
        context = _engine(embeddings).retrieve(str(repository_id), payload)
    except Exception as exc:
        logger.warning("retrieve failed for %s: %s", repository_id, exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=(
                "Retrieval is temporarily unavailable -- the embedding provider "
                "or vector index couldn't be reached. Check backend logs."
            ),
        ) from exc
    _record_history(db, repository_id, context, context.metrics.latency_ms, context.metrics.cache_hit, payload.mode.value)
    return RetrieveResponse(context=context)


@router.post("/repositories/{repository_id}/search/intelligent", response_model=SearchResponse)
def search_intelligent(
    repository_id: uuid.UUID,
    payload: RetrieveRequest,
    db: Annotated[Session, Depends(get_db)],
    embeddings: Annotated[Embeddings, Depends(get_embeddings)],
) -> SearchResponse:
    _get_repository_or_404(db, repository_id)
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty.")
    try:
        context = _engine(embeddings).retrieve(str(repository_id), payload)
    except Exception as exc:
        logger.warning("search failed for %s: %s", repository_id, exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=(
                "Search is temporarily unavailable -- the embedding provider "
                "or vector index couldn't be reached. Check backend logs."
            ),
        ) from exc
    _record_history(db, repository_id, context, context.metrics.latency_ms, context.metrics.cache_hit, payload.mode.value)
    return SearchResponse(context=context)


@router.post("/repositories/{repository_id}/lookup", response_model=LookupResponse)
def lookup(
    repository_id: uuid.UUID,
    payload: LookupRequest,
    db: Annotated[Session, Depends(get_db)],
    embeddings: Annotated[Embeddings, Depends(get_embeddings)],
) -> LookupResponse:
    _get_repository_or_404(db, repository_id)
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty.")
    try:
        response = _engine(embeddings).lookup(
            str(repository_id), payload.query, kind=payload.kind, limit=payload.limit
        )
    except Exception as exc:
        logger.warning("lookup failed for %s: %s", repository_id, exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=(
                "Lookup is temporarily unavailable -- the vector index "
                "couldn't be reached. Check backend logs."
            ),
        ) from exc
    return response


@router.get("/repositories/{repository_id}/suggestions", response_model=SuggestionResponse)
def suggestions(
    repository_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    embeddings: Annotated[Embeddings, Depends(get_embeddings)],
    q: str = Query(default="", max_length=120),
) -> SuggestionResponse:
    _get_repository_or_404(db, repository_id)
    try:
        return _engine(embeddings).suggest(str(repository_id), q)
    except Exception as exc:
        logger.warning("suggestions failed for %s: %s", repository_id, exc)
        return SuggestionResponse(query=q, items=[])


@router.get("/repositories/{repository_id}/history", response_model=QueryHistoryResponse)
def history(
    repository_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=20, ge=1, le=100),
) -> QueryHistoryResponse:
    _get_repository_or_404(db, repository_id)
    rows = db.scalars(
        select(RetrievalQueryRecord)
        .where(RetrievalQueryRecord.repository_id == repository_id)
        .order_by(RetrievalQueryRecord.created_at.desc())
        .limit(limit)
    ).all()
    total = db.scalar(
        select(func.count())
        .select_from(RetrievalQueryRecord)
        .where(RetrievalQueryRecord.repository_id == repository_id)
    ) or 0
    return QueryHistoryResponse(
        total=total,
        items=[
            QueryHistoryRecord(
                id=row.id,
                repository_id=row.repository_id,
                query=row.query,
                intent=row.intent,
                mode=row.mode,
                latency_ms=row.latency_ms,
                chunk_count=row.chunk_count,
                cache_hit=row.cache_hit,
                quality_score=row.quality_score,
                created_at=row.created_at,
            )
            for row in rows
        ],
    )


@router.get("/repositories/{repository_id}/retrieval/metrics", response_model=RetrievalMetricsResponse)
def retrieval_metrics(
    repository_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> RetrievalMetricsResponse:
    _get_repository_or_404(db, repository_id)
    base = select(RetrievalQueryRecord).where(RetrievalQueryRecord.repository_id == repository_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    avg_latency = db.scalar(select(func.avg(RetrievalQueryRecord.latency_ms)).where(
        RetrievalQueryRecord.repository_id == repository_id
    )) or 0.0
    cache_hits = db.scalar(select(func.count()).where(
        RetrievalQueryRecord.repository_id == repository_id,
        RetrievalQueryRecord.cache_hit.is_(True),
    )) or 0
    recent = db.scalar(select(func.count()).where(
        RetrievalQueryRecord.repository_id == repository_id,
        RetrievalQueryRecord.created_at
        >= datetime.now(timezone.utc) - timedelta(hours=24),
    )) or 0
    intent_rows = db.execute(
        select(RetrievalQueryRecord.intent, func.count())
        .where(RetrievalQueryRecord.repository_id == repository_id)
        .group_by(RetrievalQueryRecord.intent)
        .order_by(func.count().desc())
        .limit(6)
    ).all()
    return RetrievalMetricsResponse(
        total_queries=total,
        avg_latency_ms=round(float(avg_latency), 2),
        cache_hit_rate=round(cache_hits / total, 4) if total else 0.0,
        top_intents=[{"intent": intent, "count": count} for intent, count in intent_rows],
        recent_24h=recent,
    )
