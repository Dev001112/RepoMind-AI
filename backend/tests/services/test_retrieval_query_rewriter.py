"""Query Rewriter tests: deterministic, idempotent, domain-aware expansion."""

from app.services.retrieval.query_rewriter import QueryRewriter


def test_expands_domain_synonyms():
    rewriter = QueryRewriter()
    rewritten, terms = rewriter.rewrite("how does auth work", ["auth", "work"])
    assert "authentication" in rewritten
    assert "jwt" in rewritten
    assert "login" in rewritten
    assert set(terms) >= {"auth", "work", "authentication", "jwt"}


def test_does_not_duplicate_terms_already_present():
    rewriter = QueryRewriter()
    rewritten, _ = rewriter.rewrite("authentication token flow", ["authentication", "token", "flow"])
    assert rewritten.count("authentication") == 1
    assert rewritten.count("token") == 1


def test_rewrite_is_idempotent():
    rewriter = QueryRewriter()
    first, _ = rewriter.rewrite("database model", ["database", "model"])
    second, _ = rewriter.rewrite("database model", ["database", "model"])
    assert first == second


def test_splits_camel_case_terms():
    rewriter = QueryRewriter()
    _, terms = rewriter.rewrite("JWTAuth", ["jwtauth"])
    assert "jwt" in terms
    assert "auth" in terms


def test_unknown_terms_pass_through():
    rewriter = QueryRewriter()
    rewritten, terms = rewriter.rewrite("floop zorp", ["floop", "zorp"])
    assert rewritten == "floop zorp"
    assert terms == ["floop", "zorp"]
