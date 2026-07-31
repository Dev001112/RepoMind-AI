"""Thin helper to scope vectorstore retrieval to a single repository."""

from langchain_core.retrievers import BaseRetriever
from langchain_qdrant import QdrantVectorStore
from qdrant_client.models import FieldCondition, Filter, MatchValue


def get_repository_retriever(
    vectorstore: QdrantVectorStore, repository_id: str
) -> BaseRetriever:
    """Return a retriever that only searches chunks tagged with this repository_id.

    Assumes chunks were upserted with `metadata={"repository_id": ...}`.
    """
    qdrant_filter = Filter(
        must=[
            FieldCondition(
                key="metadata.repository_id",
                match=MatchValue(value=repository_id),
            )
        ]
    )
    return vectorstore.as_retriever(search_kwargs={"filter": qdrant_filter})
