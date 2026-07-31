import json
from pathlib import Path

from app.services.repository.detectors.dependency_detector import DependencyDetector


def test_detects_and_merges_requirements_and_package_json(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        "requests==2.31.0\n"
        "numpy>=1.20\n"
        "# a comment line, ignored\n"
        "click\n"
    )
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"react": "^18.2.0"}})
    )

    deps = DependencyDetector().detect(tmp_path).dependencies

    assert deps["requests"] == "==2.31.0"
    assert deps["numpy"] == ">=1.20"
    assert deps["click"] == "*"
    assert deps["react"] == "^18.2.0"


def test_no_manifests_returns_empty_dict(tmp_path: Path) -> None:
    assert DependencyDetector().detect(tmp_path).dependencies == {}


def test_corrupt_pyproject_toml_does_not_raise(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("this is not [valid toml")

    result = DependencyDetector().detect(tmp_path)

    assert result.dependencies == {}
