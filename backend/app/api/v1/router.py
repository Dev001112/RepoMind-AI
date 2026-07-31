from fastapi import APIRouter

from app.api.v1.endpoints import chat, code_intelligence, health, repositories

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(repositories.router, tags=["repositories"])
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(code_intelligence.router, tags=["code-intelligence"])
