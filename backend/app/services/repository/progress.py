"""Progress computation for the analysis pipeline.

`compute_progress()` turns repository status + the latest run's detector
results into the granular, streamable picture the frontend renders:

    Overall 72%
    Cloning      100%
    Scanning      63%
      README     100%
      Tree-sitter 75%
      Security     0%
    Embedding     0%

Weights are intentional and cheap to tune: cloning 15%, scanning 55%
(detectors 85% of it, tree-sitter parse + knowledge assembly 15%), embedding
30%. A stage in flight gets half its weight; a completed stage gets all of
it. Detector-level completion comes from `detector_results` (persisted by
the scanning stage), so the math is deterministic -- no event replay needed.
"""

import uuid

from sqlalchemy.orm import Session

from app.models.orm.analysis import AnalysisEvent, DetectorResultRecord
from app.models.orm.repository import Repository
from app.models.schemas.repository import RepositoryStatus
from app.services.repository.pipeline.events import (
    EMBEDDINGS_GENERATED,
    KNOWLEDGE_CHUNKS_BUILT,
    VECTOR_INDEX_UPDATED,
)

# Stage name + display label + weight, in pipeline order.
_STAGE_WEIGHTS: list[tuple[str, str, float]] = [
    ("cloning", "Cloning Repository", 0.15),
    ("scanning", "Scanning & Detecting", 0.55),
    ("embedding", "Generating Embeddings", 0.30),
]

# Detectors the scanner runs, in order, with display labels. Tree-sitter
# parsing and knowledge assembly are reported as pseudo-detectors too, so the
# progress view reads like the milestone spec's example.
DETECTORS: list[tuple[str, str]] = [
    ("LanguageDetector", "Languages"),
    ("FrameworkDetector", "Frameworks"),
    ("DependencyDetector", "Dependencies"),
    ("PackageManagerDetector", "Package Managers"),
    ("DockerDetector", "Docker"),
    ("CudaDetector", "CUDA"),
    ("SecurityDetector", "Security"),
    ("ReadmeParser", "README"),
    ("CiCdDetector", "CI/CD"),
    ("DeploymentDetector", "Deployment"),
    ("TestingDetector", "Testing"),
    ("ApiSurfaceDetector", "API Surface"),
    ("DatabaseDetector", "Database"),
    ("QualityDetector", "Quality"),
    ("TreeSitter", "Source Parsing"),
    ("KnowledgeBuilder", "Knowledge Building"),
]

# Scanning's 85% detector/parse share is split across the DETECTORS list;
# knowledge assembly is the remaining 15%.
_SCANNING_DETECTOR_SHARE = 0.85
_SCANNING_KNOWLEDGE_SHARE = 1.0 - _SCANNING_DETECTOR_SHARE

_STATUS_INDEX = {
    RepositoryStatus.CLONING.value: 0,
    RepositoryStatus.SCANNING.value: 1,
    RepositoryStatus.KNOWLEDGE_BUILT.value: 1,
    RepositoryStatus.EMBEDDING.value: 2,
}


def _detector_percent(done_names: set[str]) -> float:
    if not DETECTORS:
        return 0.0
    finished = sum(1 for name, _label in DETECTORS if name in done_names)
    return finished / len(DETECTORS)


def _stage_partial(
    db: Session,
    repository: Repository,
    name: str,
    status: str,
    weight: float,
    done_names: set[str],
) -> tuple[float, str]:
    """Partial credit for the stage currently in flight (or failed).

    Returns a 0..1 fraction *of the stage itself* -- the caller multiplies by
    the stage's weight to get its contribution to the overall figure and by
    100 to render the stage bar (e.g. "Scanning 63%").
    """
    if name == "cloning":
        return 0.5, "active"
    if name == "scanning":
        # KNOWLEDGE_BUILT means scanning + assembly actually finished.
        knowledge_done = status == RepositoryStatus.KNOWLEDGE_BUILT.value
        frac = _detector_percent(done_names) * _SCANNING_DETECTOR_SHARE + (
            _SCANNING_KNOWLEDGE_SHARE if knowledge_done else 0.0
        )
        return frac, "done" if knowledge_done else "active"
    if name == "embedding":
        # Phase 3.2: the index build emits three milestones in order -- chunks
        # built, embeddings generated, index updated -- so progress is real
        # (the example states "Creating Knowledge Chunks ... Generating
        # Embeddings ... Building Vector Index") instead of one fixed spinner.
        milestones = _embedding_milestones(db, repository.id)
        if VECTOR_INDEX_UPDATED in milestones:
            frac = 1.0
        elif EMBEDDINGS_GENERATED in milestones:
            frac = 0.7
        elif KNOWLEDGE_CHUNKS_BUILT in milestones:
            frac = 0.4
        else:
            frac = 0.15
        return frac, "active"
    return 0.5, "active"


def compute_progress(db: Session, repository: Repository) -> dict:
    """Return the progress payload for `repository` (see the schema module)."""
    status = repository.status
    done_names = _completed_detectors(db, repository.id)

    stages: list[dict] = []
    overall = 0.0

    if status == RepositoryStatus.READY.value:
        current_index = len(_STAGE_WEIGHTS)  # everything done
        failed = False
    elif status == RepositoryStatus.PENDING.value:
        current_index = None  # nothing started
        failed = False
    else:
        current_index = _STATUS_INDEX.get(status)
        failed = status == RepositoryStatus.FAILED.value
        if failed and current_index is None:
            current_index = 0  # failed before any known stage -- blame cloning

    for i, (name, label, weight) in enumerate(_STAGE_WEIGHTS):
        if current_index is None:
            percent, state = 0.0, "queued"
        elif i < current_index:
            percent, state = 100.0, "done"
            # Completed stages display 100 but only contribute their weight to
            # the overall figure -- otherwise "overall" is the raw sum of stage
            # percents (cloning done + scanning partial + ...) and jumps to
            # ~100% the moment the first stage finishes, or even past 100%.
            overall += weight * 100.0
        elif i == current_index:
            frac, state = _stage_partial(db, repository, name, status, weight, done_names)
            if failed:
                state = "failed"
            # Stage bar shows how far this stage is through its own work; the
            # overall figure adds the stage's weighted contribution.
            percent = frac * 100.0
            overall += weight * percent
        else:
            percent, state = 0.0, "queued"

        detectors = None
        if name == "scanning":
            detectors = [
                {
                    "name": detector_name,
                    "label": label,
                    "percent": 100 if detector_name in done_names else 0,
                }
                for detector_name, label in DETECTORS
            ]
        stages.append(
            {
                "name": name,
                "label": label,
                "percent": round(percent),
                "state": state,
                **({"detectors": detectors} if detectors is not None else {}),
            }
        )

    if status == RepositoryStatus.READY.value:
        overall = 100.0

    overall = max(0.0, min(100.0, overall))

    return {
        "status": status,
        "overall_percent": round(overall),
        "stages": stages,
        "message": _status_message(status),
    }


def _status_message(status: str) -> str | None:
    messages = {
        RepositoryStatus.PENDING.value: "Queued -- analysis will start shortly.",
        RepositoryStatus.CLONING.value: "Cloning repository...",
        RepositoryStatus.SCANNING.value: "Running detectors...",
        RepositoryStatus.KNOWLEDGE_BUILT.value: "Knowledge built -- generating embeddings...",
        RepositoryStatus.EMBEDDING.value: "Creating knowledge chunks, generating embeddings...",
        RepositoryStatus.READY.value: "Analysis complete.",
        RepositoryStatus.FAILED.value: "Analysis failed.",
    }
    return messages.get(status)


def _completed_detectors(db: Session, repository_id: uuid.UUID) -> set[str]:
    rows = (
        db.query(DetectorResultRecord.detector_name)
        .filter(DetectorResultRecord.repository_id == repository_id)
        .all()
    )
    return {row[0] for row in rows}


def _embedding_milestones(db: Session, repository_id: uuid.UUID) -> set[str]:
    rows = (
        db.query(AnalysisEvent.event_name)
        .filter(
            AnalysisEvent.repository_id == repository_id,
            AnalysisEvent.event_name.in_(
                [KNOWLEDGE_CHUNKS_BUILT, EMBEDDINGS_GENERATED, VECTOR_INDEX_UPDATED]
            ),
        )
        .all()
    )
    return {row[0] for row in rows}
