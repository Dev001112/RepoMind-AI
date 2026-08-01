from fastapi import APIRouter

from app.api.v1.endpoints import (
    analysis,
    chat,
    code_intelligence,
    health,
    knowledge_search,
    repositories,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(repositories.router, tags=["repositories"])
api_router.include_router(analysis.router, tags=["analysis"])
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(code_intelligence.router, tags=["code-intelligence"])
api_router.include_router(knowledge_search.router, tags=["knowledge-search"])
