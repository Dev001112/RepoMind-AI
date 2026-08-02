"""Retrieval services: the deterministic pipeline that turns a user query
into a RetrievalContext. Every stage is independent, observable and unit
testable -- no LLM is involved anywhere in retrieval (the LLM only enriches
knowledge at analysis time; a future agent reasons over the context).

Pipeline: intent.py -> query_rewriter.py -> metadata.py -> planner.py ->
retriever (existing KnowledgeRetriever) -> relationship.py -> reranker.py ->
compressor.py -> builder.py -> engine.py (orchestrator + cache).
"""
