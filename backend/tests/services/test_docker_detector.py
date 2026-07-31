from pathlib import Path

from app.services.repository.detectors.docker_detector import DockerDetector


def test_dockerfile_at_root(tmp_path: Path) -> None:
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\n")
    result = DockerDetector().detect(tmp_path)
    assert result.docker_support is True
    assert result.dockerfile_path == "Dockerfile"


def test_dockerfile_one_level_deep(tmp_path: Path) -> None:
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    (docker_dir / "Dockerfile").write_text("FROM python:3.12\n")
    assert DockerDetector().detect(tmp_path).docker_support is True


def test_compose_file_variant(tmp_path: Path) -> None:
    (tmp_path / "compose.yaml").write_text("services:\n  web:\n    image: myapp\n")
    result = DockerDetector().detect(tmp_path)
    assert result.docker_support is True
    assert result.compose_services == ["web"]


def test_empty_dir_returns_false(tmp_path: Path) -> None:
    result = DockerDetector().detect(tmp_path)
    assert result.docker_support is False
    assert result.dockerfile_path is None
    assert result.compose_services == []
