"""Request/response schemas for the code-search / explain / navigation
endpoints -- "Deep Code Understanding" (semantic search, explain a symbol or
module, browse a file's structure) on top of the chunks already embedded
during analysis.
"""

from app.models.schemas.base import CamelModel


class SearchRequest(CamelModel):
    query: str
    limit: int = 10


class SearchResult(CamelModel):
    file_path: str
    start_line: int
    end_line: int
    language: str
    symbol_name: str | None = None
    snippet: str
    score: float


class SearchResponse(CamelModel):
    results: list[SearchResult]


class ExplainRequest(CamelModel):
    # A function/class name (exact match against extracted symbols) or a
    # repo-relative file path (exact match -> explains the whole file/module).
    # Falls back to semantic search over the target text if neither matches.
    target: str


class ExplainResponse(CamelModel):
    target: str
    explanation: str
    sources: list[str]


class FileSymbol(CamelModel):
    symbol_name: str
    start_line: int
    end_line: int


class FileDetailResponse(CamelModel):
    path: str
    content: str
    language: str | None = None
    symbols: list[FileSymbol]
