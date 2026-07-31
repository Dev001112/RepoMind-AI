"""LangGraph orchestration for repository chat.

Classifies the question, retrieves scoped context, then routes to a
category-specific prompt (general / security / architecture) -- each a
different lens over the same retrieved code and already-known facts, not a
separate agent with its own tools. Real multi-agent tool-use (a security
agent that can run its own scans on demand, etc.) is a later phase; this is
the first actual use of LangGraph beyond the Phase 1 placeholder passthrough.

Classification is a fast keyword match, not an LLM call -- deterministic
where possible is the same principle the detectors follow; the LLM call is
reserved for the part that actually needs judgment (the answer itself).
"""

import re
from typing import TypedDict

from langchain_core.documents import Document
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import Runnable
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.ai.prompts.architecture_qa_prompt import ARCHITECTURE_QA_PROMPT
from app.ai.prompts.repository_qa_prompt import REPOSITORY_QA_PROMPT
from app.ai.prompts.security_review_prompt import SECURITY_REVIEW_PROMPT

# Word-boundary regex, not bare substrings -- a plain `in` check false-positives
# on common unrelated words/phrases: "auth" inside "author", "risk" inside
# "asterisk", bare "injection" inside "dependency injection" (same class of bug
# as the "jax"-inside-"AJAX" false positive found in cuda_detector.py).
_SECURITY_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"\bsecurity\b",
        r"\bvulnerab\w*\b",
        r"\bsecrets?\b",
        r"\bcve\b",
        r"\bexploits?\b",
        r"\b(?:sql|code|command)\s+injection\b",
        r"\binjection\s+attack\b",
        r"\bauth(?!or)\w*\b",  # authentication/authorize/auth, but not author(s|ed)
        r"\bpasswords?\b",
        r"\bcredentials?\b",
        r"\bunsafe\b",
        r"\brisks?\b",
        r"\battacks?\b",
    )
]
_ARCHITECTURE_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"\barchitecture\b",
        r"\bstructur\w*\b",
        r"\bdesign\w*\b",
        r"\borganiz\w*\b",
        r"\bmodules?\b",
        r"\bfolders?\b",
        r"\blayout\b",
        r"\blayered\b",
        r"\bcomponents?\b",
    )
]


class ChatState(TypedDict):
    question: str
    category: str
    context: str
    sources: list[str]
    known_facts: str
    security_findings: list[str]
    architecture_summary: str
    answer: str


def _classify(state: ChatState) -> dict:
    lower = state["question"].lower()
    if any(pattern.search(lower) for pattern in _SECURITY_PATTERNS):
        return {"category": "security"}
    if any(pattern.search(lower) for pattern in _ARCHITECTURE_PATTERNS):
        return {"category": "architecture"}
    return {"category": "general"}


def _route_by_category(state: ChatState) -> str:
    return state["category"]


def _format_docs(docs: list[Document]) -> tuple[str, list[str]]:
    context = "\n\n".join(doc.page_content for doc in docs)
    sources = sorted({doc.metadata.get("file_path", "") for doc in docs} - {""})
    return context, sources


def build_graph(
    retriever: BaseRetriever,
    llm: Runnable[LanguageModelInput, BaseMessage],
) -> CompiledStateGraph:
    parser = StrOutputParser()

    def retrieve(state: ChatState) -> dict:
        docs = retriever.invoke(state["question"])
        context, sources = _format_docs(docs)
        return {"context": context, "sources": sources}

    def generate_general(state: ChatState) -> dict:
        known_facts = state.get("known_facts") or "No analysis summary available yet."
        chain = REPOSITORY_QA_PROMPT | llm | parser
        answer = chain.invoke(
            {
                "context": state["context"],
                "question": state["question"],
                "known_facts": known_facts,
            }
        )
        return {"answer": answer}

    def generate_security(state: ChatState) -> dict:
        findings = state.get("security_findings") or []
        findings_text = "\n".join(f"- {f}" for f in findings) or "None flagged by static analysis."
        chain = SECURITY_REVIEW_PROMPT | llm | parser
        answer = chain.invoke(
            {
                "context": state["context"],
                "question": state["question"],
                "findings": findings_text,
            }
        )
        return {"answer": answer}

    def generate_architecture(state: ChatState) -> dict:
        summary = state.get("architecture_summary") or "No architecture summary available yet."
        chain = ARCHITECTURE_QA_PROMPT | llm | parser
        answer = chain.invoke(
            {
                "context": state["context"],
                "question": state["question"],
                "summary": summary,
            }
        )
        return {"answer": answer}

    graph = StateGraph(ChatState)
    graph.add_node("classify", _classify)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate_general", generate_general)
    graph.add_node("generate_security", generate_security)
    graph.add_node("generate_architecture", generate_architecture)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "retrieve")
    graph.add_conditional_edges(
        "retrieve",
        _route_by_category,
        {
            "security": "generate_security",
            "architecture": "generate_architecture",
            "general": "generate_general",
        },
    )
    graph.add_edge("generate_general", END)
    graph.add_edge("generate_security", END)
    graph.add_edge("generate_architecture", END)

    return graph.compile()
