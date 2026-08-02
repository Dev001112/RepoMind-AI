"""Intent Analyzer: deterministic lexicon/pattern classification of a query
into the 16 supported intents.

Pure rules -- no LLM, no external calls. A query may match several intents;
they come back ranked, and the planner uses the primary one. Scores are the
fraction of the query's tokens that matched the intent's lexicon, weighted
so a question-phrase ("how does ... work") or an exact symbol hit outranks
a lone dictionary word.
"""

import re
import uuid
from dataclasses import dataclass, field

from app.models.schemas.retrieval import IntentMatch, RetrievalIntent, QueryAnalysis

_TOKEN_RE = re.compile(r"[a-z0-9_]{2,}")
_QUESTION_RE = re.compile(
    r"\b(what|why|how|which|who|where|when|does|do|is|are|can|give|tell|list|show)\b"
)


def _stem(token: str) -> str:
    """Cheap plural fold: 'tokens' -> 'token', 'errors' -> 'error'."""
    return token[:-1] if token.endswith("s") and len(token) > 3 else token


@dataclass
class _IntentSpec:
    intent: RetrievalIntent
    words: set[str] = field(default_factory=set)
    phrases: set[str] = field(default_factory=set)
    patterns: list[re.Pattern] = field(default_factory=list)


_WORD_LEXICON: dict[RetrievalIntent, set[str]] = {
    RetrievalIntent.ARCHITECTURE: {
        "architecture", "architect", "structure", "design", "layer", "layer",
        "modules", "organiz", "topology", "layout", "diagram", "overview",
        "component", "system", "stack", "folders", "directory", "dir",
    },
    RetrievalIntent.EXPLANATION: {
        "explain", "meaning", "understand", "purpose", "behavior", "behaviour",
        "work", "works", "how", "what", "why", "concept", "detail", "details",
        "overview",
    },
    RetrievalIntent.SETUP: {
        "setup", "set-up", "install", "installer", "installation", "configure",
        "configuring", "run", "running", "start", "startup", "local", "env",
        "environment", "init", "bootstrap", "quickstart", "getting-started",
        "prerequisite", "requirements", "dependency",
    },
    RetrievalIntent.DEPLOYMENT: {
        "deploy", "deployment", "release", "ci", "cd", "pipeline", "build",
        "docker", "compose", "container", "image", "kubernetes", "k8s",
        "helm", "production", "staging", "prod", "cloud", "aws", "gcp",
        "azure", "heroku", "vercel", "nginx", "gunicorn", "uvicorn", "systemd",
    },
    RetrievalIntent.API: {
        "api", "endpoint", "endpoints", "route", "routes", "http", "rest",
        "restful", "request", "requests", "response", "responses", "payload",
        "json", "status-code", "status", "get", "post", "put", "patch",
        "delete", "auth-header", "header", "middleware", "serializer",
        "swagger", "openapi", "graphql", "grpc",
    },
    RetrievalIntent.DATABASE: {
        "database", "db", "sql", "postgres", "postgresql", "mysql", "sqlite",
        "mongo", "redis", "elasticsearch", "table", "tables", "schema",
        "migration", "migrations", "orm", "alchemy", "model", "models",
        "query", "queries", "index", "indexes", "query-set", "queryset",
        "seed", "cursor", "transaction", "key", "foreign",
    },
    RetrievalIntent.SECURITY: {
        "security", "secure", "auth", "authentication", "authorization",
        "authorise", "authorize", "login", "signin", "sign-in", "logout",
        "signout", "sign-out", "jwt", "token", "tokens", "oauth", "oauth2",
        "session", "cookie", "password", "hash", "bcrypt", "csrf", "cors",
        "permission", "permissions", "role", "roles", "rbac", "vulnerab",
        "injection", "xss", "sanitize", "rate-limit", "throttle", "firewall",
    },
    RetrievalIntent.PERFORMANCE: {
        "performance", "performant", "slow", "slower", "latency", "throughput",
        "optimize", "optimise", "optimization", "optimisation", "benchmark",
        "caching", "cache", "async", "concurrency", "parallel", "pool",
        "memory", "leak", "bottleneck", "profile", "profiling", "speed",
        "fast", "efficient", "indexed",
    },
    RetrievalIntent.DEPENDENCIES: {
        "dependency", "dependencies", "package", "packages", "library",
        "libraries", "version", "versions", "requirements", "pip", "npm",
        "yarn", "poetry", "gem", "cargo", "go-mod", "maven", "gradle",
        "plugin", "plugin", "third-party", "vendored", "lockfile", "lock",
        "compatib", "upgrade", "downgrade", "pin", "pinned",
    },
    RetrievalIntent.DOCUMENTATION: {
        "documentation", "docs", "docstring", "readme", "guide", "guides",
        "tutorial", "tutorials", "manual", "wiki", "comment", "comments",
        "sample", "example", "examples", "usage", "how-to", "faq", "changelog",
    },
    RetrievalIntent.FILE_LOOKUP: {
        "file", "files", "folder", "folder", "path", "paths", "location",
        "locate", "where", "find", "named", "called", "directory", "dir",
        "root", "module", "package",
    },
    RetrievalIntent.FUNCTION_LOOKUP: {
        "function", "functions", "method", "methods", "call", "calls",
        "signature", "params", "parameters", "argument", "arguments",
        "return", "returns", "callback", "handler", "helper", "utility",
        "util", "decorator", "async-function", "coroutine",
    },
    RetrievalIntent.CLASS_LOOKUP: {
        "class", "classes", "object", "objects", "instance", "constructor",
        "inheritance", "subclass", "abstract", "interface", "type", "types",
        "enum", "generic", "dataclass", "base-class", "super",
    },
    RetrievalIntent.COMPARISON: {
        "compare", "comparison", "vs", "versus", "difference", "differences",
        "between", "better", "best", "prefer", "preferred", "trade-off",
        "tradeoffs", "alternative", "alternatives", "instead-of", "either",
        "which", "choose", "choice",
    },
    RetrievalIntent.BUG_INVESTIGATION: {
        "bug", "bugs", "error", "errors", "exception", "exceptions", "crash",
        "crashes", "fails", "failure", "failures", "broken", "issue", "issues",
        "fix", "fixing", "debug", "debugging", "traceback", "stack-trace",
        "stacktrace", "hang", "freeze", "stuck", "not-working", "wrong",
        "misbehav", "inconsistent", "race", "deadlock", "unhandled",
    },
    RetrievalIntent.FEATURE_LOCATION: {
        "feature", "implement", "implemented", "implementation", "support",
        "supported", "where-is", "find", "locate", "handles", "handled",
        "responsible", "manages", "built", "built-in", "exists", "added",
        "feature-flag", "search",
    },
}

_PHRASE_LEXICON: dict[RetrievalIntent, set[str]] = {
    RetrievalIntent.ARCHITECTURE: {
        "how is the project structured", "project structure", "system design",
        "how is it organized", "directory structure", "what architecture",
    },
    RetrievalIntent.EXPLANATION: {
        "explain how", "explain what", "explain why", "what does it mean",
        "what is the purpose", "what is the meaning", "in detail",
    },
    RetrievalIntent.SETUP: {
        "get started", "getting started", "set up", "how to install",
        "how do i run", "how to run", "how do i set up", "run locally",
        "setup guide", "development setup",
    },
    RetrievalIntent.DEPLOYMENT: {
        "how to deploy", "deployment pipeline", "how do i deploy",
        "production deployment", "ci/cd", "deploy to",
    },
    RetrievalIntent.API: {
        "api endpoint", "http request", "rest api", "endpoint for",
        "how do i call", "make a request", "request format", "api route",
        "http status", "how is authentication handled",
    },
    RetrievalIntent.DATABASE: {
        "database schema", "database model", "data model", "database table",
        "how is data stored", "database connection", "database setup",
        "how does the database work",
    },
    RetrievalIntent.SECURITY: {
        "authentication flow", "login flow", "how is auth handled",
        "how is authentication", "authorization mechanism", "security model",
        "password hashing", "token based", "access control",
    },
    RetrievalIntent.PERFORMANCE: {
        "performance issue", "performance problem", "why is it slow",
        "how is performance", "optimization opportunity", "slow query",
        "caching strategy", "performance optimization",
    },
    RetrievalIntent.DEPENDENCIES: {
        "third party", "list of dependencies", "dependency list",
        "what versions", "package versions", "what libraries",
    },
    RetrievalIntent.DOCUMENTATION: {
        "how do i use", "how to use", "usage example", "where is it documented",
        "is there a guide", "how to use it", "documented",
    },
    RetrievalIntent.FILE_LOOKUP: {
        "where is the file", "which file", "what file", "file location",
        "where is it defined", "find the file", "where is the",
    },
    RetrievalIntent.FUNCTION_LOOKUP: {
        "what does the function", "function called", "method that",
        "where is the function", "what function", "how is the function used",
    },
    RetrievalIntent.CLASS_LOOKUP: {
        "what class", "class called", "where is the class", "class that",
        "what is the class",
    },
    RetrievalIntent.COMPARISON: {
        "difference between", "what is the difference", "compared to",
        "instead of", "vs ", "a vs b", "which one",
    },
    RetrievalIntent.BUG_INVESTIGATION: {
        "why is it failing", "why does it fail", "why does this error",
        "what is the error", "why is it broken", "why is this not",
        "causing the error", "this is broken", "getting an error",
        "fix the bug", "what causes",
    },
    RetrievalIntent.FEATURE_LOCATION: {
        "where is it implemented", "how is it implemented", "where is this",
        "how is this done", "where is that", "how is it handled",
        "where is the code", "which part",
    },
}

_PATTERN_LEXICON: dict[RetrievalIntent, list[re.Pattern]] = {
    RetrievalIntent.FILE_LOOKUP: [
        re.compile(r"(?:[\w-]+\.)+[a-z]{1,6}\b"),
        re.compile(r"\b[\w-]+(?:/[\w-]+)+\b"),
    ],
    RetrievalIntent.API: [
        re.compile(r"/(?:[\w{}:.-]+/?){1,4}\b"),
        re.compile(r"\b(get|post|put|patch|delete)\s+(?:/)?[\w:{}.-]+"),
    ],
    RetrievalIntent.FUNCTION_LOOKUP: [
        re.compile(r"\b[a-z_]\w*\(\)"),
        re.compile(r"\b[a-z_]\w*\([^)]*\)"),
    ],
    RetrievalIntent.SETUP: [
        re.compile(r"\b(install|run|setup|start)\b", re.IGNORECASE),
    ],
    RetrievalIntent.SECURITY: [
        re.compile(r"\b(auth|login|jwt|token|oauth)\b", re.IGNORECASE),
    ],
    RetrievalIntent.DEPLOYMENT: [
        re.compile(r"\b(deploy|docker|compose|ci|release)\b", re.IGNORECASE),
    ],
}


class IntentAnalyzer:
    """Classifies a query into the 16 intents with per-intent scores.

    Score = 0.60 * (matched tokens / total meaningful tokens)
          + 0.30 * phrase hits
          + 0.10 * pattern hits
    Primary intent = highest score (ties broken by a stable intent order).
    """

    def __init__(self) -> None:
        self._specs: list[_IntentSpec] = [
            _IntentSpec(
                intent=intent,
                words=_WORD_LEXICON.get(intent, set()),
                phrases=_PHRASE_LEXICON.get(intent, set()),
                patterns=_PATTERN_LEXICON.get(intent, []),
            )
            for intent in RetrievalIntent
        ]

    def analyze(self, query: str) -> QueryAnalysis:
        lowered = query.lower().strip()
        tokens = _TOKEN_RE.findall(lowered)
        meaningful = [t for t in tokens if t not in {"the", "and", "for", "are", "with", "from", "this", "that", "does"}]
        total = max(len(meaningful), 1)

        matches: list[IntentMatch] = []
        for spec in self._specs:
            word_hits = [
                t for t in meaningful
                if spec.words and (_stem(t) in spec.words or t in spec.words)
            ]
            phrase_hits = [p for p in spec.phrases if p in lowered]
            pattern_hits = [p for p in spec.patterns if p.search(lowered)]
            if not (word_hits or phrase_hits or pattern_hits):
                continue
            score = (
                0.60 * (len(word_hits) / total)
                + 0.30 * (1.0 if phrase_hits else 0.0)
                + 0.10 * (1.0 if pattern_hits else 0.0)
            )
            matched = word_hits + phrase_hits
            matches.append(
                IntentMatch(intent=spec.intent, score=round(score, 4), matched_terms=matched)
            )

        if not matches:
            matches = [
                IntentMatch(
                    intent=RetrievalIntent.EXPLANATION,
                    score=0.05,
                    matched_terms=[],
                )
            ]
        matches.sort(key=lambda m: (-m.score, m.intent.value))
        primary = matches[0].intent
        # A specific domain match (auth, database, api...) beats the generic
        # "explain" fallback: "how does auth work" is a SECURITY question, not
        # an EXPLANATION one -- unless nothing content-specific fired.
        if primary == RetrievalIntent.EXPLANATION:
            content = [m for m in matches if m.intent != RetrievalIntent.EXPLANATION]
            if content and content[0].score >= 0.05:
                best = content[0]
                matches.remove(best)
                matches.insert(0, best)
                primary = best.intent
        return QueryAnalysis(
            query=query,
            primary_intent=primary,
            intents=matches[:4],
            rewritten_query=query,
            terms=meaningful,
        )


def get_intent_analyzer() -> IntentAnalyzer:
    return IntentAnalyzer()
