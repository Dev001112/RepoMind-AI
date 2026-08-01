"""ChunkBuilder tests: RepositoryKnowledge -> semantic KnowledgeChunks.

These are pure, deterministic, DB/Qdrant-free -- the builder is a function
of the report alone. The invariants that make the index incremental live
here: stable ids (same input -> same id), content-addressed checksums, the
closed type vocabulary, and cross-chunk relationships.
"""

import uuid

from app.services.knowledge.chunk_builder import (
    API_ENDPOINT,
    ARCHITECTURE,
    DATABASE,
    DEPENDENCY,
    DOCUMENTATION,
    FILE,
    FOLDER,
    FRAMEWORK,
    QUALITY,
    SECURITY,
    SUMMARY,
    TESTING,
    build_knowledge_chunks,
)


def _build(sample_knowledge):
    return build_knowledge_chunks(sample_knowledge.repository_id, sample_knowledge)


def test_builds_all_major_sections(sample_knowledge) -> None:
    chunks = _build(sample_knowledge)
    types = {chunk.type for chunk in chunks}
    assert SUMMARY in types
    assert ARCHITECTURE in types
    assert FOLDER in types
    assert FILE in types
    assert API_ENDPOINT in types
    assert DATABASE in types
    assert FRAMEWORK in types
    assert DEPENDENCY in types
    assert TESTING in types
    assert DOCUMENTATION in types
    assert SECURITY in types
    assert QUALITY in types


def test_chunk_ids_are_stable_and_checksums_are_content_addressed(sample_knowledge) -> None:
    first = _build(sample_knowledge)
    second = _build(sample_knowledge)
    by_title = {c.title: c for c in first}
    assert {c.id for c in first} == {c.id for c in second}
    assert {c.checksum for c in first} == {c.checksum for c in second}

    # Touching one section changes exactly the chunks that mention it -- and
    # leaves everything else byte-identical (that's what makes re-embedding
    # cheap on re-analysis).
    sample_knowledge.security.findings.append("another finding")
    changed = {c.title for c in _build(sample_knowledge) if c.checksum != by_title[c.title].checksum}
    assert "Security Considerations" in changed
    assert "Repository Summary" not in changed


def test_endpoint_chunk_carries_auth_hint_and_edges(sample_knowledge) -> None:
    chunks = _build(sample_knowledge)
    login = next(c for c in chunks if c.type == API_ENDPOINT and "POST /login" in c.title)
    health = next(c for c in chunks if c.type == API_ENDPOINT and "GET /health" in c.title)

    assert "authentication: yes" in login.content
    assert "authentication: no" in health.content

    # Endpoint -> the file that defines it, and the database it touches.
    kinds = {rel.kind: rel.target_title for rel in login.relationships}
    assert kinds["defined_in"] == "File: api/auth.py"
    assert kinds["uses"] == "Database: PostgreSQL"


def test_folder_and_file_chunks_wire_up(sample_knowledge) -> None:
    chunks = _build(sample_knowledge)
    folder = next(c for c in chunks if c.type == FOLDER and c.title == "Folder: api")
    auth_file = next(c for c in chunks if c.type == FILE and c.title == "File: api/auth.py")

    assert "api" in folder.content
    contains = [rel.target_title for rel in folder.relationships if rel.kind == "contains"]
    assert "File: api/routes.py" in contains or "File: api/auth.py" in contains

    # The auth file's chunk mentions the login endpoint and the framework.
    assert "POST /login" in auth_file.content
    uses = [rel.target_title for rel in auth_file.relationships if rel.kind == "uses"]
    assert "Framework: Flask" in uses


def test_deterministic_across_runs_and_repository_scoped(sample_knowledge) -> None:
    chunks = _build(sample_knowledge)
    other_repo = uuid.uuid4()
    same_report = sample_knowledge.model_copy(deep=True)
    same_report.repository_id = other_repo
    other_chunks = build_knowledge_chunks(other_repo, same_report)

    # Same report, different repository -> same content, different ids.
    assert len(chunks) == len(other_chunks)
    assert chunks[0].content == other_chunks[0].content
    assert chunks[0].id != other_chunks[0].id


def test_same_route_in_multiple_files_stays_unique(sample_knowledge) -> None:
    # A real-world trap: test suites re-define the same route, so "GET /"
    # exists in several files. Chunks must stay unique (one id per chunk) or
    # the index collapses them into a single point.
    sample_knowledge.apis.endpoints = [
        {"method": "GET", "path": "/", "file": "api/routes.py"},
        {"method": "GET", "path": "/", "file": "tests/test_routes.py"},
    ]
    chunks = _build(sample_knowledge)
    endpoint_chunks = [c for c in chunks if c.type == API_ENDPOINT]
    assert len(endpoint_chunks) == 2
    assert len({c.id for c in endpoint_chunks}) == 2
    assert len({c.title for c in endpoint_chunks}) == 2
    assert all(c.title.endswith(".py)") for c in endpoint_chunks)

    # Still deterministic across runs.
    assert {c.id for c in chunks} == {c.id for c in _build(sample_knowledge)}


def test_empty_report_yields_only_skeleton_chunks(sample_knowledge) -> None:
    sample_knowledge.security.findings = []
    sample_knowledge.apis.endpoints = []
    sample_knowledge.frameworks.frameworks = []
    sample_knowledge.dependencies.dependencies = {}
    sample_knowledge.deployment.platforms = []
    chunks = _build(sample_knowledge)
    # No endpoint/framework/dependency chunks, but summary + security "clean"
    # report still exist.
    assert all(c.type != API_ENDPOINT for c in chunks)
    assert all(c.type != FRAMEWORK for c in chunks)
    assert all(c.type != DEPENDENCY for c in chunks)
    assert any(c.type == SECURITY and "No security findings" in c.content for c in chunks)
    assert any(c.type == SUMMARY for c in chunks)
