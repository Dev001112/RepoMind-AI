"""Deep code understanding: semantic search, explain a symbol/module, and
browse a specific file's content + extracted symbols.

All three read directly from the chunks already embedded during analysis
(via app.services.repository.analysis_pipeline) -- nothing here re-parses
the repository.
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import Runnable
from langchain_qdrant import QdrantVectorStore
from qdrant_client.models import FieldCondition, Filter, MatchValue
from sqlalchemy.orm import Session

from app.ai.prompts.explain_prompt import EXPLAIN_PROMPT
from app.ai.vectorstore.qdrant_store import get_qdrant_client, scroll_chunks
from app.api.deps import get_chat_model, get_db, get_vectorstore
from app.core.config import get_settings
from app.core.exceptions import RepositoryNotFoundError
from app.models.orm.repository import Repository
from app.models.schemas.code_intelligence import (
    ExplainRequest,
    ExplainResponse,
    FileDetailResponse,
    FileSymbol,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from app.utils.file_utils import safe_join

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_repository_or_404(db: Session, repository_id: uuid.UUID) -> Repository:
    repository = db.get(Repository, repository_id)
    if repository is None:
        raise RepositoryNotFoundError(str(repository_id))
    return repository


@router.post("/repositories/{repository_id}/search", response_model=SearchResponse)
def search_repository(
    repository_id: uuid.UUID,
    payload: SearchRequest,
    db: Annotated[Session, Depends(get_db)],
    vectorstore: Annotated[QdrantVectorStore, Depends(get_vectorstore)],
) -> SearchResponse:
    """Semantic code search -- direct vector similarity, no LLM involved. Fast,
    free, and not subject to any provider's rate limit."""
    _get_repository_or_404(db, repository_id)

    qdrant_filter = Filter(
        must=[FieldCondition(key="metadata.repository_id", match=MatchValue(value=str(repository_id)))]
    )
    hits = vectorstore.similarity_search_with_score(
        payload.query, k=payload.limit, filter=qdrant_filter
    )

    results = [
        SearchResult(
            file_path=doc.metadata.get("file_path", ""),
            start_line=doc.metadata.get("start_line", 0),
            end_line=doc.metadata.get("end_line", 0),
            language=doc.metadata.get("language", ""),
            symbol_name=doc.metadata.get("symbol_name"),
            snippet=doc.page_content[:500],
            score=score,
        )
        for doc, score in hits
    ]
    return SearchResponse(results=results)


@router.post("/repositories/{repository_id}/explain", response_model=ExplainResponse)
def explain_target(
    repository_id: uuid.UUID,
    payload: ExplainRequest,
    db: Annotated[Session, Depends(get_db)],
    vectorstore: Annotated[QdrantVectorStore, Depends(get_vectorstore)],
    llm: Annotated[Runnable[LanguageModelInput, BaseMessage], Depends(get_chat_model)],
) -> ExplainResponse:
    """Explain a specific function/class (exact symbol match) or file (exact
    path match -> the whole module); falls back to semantic search on the
    target text if neither matches anything embedded."""
    _get_repository_or_404(db, repository_id)

    settings = get_settings()
    client = get_qdrant_client()
    repo_id_str = str(repository_id)
    # Stored file_path is always forward-slash (see chunk_builder.py) -- normalize in
    # case the caller sent a Windows-style path or copied one straight from a UI.
    target = payload.target.replace("\\", "/")

    chunks = scroll_chunks(client, settings, repo_id_str, file_path=target)
    if not chunks:
        chunks = scroll_chunks(client, settings, repo_id_str, symbol_name=target)

    if chunks:
        context = "\n\n".join(c["page_content"] for c in chunks)
        sources = sorted({c["metadata"].get("file_path", "") for c in chunks} - {""})
    else:
        qdrant_filter = Filter(
            must=[
                FieldCondition(
                    key="metadata.repository_id", match=MatchValue(value=repo_id_str)
                )
            ]
        )
        docs = vectorstore.similarity_search(target, k=5, filter=qdrant_filter)
        context = "\n\n".join(doc.page_content for doc in docs)
        sources = sorted({doc.metadata.get("file_path", "") for doc in docs} - {""})

    if not context:
        return ExplainResponse(
            target=payload.target,
            explanation=(
                f'Nothing embedded for this repository matches "{payload.target}" -- '
                "check the exact function/class name or file path, or make sure "
                "analysis has finished."
            ),
            sources=[],
        )

    chain = EXPLAIN_PROMPT | llm | StrOutputParser()
    explanation = chain.invoke({"target": payload.target, "context": context})
    return ExplainResponse(target=payload.target, explanation=explanation, sources=sources)


@router.get("/repositories/{repository_id}/files/{file_path:path}", response_model=FileDetailResponse)
def get_file_detail(
    repository_id: uuid.UUID,
    file_path: str,
    db: Annotated[Session, Depends(get_db)],
) -> FileDetailResponse:
    """Browse a single file: its raw content plus the symbols (functions/
    classes) extracted from it during analysis, for a code-navigation view."""
    repository = _get_repository_or_404(db, repository_id)

    if not repository.local_path:
        raise HTTPException(status_code=404, detail="Repository hasn't been cloned/analyzed yet.")

    # Stored file_path (and safe_join, on a non-Windows deployment) both expect
    # forward slashes -- normalize in case the caller sent a Windows-style path.
    file_path = file_path.replace("\\", "/")

    try:
        target = safe_join(repository.local_path, file_path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path.") from None

    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"'{file_path}' not found in this repository.")

    content = target.read_text(encoding="utf-8", errors="replace")

    settings = get_settings()
    client = get_qdrant_client()
    chunks = scroll_chunks(client, settings, str(repository_id), file_path=file_path)
    symbols = [
        FileSymbol(
            symbol_name=c["metadata"]["symbol_name"],
            start_line=c["metadata"]["start_line"],
            end_line=c["metadata"]["end_line"],
        )
        for c in chunks
        if c.get("metadata", {}).get("symbol_name")
    ]
    language = chunks[0]["metadata"].get("language") if chunks else None

    return FileDetailResponse(path=file_path, content=content, language=language, symbols=symbols)
