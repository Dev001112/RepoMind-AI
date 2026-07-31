"""Custom application exceptions and their FastAPI exception handlers."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class RepositoryNotFoundError(Exception):
    """Raised when a repository id doesn't exist in the database."""

    def __init__(self, repository_id: str) -> None:
        self.repository_id = repository_id
        super().__init__(f"Repository '{repository_id}' not found")


class UnsupportedProviderError(Exception):
    """Raised when an llm/embedding provider name isn't one we know how to build."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"Unsupported provider: '{provider}'")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RepositoryNotFoundError)
    async def _repository_not_found_handler(
        request: Request, exc: RepositoryNotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(UnsupportedProviderError)
    async def _unsupported_provider_handler(
        request: Request, exc: UnsupportedProviderError
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
