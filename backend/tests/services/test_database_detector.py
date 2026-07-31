from pathlib import Path

from app.services.repository.detectors.database_detector import DatabaseDetector


def test_postgres_and_sqlalchemy_detected_from_requirements(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("psycopg2-binary==2.9.10\nSQLAlchemy==2.0.36\n")

    result = DatabaseDetector().detect(tmp_path)

    assert "PostgreSQL" in result.databases
    assert "SQLAlchemy" in result.orms


def test_compose_service_image_detected(tmp_path: Path) -> None:
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  db:\n    image: redis:7\n"
    )

    result = DatabaseDetector().detect(tmp_path)

    assert "Redis" in result.databases


def test_no_signals_returns_empty(tmp_path: Path) -> None:
    result = DatabaseDetector().detect(tmp_path)

    assert result.databases == []
    assert result.orms == []
