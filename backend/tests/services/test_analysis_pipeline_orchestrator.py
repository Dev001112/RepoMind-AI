"""Tests the orchestrator's own logic (stage sequencing, failure handling,
incremental short-circuit) against fake, no-op stages -- not the real
cloning/scanning/embedding bodies, which need network/LLM/Qdrant and are
covered by live end-to-end verification instead."""

import uuid
from datetime import datetime, timezone

import pytest

from app.database.session import SessionLocal
from app.models.orm.repository import Repository
from app.services.repository import analysis_pipeline
from app.services.repository.pipeline.types import StageDef

pytestmark = pytest.mark.usefixtures("_cleanup_repository_rows")

_created_ids: list[uuid.UUID] = []


@pytest.fixture
def _cleanup_repository_rows():
    yield
    db = SessionLocal()
    try:
        for repo_id in _created_ids:
            row = db.get(Repository, repo_id)
            if row is not None:
                db.delete(row)
        db.commit()
    finally:
        _created_ids.clear()
        db.close()


def _make_repository(**kwargs) -> uuid.UUID:
    db = SessionLocal()
    try:
        repository = Repository(source_url="https://example.com/x.git", status="pending", **kwargs)
        db.add(repository)
        db.commit()
        db.refresh(repository)
        _created_ids.append(repository.id)
        return repository.id
    finally:
        db.close()


def _get_repository(repository_id: uuid.UUID) -> Repository:
    db = SessionLocal()
    try:
        return db.get(Repository, repository_id)
    finally:
        db.close()


def test_successful_pipeline_reaches_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    repository_id = _make_repository()
    calls: list[str] = []

    fake_pipeline = [
        StageDef(analysis_pipeline.RepositoryStatus.SCANNING, lambda rid, s: calls.append("scanning")),
        StageDef(analysis_pipeline.RepositoryStatus.EMBEDDING, lambda rid, s: calls.append("embedding")),
    ]
    monkeypatch.setattr(analysis_pipeline, "PIPELINE", fake_pipeline)

    analysis_pipeline.run_analysis_pipeline(repository_id)

    assert calls == ["scanning", "embedding"]
    repository = _get_repository(repository_id)
    assert repository.status == "ready"
    assert repository.last_analyzed_at is not None


def test_stage_failure_sets_failed_status_and_records_error(monkeypatch: pytest.MonkeyPatch) -> None:
    repository_id = _make_repository()

    def _boom(rid, settings):
        raise RuntimeError("simulated detector explosion")

    fake_pipeline = [StageDef(analysis_pipeline.RepositoryStatus.SCANNING, _boom)]
    monkeypatch.setattr(analysis_pipeline, "PIPELINE", fake_pipeline)

    analysis_pipeline.run_analysis_pipeline(repository_id)

    repository = _get_repository(repository_id)
    assert repository.status == "failed"
    assert "simulated detector explosion" in repository.last_error
    assert repository.last_error_stage == "scanning"


def test_incremental_skip_avoids_running_stages_unless_forced(monkeypatch: pytest.MonkeyPatch) -> None:
    repository_id = _make_repository(
        last_analyzed_commit_sha="deadbeef", last_analyzed_at=datetime.now(timezone.utc)
    )
    calls: list[str] = []
    fake_pipeline = [StageDef(analysis_pipeline.RepositoryStatus.SCANNING, lambda rid, s: calls.append("ran"))]
    monkeypatch.setattr(analysis_pipeline, "PIPELINE", fake_pipeline)
    # Remote is unreachable in this test environment (fake URL) -- should_skip_analysis
    # treats "can't confirm" as "run it", so force the skip path deterministically
    # by stubbing the remote-sha lookup to match the stored sha.
    monkeypatch.setattr(
        "app.services.repository.pipeline.incremental._remote_head_sha",
        lambda url, token: "deadbeef",
    )

    analysis_pipeline.run_analysis_pipeline(repository_id)
    assert calls == []  # skipped -- nothing changed since last run
    assert _get_repository(repository_id).status == "ready"

    analysis_pipeline.run_analysis_pipeline(repository_id, force=True)
    assert calls == ["ran"]  # force bypasses the short-circuit
