"""Dashboard card assembly: one query batch turning Repository rows into the
cards the dashboard renders (name, status, languages, frameworks, key
metrics) -- everything sourced from the Repository Knowledge layer, never
from the repository on disk.

The metrics/languages/frameworks are read from their normalized tables
(repository_metrics, repository_languages, repository_frameworks) with
`IN` queries, so the whole dashboard is a constant number of queries no
matter how many repositories exist.
"""

import uuid
from collections import defaultdict

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.orm.analysis import RepositoryMetric
from app.models.orm.knowledge import (
    RepositoryFramework,
    RepositoryKnowledge,
    RepositoryLanguage,
)
from app.models.orm.repository import Repository


def load_dashboard_cards(db: Session, limit: int = 50) -> list[dict]:
    repositories = (
        db.query(Repository).order_by(desc(Repository.created_at)).limit(limit).all()
    )
    if not repositories:
        return []

    ids = [repo.id for repo in repositories]

    metrics_by_repo: dict[uuid.UUID, dict[str, float]] = defaultdict(dict)
    for metric in db.query(RepositoryMetric).filter(RepositoryMetric.repository_id.in_(ids)):
        metrics_by_repo[metric.repository_id][metric.metric_name] = metric.metric_value

    languages_by_repo: dict[uuid.UUID, list[str]] = defaultdict(list)
    for language in db.query(RepositoryLanguage).filter(
        RepositoryLanguage.repository_id.in_(ids)
    ):
        languages_by_repo[language.repository_id].append(language.name)

    frameworks_by_repo: dict[uuid.UUID, list[str]] = defaultdict(list)
    for framework in db.query(RepositoryFramework).filter(
        RepositoryFramework.repository_id.in_(ids)
    ):
        frameworks_by_repo[framework.repository_id].append(framework.name)

    names_by_repo: dict[uuid.UUID, str | None] = {}
    for knowledge in db.query(
        RepositoryKnowledge.repository_id, RepositoryKnowledge.name
    ).filter(RepositoryKnowledge.repository_id.in_(ids)):
        names_by_repo[knowledge.repository_id] = knowledge.name

    return [
        {
            "id": repo.id,
            "source_url": repo.source_url,
            "upload_filename": repo.upload_filename,
            "status": repo.status,
            "last_analyzed_at": repo.last_analyzed_at,
            "created_at": repo.created_at,
            "knowledge_name": names_by_repo.get(repo.id),
            "languages": languages_by_repo.get(repo.id, []),
            "frameworks": frameworks_by_repo.get(repo.id, []),
            "metrics": metrics_by_repo.get(repo.id, {}),
        }
        for repo in repositories
    ]
