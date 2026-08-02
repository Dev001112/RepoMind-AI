"""Intent Analyzer tests: deterministic classification of the 16 intents."""

from app.models.schemas.retrieval import RetrievalIntent
from app.services.retrieval.intent import IntentAnalyzer


def test_security_query_is_security():
    analysis = IntentAnalyzer().analyze("how does authentication with JWT tokens work?")
    assert analysis.primary_intent == RetrievalIntent.SECURITY
    intents = {m.intent for m in analysis.intents}
    assert RetrievalIntent.EXPLANATION in intents or RetrievalIntent.FEATURE_LOCATION in intents


def test_database_query_is_database():
    analysis = IntentAnalyzer().analyze("what database and ORM does this project use?")
    assert analysis.primary_intent == RetrievalIntent.DATABASE
    assert analysis.intents[0].score > 0


def test_api_query_is_api():
    analysis = IntentAnalyzer().analyze("show me the POST /login endpoint and its request format")
    assert analysis.primary_intent == RetrievalIntent.API
    assert analysis.intents[0].score > 0


def test_setup_query_is_setup():
    analysis = IntentAnalyzer().analyze("how do I install the dependencies and run it locally?")
    assert analysis.primary_intent == RetrievalIntent.SETUP


def test_bug_query_is_bug_investigation():
    analysis = IntentAnalyzer().analyze("login fails with a 500 error, why is it broken?")
    assert analysis.primary_intent == RetrievalIntent.BUG_INVESTIGATION


def test_comparison_query_is_comparison():
    analysis = IntentAnalyzer().analyze("what is the difference between Flask and FastAPI here?")
    assert analysis.primary_intent == RetrievalIntent.COMPARISON


def test_file_lookup_detects_paths():
    analysis = IntentAnalyzer().analyze("where is the file api/auth.py?")
    assert analysis.primary_intent == RetrievalIntent.FILE_LOOKUP


def test_architecture_query_is_architecture():
    analysis = IntentAnalyzer().analyze("what is the overall architecture and folder structure?")
    assert analysis.primary_intent == RetrievalIntent.ARCHITECTURE


def test_documentation_query_is_documentation():
    analysis = IntentAnalyzer().analyze("is there a readme or usage example for this?")
    assert analysis.primary_intent == RetrievalIntent.DOCUMENTATION


def test_unknown_query_falls_back_to_explanation():
    analysis = IntentAnalyzer().analyze("zzz zqx")
    assert analysis.primary_intent == RetrievalIntent.EXPLANATION
    assert analysis.intents[0].score >= 0.05


def test_scores_are_bounded_and_ordered():
    analysis = IntentAnalyzer().analyze("how does authentication with JWT tokens work?")
    assert all(0.0 <= m.score <= 1.0 for m in analysis.intents)
    scores = [m.score for m in analysis.intents]
    assert scores == sorted(scores, reverse=True)
