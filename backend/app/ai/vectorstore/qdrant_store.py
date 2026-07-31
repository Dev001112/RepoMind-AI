"""Qdrant client + LangChain vectorstore wiring. Real, working plumbing."""

from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, VectorParams

from app.core.config import Settings, get_settings

_settings = get_settings()

# Process-wide singleton (mirrors app.database.session.engine). Required for embedded/
# local mode: the on-disk storage takes an exclusive lock, so a fresh QdrantClient(path=...)
# per request (e.g. via FastAPI Depends) would fail on the second concurrent request.
_client = (
    QdrantClient(url=_settings.qdrant_url, api_key=_settings.qdrant_api_key)
    if _settings.qdrant_url
    else QdrantClient(path=_settings.qdrant_local_path)
)


def get_qdrant_client() -> QdrantClient:
    return _client


def ensure_collection(client: QdrantClient, settings: Settings, vector_size: int) -> None:
    """Create the configured collection if it doesn't already exist.

    Raises a clear error if it already exists with a DIFFERENT vector size
    (e.g. EMBEDDING_PROVIDER was switched between analysis runs) -- otherwise
    that mismatch only surfaces as an opaque qdrant-client error deep inside
    add_texts(), on every repository, since the collection name is shared.
    """
    try:
        info = client.get_collection(settings.qdrant_collection_name)
    except (UnexpectedResponse, ValueError):
        client.create_collection(
            collection_name=settings.qdrant_collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        return

    existing_size = info.config.params.vectors.size
    if existing_size != vector_size:
        raise ValueError(
            f"Qdrant collection '{settings.qdrant_collection_name}' already exists with "
            f"vector size {existing_size}, but the configured embedding provider produces "
            f"{vector_size}-dim vectors. Either switch EMBEDDING_PROVIDER back, or set a "
            "different QDRANT_COLLECTION_NAME to start a fresh collection."
        )


def get_vectorstore(settings: Settings, embeddings: Embeddings) -> QdrantVectorStore:
    return QdrantVectorStore(
        client=get_qdrant_client(),
        collection_name=settings.qdrant_collection_name,
        embedding=embeddings,
    )


def scroll_chunks(
    client: QdrantClient,
    settings: Settings,
    repository_id: str,
    *,
    file_path: str | None = None,
    symbol_name: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Exact-filter lookup (not vector search) -- e.g. "every chunk from this
    file" or "every chunk named exactly this" for explain/navigation, where an
    exact match is more reliable than similarity search alone. Returns raw
    payloads: [{"page_content": ..., "metadata": {...}}, ...]."""
    must = [FieldCondition(key="metadata.repository_id", match=MatchValue(value=repository_id))]
    if file_path is not None:
        must.append(FieldCondition(key="metadata.file_path", match=MatchValue(value=file_path)))
    if symbol_name is not None:
        must.append(FieldCondition(key="metadata.symbol_name", match=MatchValue(value=symbol_name)))

    try:
        points, _ = client.scroll(
            collection_name=settings.qdrant_collection_name,
            scroll_filter=Filter(must=must),
            limit=limit,
            with_payload=True,
        )
    except (UnexpectedResponse, ValueError):
        return []  # collection doesn't exist yet -- nothing analyzed
    return [point.payload for point in points]
