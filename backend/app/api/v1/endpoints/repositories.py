"""Repository submission/lookup endpoints.

Submitting a repository (by URL or zip upload) records it and immediately
kicks off the analysis pipeline as a background task -- the request returns
right away with status="pending"; poll GET /repositories/{id} for status.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import Settings, get_settings
from app.core.exceptions import RepositoryNotFoundError
from app.models.orm.repository import Repository
from app.models.orm.knowledge import RepositoryKnowledge as RepositoryKnowledgeORM
from app.models.schemas.knowledge import RepositoryKnowledge as RepositoryKnowledgeSchema
from app.models.schemas.repository import RepositoryCreate, RepositoryRead
from app.services.repository.analysis_pipeline import run_analysis_pipeline
from app.utils.file_utils import ensure_dir, safe_join

router = APIRouter()


@router.post("/repositories", response_model=RepositoryRead, status_code=201)
def create_repository(
    payload: RepositoryCreate,
    db: Annotated[Session, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> Repository:
    """Register a repository by its GitHub URL and kick off analysis in the background."""
    repository = Repository(source_url=str(payload.source_url), status="pending")
    db.add(repository)
    db.commit()
    db.refresh(repository)
    background_tasks.add_task(run_analysis_pipeline, repository.id)
    return repository


@router.post("/repositories/upload", response_model=RepositoryRead, status_code=201)
def upload_repository(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    background_tasks: BackgroundTasks,
    file: UploadFile,
) -> Repository:
    """Register a repository from an uploaded zip file and kick off analysis
    in the background. The archive is saved to disk immediately; extraction
    happens as part of the pipeline (see app.services.repository.clone.zip_extractor)."""
    repository_id = uuid.uuid4()
    upload_dir = ensure_dir(settings.uploads_dir)
    dest_path = safe_join(upload_dir, f"{repository_id}.zip")
    with open(dest_path, "wb") as out_file:
        out_file.write(file.file.read())

    repository = Repository(
        id=repository_id,
        upload_filename=file.filename,
        local_path=str(dest_path),
        status="pending",
    )
    db.add(repository)
    db.commit()
    db.refresh(repository)
    background_tasks.add_task(run_analysis_pipeline, repository.id)
    return repository


@router.post("/repositories/{repository_id}/reanalyze", response_model=RepositoryRead)
def reanalyze_repository(
    repository_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> Repository:
    """Re-run the analysis pipeline on an already-submitted repository (e.g.
    after a detector improves). Refuses to double-trigger while a run is
    already in flight.

    Uses a single conditional UPDATE (not read-then-write) so two
    near-simultaneous reanalyze calls can't both observe status="ready", both
    pass the check, and both schedule a background run against the same repo --
    only one UPDATE can flip a matching row per SQL semantics; the other sees
    rowcount 0 and gets the 409 instead.
    """
    result = db.execute(
        update(Repository)
        .where(Repository.id == repository_id, Repository.status.notin_(["cloning", "analyzing"]))
        .values(status="pending")
    )
    db.commit()

    if result.rowcount == 0:
        repository = db.get(Repository, repository_id)
        if repository is None:
            raise RepositoryNotFoundError(str(repository_id))
        raise HTTPException(
            status_code=409,
            detail=f"Analysis already in progress (status: {repository.status}).",
        )

    repository = db.get(Repository, repository_id)
    background_tasks.add_task(run_analysis_pipeline, repository.id)
    return repository


@router.get("/repositories/{repository_id}", response_model=RepositoryRead)
def get_repository(
    repository_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> Repository:
    repository = db.get(Repository, repository_id)
    if repository is None:
        raise RepositoryNotFoundError(str(repository_id))
    return repository


@router.get("/repositories/{repository_id}/knowledge", response_model=RepositoryKnowledgeSchema)
def get_repository_knowledge(
    repository_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> RepositoryKnowledgeORM:
    repository = db.get(Repository, repository_id)
    if repository is None:
        raise RepositoryNotFoundError(str(repository_id))

    knowledge = (
        db.query(RepositoryKnowledgeORM)
        .filter(RepositoryKnowledgeORM.repository_id == repository_id)
        .first()
    )
    if knowledge is None:
        raise HTTPException(
            status_code=404,
            detail=f"Knowledge not available yet (repository status: {repository.status}).",
        )
    return knowledge
