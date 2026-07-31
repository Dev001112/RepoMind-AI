from pathlib import Path

from app.services.repository.detectors.cicd_detector import CiCdDetector


def test_github_actions_workflows_detected(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: CI\n")

    result = CiCdDetector().detect(tmp_path)

    assert result.providers == ["GitHub Actions"]
    assert result.workflow_files == [".github/workflows/ci.yml"]


def test_gitlab_ci_detected(tmp_path: Path) -> None:
    (tmp_path / ".gitlab-ci.yml").write_text("stages: []\n")

    result = CiCdDetector().detect(tmp_path)

    assert result.providers == ["GitLab CI"]


def test_no_ci_config_returns_empty(tmp_path: Path) -> None:
    result = CiCdDetector().detect(tmp_path)

    assert result.providers == []
    assert result.workflow_files == []
