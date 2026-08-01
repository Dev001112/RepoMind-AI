"""Tests for the analysis observability layer: run lifecycle, event log,
detector-result persistence, metrics, and progress computation.

These use a real DB session against the dev SQLite file (same pattern as the
other service tests) with cleanup fixtures, and no-op pipeline stages where
the orchestrator is involved -- network/LLM/Qdrant work isn't exercised here.
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import BaseModel

from app.database.session import SessionLocal
from app.models.orm.analysis import (
    AnalysisEvent,
    AnalysisRun,
    DetectorResultRecord,
    RepositoryMetric,
)
from app.models.orm.repository import Repository
from app.models.schemas.knowledge import RepositoryKnowledge
from app.models.schemas.repository import RepositoryStatus
from app.services.knowledge_builder.persistence import persist_detector_results
from app.services.repository import analysis_pipeline
from app.services.repository.detectors.base import Detector
from app.services.repository.metrics import load_metrics, persist_metrics
from app.services.repository.pipeline.events import (
    ANALYSIS_COMPLETED,
    ANALYSIS_STARTED,
    DetectorEventSink,
    record_event,
)
from app.services.repository.pipeline.runs import create_run, finish_run, latest_running_run_id
from app.services.repository.pipeline.types import StageDef
from app.services.repository.progress import compute_progress

pytestmark = pytest.mark.usefixtures("_cleanup_rows")

_created_repo_ids: list[uuid.UUID] = []


@pytest.fixture
def _cleanup_rows():
    yield
    _teardown()
    _created_repo_ids.clear()


def _teardown() -> None:
    db = SessionLocal()
    try:
        for repo_id in _created_repo_ids:
            db.query(AnalysisEvent).filter(AnalysisEvent.repository_id == repo_id).delete()
            db.query(DetectorResultRecord).filter(
                DetectorResultRecord.repository_id == repo_id
            ).delete()
            db.query(RepositoryMetric).filter(RepositoryMetric.repository_id == repo_id).delete()
            db.query(AnalysisRun).filter(AnalysisRun.repository_id == repo_id).delete()
            row = db.get(Repository, repo_id)
            if row is not None:
                db.delete(row)
        db.commit()
    finally:
        db.close()


def _make_repository(**kwargs) -> uuid.UUID:
    db = SessionLocal()
    try:
        repository = Repository(
            source_url="https://example.com/x.git",
            status=kwargs.pop("status", "pending"),
            **kwargs,
        )
        db.add(repository)
        db.commit()
        db.refresh(repository)
        _created_repo_ids.append(repository.id)
        return repository.id
    finally:
        db.close()


def _get_repository(repository_id: uuid.UUID) -> Repository:
    db = SessionLocal()
    try:
        return db.get(Repository, repository_id)
    finally:
        db.close()


class _Payload(BaseModel):
    pass


class _Detector:
    result_model: ClassVar[type[BaseModel]] = _Payload

    def __init__(self, name: str = "_Detector") -> None:
        self._name = name

    def run(self, repo_path: Path):
        from app.services.repository.detectors.base import DetectorResult

        return DetectorResult(
            detector_name=self._name,
            detector_version="1",
            data=_Payload(),
            confidence=0.9,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            warnings=["w"],
            errors=[],
        )


def test_run_lifecycle_create_and_finish() -> None:
    repo_id = _make_repository()
    run_id = uuid.uuid4()
    started_at = datetime.now(timezone.utc)

    db = SessionLocal()
    try:
        create_run(db, repo_id, run_id, trigger="create")
        assert latest_running_run_id(db, repo_id) == run_id
        finish_run(db, repo_id, run_id, started_at, status="completed")
        assert latest_running_run_id(db, repo_id) is None
    finally:
        db.close()

    db = SessionLocal()
    try:
        run = db.get(AnalysisRun, run_id)
        assert run is not None
        assert run.status == "completed"
        assert run.finished_at is not None
        assert run.duration_ms is not None and run.duration_ms >= 0
    finally:
        db.close()


def test_record_event_persists() -> None:
    repo_id = _make_repository()
    record_event(repo_id, ANALYSIS_STARTED, level="info", message="hi", data={"k": "v"})
    db = SessionLocal()
    try:
        events = db.query(AnalysisEvent).filter(AnalysisEvent.repository_id == repo_id).all()
        assert len(events) == 1
        assert events[0].event_name == ANALYSIS_STARTED
        assert events[0].data == {"k": "v"}
    finally:
        db.close()


def test_orchestrator_writes_run_and_events() -> None:
    repo_id = _make_repository()
    fake_pipeline = [StageDef(analysis_pipeline.RepositoryStatus.SCANNING, lambda rid, s: None)]
    with pytest.MonkeyPatch.context() as m:
        m.setattr(analysis_pipeline, "PIPELINE", fake_pipeline)
        analysis_pipeline.run_analysis_pipeline(repo_id)

    db = SessionLocal()
    try:
        runs = db.query(AnalysisRun).filter(AnalysisRun.repository_id == repo_id).all()
        assert len(runs) == 1
        assert runs[0].status == "completed"

        names = {
            e.event_name
            for e in db.query(AnalysisEvent).filter(AnalysisEvent.repository_id == repo_id).all()
        }
        assert ANALYSIS_STARTED in names
        assert ANALYSIS_COMPLETED in names
        assert "scanning.start" in names
        assert "scanning.success" in names
    finally:
        db.close()


def test_persist_detector_results_roundtrip() -> None:
    repo_id = _make_repository()
    sink_result = _Detector().run(Path("."))
    db = SessionLocal()
    try:
        persist_detector_results(db, repo_id, None, [sink_result])
        rows = db.query(DetectorResultRecord).filter(
            DetectorResultRecord.repository_id == repo_id
        ).all()
        assert len(rows) == 1
        assert rows[0].detector_name == "_Detector"
        assert rows[0].confidence == 0.9
        assert rows[0].warnings == ["w"]
        assert rows[0].duration_ms is not None
    finally:
        db.close()


def test_metrics_persist_latest_only() -> None:
    repo_id = _make_repository()
    knowledge = RepositoryKnowledge(
        repository_id=repo_id,
        files={"total_files": 7},
        symbols={"total_symbols": 42},
        quality={"total_files": 7, "total_lines": 100, "todo_count": 2},
    )
    db = SessionLocal()
    try:
        persist_metrics(db, repo_id, None, knowledge, )
        first = load_metrics(db, repo_id)
        assert {m.metric_name for m in first} >= {"total_files", "total_symbols", "total_lines"}
        assert {m.metric_name: m.metric_value for m in first}["total_files"] == 7

        # Re-persisting replaces, not duplicates.
        persist_metrics(db, repo_id, None, knowledge)
        second = load_metrics(db, repo_id)
        assert len(second) == len(first)

        progress = compute_progress(db, _get_repository(repo_id))
        assert progress["status"] == "pending"
        assert progress["overall_percent"] == 0
        assert len(progress["stages"]) == 3
    finally:
        db.close()


def test_progress_overall_is_weighted_not_raw_sum() -> None:
    # Regression: overall used to be the raw sum of stage percents, so the
    # moment cloning finished the bar jumped to 100% (or past it -- 200% was
    # observed) and never moved again.
    db = SessionLocal()
    try:
        # Cloning done, scanning in flight with no detector finished yet.
        repo_id = _make_repository(status="scanning")
        progress = compute_progress(db, _get_repository(repo_id))
        assert progress["overall_percent"] == 15  # cloning's weight, not 100
        stages = {s["name"]: s for s in progress["stages"]}
        assert stages["cloning"]["percent"] == 100  # displayed as done
        assert stages["scanning"]["percent"] == 0
        assert stages["embedding"]["percent"] == 0

        # Cloning + scanning done, embedding in flight with no milestones yet
        # -> overall 15 + 55 + 30*0.15 = 74.5, never near 200.
        repo_id = _make_repository(status=RepositoryStatus.EMBEDDING.value)
        progress = compute_progress(db, _get_repository(repo_id))
        assert progress["overall_percent"] in (74, 75)
        assert progress["overall_percent"] <= 100
        embedding = next(s for s in progress["stages"] if s["name"] == "embedding")
        assert embedding["percent"] == 15  # 0.15 of the embedding stage itself
        assert embedding["state"] == "active"
    finally:
        db.close()


def test_progress_reflects_status_and_detectors() -> None:
    repo_id = _make_repository(status="scanning")
    db = SessionLocal()
    try:
        # Half the detectors done -> scanning stage shows partial progress.
        persist_detector_results(
            db,
            repo_id,
            None,
            [_Detector(name=n).run(Path(".")) for n in ["LanguageDetector", "FrameworkDetector"]],
        )
        progress = compute_progress(db, _get_repository(repo_id))
        assert progress["status"] == "scanning"
        assert progress["overall_percent"] > 0
        scanning = next(s for s in progress["stages"] if s["name"] == "scanning")
        langs = next(d for d in scanning["detectors"] if d["name"] == "LanguageDetector")
        sec = next(d for d in scanning["detectors"] if d["name"] == "SecurityDetector")
        assert langs["percent"] == 100
        assert sec["percent"] == 0
    finally:
        db.close()
