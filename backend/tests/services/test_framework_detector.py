from pathlib import Path

from app.services.repository.detectors.framework_detector import FrameworkDetector


def test_python_and_js_manifests_detected(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("fastapi==0.100.0\nsqlalchemy==2.0.0\n")
    (tmp_path / "package.json").write_text('{"dependencies": {"react": "^18.0.0"}}')

    frameworks = FrameworkDetector().detect(tmp_path).frameworks

    assert "FastAPI" in frameworks
    assert "SQLAlchemy" in frameworks
    assert "React" in frameworks


def test_no_manifests_returns_empty(tmp_path: Path) -> None:
    assert FrameworkDetector().detect(tmp_path).frameworks == []


def test_malformed_pyproject_toml_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("this is not [valid toml")
    (tmp_path / "requirements.txt").write_text("flask==3.0.0\n")

    result = FrameworkDetector().detect(tmp_path)

    assert result.frameworks == ["Flask"]
