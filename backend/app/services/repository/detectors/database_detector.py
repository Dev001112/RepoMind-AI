"""Detects database/ORM usage from manifest dependency names and, if present,
docker-compose service images -- both cheap substring checks, no new
dependency (no PyYAML) needed for either."""

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from app.services.repository.detectors.base import Detector

_MANIFEST_NAMES = ("requirements.txt", "pyproject.toml", "package.json", "Pipfile", "go.mod", "Cargo.toml")
_COMPOSE_NAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")

# (substring in manifest text, database name).
_DB_SIGNATURES = [
    ("psycopg2", "PostgreSQL"), ("asyncpg", "PostgreSQL"), ("pg8000", "PostgreSQL"),
    ("pymysql", "MySQL"), ("mysqlclient", "MySQL"), ("mysql2", "MySQL"),
    ("pymongo", "MongoDB"), ("mongoose", "MongoDB"), ("motor", "MongoDB"),
    ("redis", "Redis"), ("ioredis", "Redis"),
    ("sqlite3", "SQLite"), ("better-sqlite3", "SQLite"),
    ("cassandra-driver", "Cassandra"),
    ("elasticsearch", "Elasticsearch"),
    ("cx_oracle", "Oracle"), ("oracledb", "Oracle"),
    ("pyodbc", "SQL Server"), ("mssql", "SQL Server"),
]
# (substring in manifest text, ORM name).
_ORM_SIGNATURES = [
    ("sqlalchemy", "SQLAlchemy"), ("django.db", "Django ORM"), ("peewee", "Peewee"),
    ("tortoise-orm", "Tortoise ORM"),
    ("prisma", "Prisma"), ("typeorm", "TypeORM"), ("sequelize", "Sequelize"),
    ("mongoose", "Mongoose"),
]
# (substring in compose text, database name) -- checked against service image lines.
_COMPOSE_IMAGE_SIGNATURES = [
    ("postgres", "PostgreSQL"), ("mysql", "MySQL"), ("mariadb", "MariaDB"),
    ("mongo", "MongoDB"), ("redis", "Redis"), ("cassandra", "Cassandra"),
    ("elasticsearch", "Elasticsearch"),
]


class DatabaseDetectionResult(BaseModel):
    databases: list[str] = []
    orms: list[str] = []


def _scan_manifests(repo_path: Path) -> tuple[list[str], list[str]]:
    databases: list[str] = []
    orms: list[str] = []
    for name in _MANIFEST_NAMES:
        path = repo_path / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        for needle, db in _DB_SIGNATURES:
            if needle in text and db not in databases:
                databases.append(db)
        for needle, orm in _ORM_SIGNATURES:
            if needle in text and orm not in orms:
                orms.append(orm)
    return databases, orms


def _scan_compose(repo_path: Path) -> list[str]:
    for name in _COMPOSE_NAMES:
        path = repo_path / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        return [db for needle, db in _COMPOSE_IMAGE_SIGNATURES if needle in text]
    return []


class DatabaseDetector(Detector[DatabaseDetectionResult]):
    result_model: ClassVar[type[DatabaseDetectionResult]] = DatabaseDetectionResult

    def detect(self, repo_path: Path) -> DatabaseDetectionResult:
        databases, orms = _scan_manifests(repo_path)
        for db in _scan_compose(repo_path):
            if db not in databases:
                databases.append(db)
        return DatabaseDetectionResult(databases=databases, orms=orms)
