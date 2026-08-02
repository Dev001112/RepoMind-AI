"""Planner tests: intent/mode -> deterministic retrieval plan."""

from app.models.schemas.retrieval import (
    ExtractedMetadata,
    RetrievalIntent,
    RetrievalPlan,
    SearchMode,
)
from app.services.retrieval.planner import RetrievalPlanner


def test_api_intent_uses_hybrid_and_restricts_types():
    plan = RetrievalPlanner().plan(
        RetrievalIntent.API, ExtractedMetadata(), SearchMode.AUTO
    )
    assert "hybrid" in plan.legs
    assert "api_endpoint" in plan.target_types


def test_exploratory_intents_expand_relationships():
    plan = RetrievalPlanner().plan(
        RetrievalIntent.FEATURE_LOCATION, ExtractedMetadata(), SearchMode.AUTO, expansion_depth=2
    )
    assert "relationship" in plan.legs
    assert plan.expansion_depth >= 1


def test_lookup_intents_run_exact_leg():
    plan = RetrievalPlanner().plan(
        RetrievalIntent.FILE_LOOKUP, ExtractedMetadata(), SearchMode.AUTO
    )
    assert "exact" in plan.legs
    assert "file" in plan.target_types


def test_extracted_metadata_becomes_filters():
    plan = RetrievalPlanner().plan(
        RetrievalIntent.API,
        ExtractedMetadata(type="api_endpoint", framework="flask"),
        SearchMode.AUTO,
    )
    assert plan.filters.type == "api_endpoint"
    assert plan.filters.framework == "flask"


def test_explicit_modes_override_intent():
    plan = RetrievalPlanner().plan(
        RetrievalIntent.API, ExtractedMetadata(), SearchMode.DOCUMENTATION
    )
    assert plan.mode == SearchMode.DOCUMENTATION
    assert "documentation" in plan.target_types
    assert "relationship" not in plan.legs
