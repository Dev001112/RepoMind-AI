"""Smoke test: `alembic upgrade head` against a throwaway SQLite file
succeeds and produces the tables/columns the new Repository Knowledge layer
expects. Run out-of-process (a real subprocess) so it exercises exactly what
a fresh `alembic upgrade head` deploy would do, not an in-process shortcut."""

import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def test_alembic_upgrade_head_creates_expected_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "smoke_test.db"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env={"DATABASE_URL": f"sqlite:///{db_path}", **_inherit_env()},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}
        for expected in (
            "repositories", "repository_knowledge",
            "repository_languages", "repository_frameworks", "repository_dependencies",
            "analysis_runs", "analysis_events", "detector_results", "repository_metrics",
        ):
            assert expected in tables

        cur.execute("PRAGMA table_info(repositories)")
        repo_columns = {row[1] for row in cur.fetchall()}
        for expected in (
            "last_error", "last_error_stage", "last_analyzed_commit_sha",
            "content_hash", "last_analyzed_at",
        ):
            assert expected in repo_columns

        cur.execute("PRAGMA table_info(repository_knowledge)")
        knowledge_columns = {row[1] for row in cur.fetchall()}
        for expected in (
            "architecture", "files", "symbols", "imports", "apis", "databases",
            "docker", "cicd", "deployment", "testing", "documentation",
            "performance", "security", "quality", "package_managers",
        ):
            assert expected in knowledge_columns
    finally:
        conn.close()


def _inherit_env() -> dict:
    import os

    return dict(os.environ)
