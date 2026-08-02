"""Filters: merge the metadata extractor's findings with any explicit request
filters into the single ChunkFilters the retriever applies.

Explicit filters win over extracted ones (the caller knows better); empty
values are dropped so they never narrow a search by accident.
"""

from app.models.schemas.knowledge_chunks import ChunkFilters
from app.models.schemas.retrieval import ExtractedMetadata


class FilterBuilder:
    def build(
        self,
        extracted: ExtractedMetadata,
        explicit: ChunkFilters | None = None,
    ) -> ChunkFilters:
        explicit = explicit or ChunkFilters()
        merged = ChunkFilters(
            type=explicit.type or extracted.type,
            language=explicit.language or extracted.language,
            framework=explicit.framework or extracted.framework,
            directory=explicit.directory or extracted.directory,
            file=explicit.file or extracted.file,
        )
        return _prune(merged)


def _prune(filters: ChunkFilters) -> ChunkFilters:
    for field in ("type", "language", "framework", "directory", "file"):
        value = getattr(filters, field)
        if value is not None and not str(value).strip():
            setattr(filters, field, None)
    return filters


def get_filter_builder() -> FilterBuilder:
    return FilterBuilder()
