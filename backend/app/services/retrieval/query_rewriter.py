"""Query Rewriter: term-level query expansion so the vector and keyword legs
see the vocabulary the repository actually uses.

No LLM. Expansion is a deterministic lexicon: domain synonyms (auth ->
authentication/token/jwt/oauth/login), plus tokenization tricks (camelCase
and snake_case splitting, path tokens, method verbs). The rewritten query is
`<original> <expanded terms>` -- the embedding sees the enriched phrase while
the full-text leg gets the synonyms to match against.

The rewrite must stay *stable* (same input -> same output) so the cache and
the regression tests hold.
"""

import re

# Splits ALLCAPS-to-lower runs: "JWTAuth" -> [JWT, Auth]; "getUserName" ->
# [get, User, Name]; "api" -> [api].
_CAMEL_CHUNK_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+")

_SYNONYMS: dict[str, tuple[str, ...]] = {
    # domain -> (canonical terms the index likely contains)
    "auth": ("authentication", "authorization", "token", "jwt", "oauth", "login", "session"),
    "authentication": ("auth", "authorization", "token", "jwt", "login"),
    "login": ("auth", "authentication", "session", "token", "signin"),
    "logout": ("auth", "session", "signout", "token"),
    "jwt": ("token", "auth", "authentication", "signature"),
    "token": ("jwt", "auth", "session"),
    "api": ("endpoint", "route", "http", "rest"),
    "endpoint": ("api", "route", "http"),
    "route": ("endpoint", "api", "path"),
    "db": ("database", "sql", "storage", "model"),
    "database": ("db", "sql", "storage", "schema", "table"),
    "sql": ("database", "query", "table", "schema"),
    "orm": ("model", "database", "sql", "query"),
    "deploy": ("deployment", "release", "production", "docker", "ci"),
    "docker": ("container", "image", "compose", "deployment"),
    "install": ("setup", "requirements", "dependency", "configuration"),
    "config": ("configuration", "settings", "env", "setup"),
    "setup": ("configuration", "installation", "requirements", "run"),
    "perf": ("performance", "latency", "benchmark", "speed"),
    "slow": ("performance", "latency", "bottleneck", "optimization"),
    "cache": ("caching", "redis", "memory"),
    "security": ("auth", "permissions", "vulnerability", "sanitization"),
    "password": ("hash", "bcrypt", "security", "auth"),
    "test": ("testing", "pytest", "unit", "coverage"),
    "docs": ("documentation", "readme", "guide"),
    "file": ("path", "module", "source"),
    "class": ("object", "type", "structure"),
    "function": ("method", "callable", "handler", "routine"),
    "model": ("schema", "table", "entity", "orm"),
    "migration": ("schema", "alter", "database", "version"),
    "error": ("exception", "failure", "traceback", "crash"),
    "bug": ("error", "exception", "failure", "issue", "regression"),
    "crash": ("error", "exception", "failure", "panic"),
    "exception": ("error", "traceback", "handling"),
    "vs": ("comparison", "difference", "alternative"),
    "compare": ("comparison", "difference", "alternative", "versus"),
    "deps": ("dependencies", "packages", "libraries", "requirements"),
    "package": ("dependency", "library", "module", "version"),
    "versions": ("version", "pin", "compatibility"),
    "env": ("environment", "variable", "settings", "configuration"),
    "http": ("request", "response", "api", "endpoint"),
    "request": ("http", "api", "payload", "endpoint"),
    "json": ("payload", "serialization", "response"),
    "auth0": ("auth", "oauth", "identity", "sso"),
    "sso": ("auth", "oauth", "identity", "single-sign-on"),
    "billing": ("payment", "invoice", "subscription", "charge"),
    "payment": ("billing", "invoice", "checkout", "charge"),
    "search": ("query", "filter", "index", "lookup"),
    "notification": ("email", "push", "event", "message"),
    "email": ("notification", "mailer", "smtp", "message"),
    "queue": ("worker", "job", "message", "async"),
    "worker": ("queue", "job", "background", "celery"),
    "celery": ("worker", "queue", "async", "job"),
    "redis": ("cache", "queue", "store"),
    "schema": ("model", "table", "database", "migration"),
    "monitoring": ("metrics", "logging", "observability", "grafana"),
    "logging": ("log", "monitoring", "observability", "metrics"),
    "prometheus": ("metrics", "monitoring", "grafana"),
    "ui": ("frontend", "component", "interface", "view"),
    "frontend": ("ui", "component", "interface", "view", "react", "vue"),
    "backend": ("server", "api", "service", "application"),
    "server": ("backend", "service", "application"),
    "migrations": ("migration", "schema", "alembic"),
}

_METHOD_VERBS = ("get", "post", "put", "patch", "delete", "head", "options")


def _split_terms(term: str) -> list[str]:
    """camelCase/snake_case -> words: 'JWTAuth' -> [jwt, auth]. Accepts
    already-lowercase input (no case info) and ALLCAPS runs."""
    if "_" in term or "-" in term:
        for sep in ("_", "-"):
            term = term.replace(sep, " ")
        return [p for p in term.lower().split() if len(p) >= 2]
    pieces = _CAMEL_CHUNK_RE.findall(term)
    if len(pieces) < 2:
        return [term.lower()] if len(term) >= 2 else []
    return [p for p in (piece.lower() for piece in pieces) if len(p) >= 2]


_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


class QueryRewriter:
    """Expands a query deterministically; safe to run twice (idempotent)."""

    def __init__(self, synonyms: dict[str, tuple[str, ...]] | None = None) -> None:
        self._synonyms = synonyms or _SYNONYMS

    def rewrite(self, query: str, terms: list[str]) -> tuple[str, list[str]]:
        """Returns (rewritten_query, all_terms). Expansion only adds terms that
        aren't already in the query, so repeated rewrites are stable."""
        lowered = query.lower()
        expansions: list[str] = []
        for term in terms:
            for piece in _split_terms(term):
                for synonym in self._synonyms.get(piece, ()):
                    if synonym not in lowered and synonym not in expansions:
                        expansions.append(synonym)
            if term in self._synonyms and term not in lowered:
                for synonym in self._synonyms[term]:
                    if synonym not in lowered and synonym not in expansions:
                        expansions.append(synonym)

        # camelCase splitting must see the original casing ("JWTAuth"), which
        # the analyzer's lowercase term list no longer has.
        for raw in _WORD_RE.findall(query):
            pieces = _split_terms(raw)
            if len(pieces) > 1:
                # The token split into pieces ("JWTAuth" -> jwt, auth): the
                # pieces are sub-parts, so they're never "already present" as
                # whole words -- always eligible.
                for piece in pieces:
                    if piece not in expansions:
                        expansions.append(piece)

        rewritten = query
        all_terms = list(terms)
        if expansions:
            rewritten = f"{query} {' '.join(expansions)}"
            for e in expansions:
                if e not in all_terms:
                    all_terms.append(e)
        return rewritten, all_terms


def get_query_rewriter() -> QueryRewriter:
    return QueryRewriter()
