"""Scalar, dashboard-ready metrics derived from RepositoryKnowledge.

These are the small, filterable figures surfaced on the dashboard and the
repository page (files, symbols, endpoints, dependencies, ...) -- stored one
row per metric in `repository_metrics` so they're queryable without loading
the full knowledge JSON. Computed by the scanning stage right after the
knowledge object is persisted; only the latest run's metrics are kept.
"""

import uuid

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.orm.analysis import RepositoryMetric
from app.models.schemas.knowledge import RepositoryKnowledge


def compute_metrics(knowledge: RepositoryKnowledge) -> list[tuple[str, float, str | None]]:
    """Return (metric_name, value, unit) triples derived from the knowledge object."""
    return [
        ("total_files", float(knowledge.files.total_files), "files"),
        ("total_lines", float(knowledge.quality.total_lines), "lines"),
        ("total_symbols", float(knowledge.symbols.total_symbols), "symbols"),
        ("endpoints", float(len(knowledge.apis.endpoints)), "endpoints"),
        ("dependencies", float(len(knowledge.dependencies.dependencies)), "dependencies"),
        ("languages", float(len(knowledge.languages.languages)), "languages"),
        ("frameworks", float(len(knowledge.frameworks.frameworks)), "frameworks"),
        ("test_files", float(knowledge.testing.test_file_count), "files"),
        ("todos", float(knowledge.quality.todo_count), "todos"),
        ("security_findings", float(len(knowledge.security.findings)), "findings"),
    ]


def persist_metrics(
    db: Session, repository_id: uuid.UUID, run_id: uuid.UUID | None, knowledge: RepositoryKnowledge
) -> None:
    db.execute(delete(RepositoryMetric).where(RepositoryMetric.repository_id == repository_id))
    for name, value, unit in compute_metrics(knowledge):
        db.add(
            RepositoryMetric(
                repository_id=repository_id,
                run_id=run_id,
                metric_name=name,
                metric_value=value,
                unit=unit,
            )
        )
    db.commit()


def load_metrics(db: Session, repository_id: uuid.UUID) -> list[RepositoryMetric]:
    return (
        db.query(RepositoryMetric)
        .filter(RepositoryMetric.repository_id == repository_id)
        .order_by(RepositoryMetric.metric_name)
        .all()
    )
