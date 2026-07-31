"""Pydantic schemas for the repository chat/RAG endpoint."""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[str] = []
