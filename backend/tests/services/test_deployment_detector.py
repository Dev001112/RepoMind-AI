from pathlib import Path

from app.services.repository.detectors.deployment_detector import DeploymentDetector


def test_procfile_detected(tmp_path: Path) -> None:
    (tmp_path / "Procfile").write_text("web: gunicorn app:app\n")

    result = DeploymentDetector().detect(tmp_path)

    assert result.platforms == ["Heroku"]


def test_k8s_directory_detected(tmp_path: Path) -> None:
    (tmp_path / "k8s").mkdir()

    result = DeploymentDetector().detect(tmp_path)

    assert result.platforms == ["Kubernetes"]


def test_no_markers_returns_empty(tmp_path: Path) -> None:
    assert DeploymentDetector().detect(tmp_path).platforms == []
