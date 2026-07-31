from pathlib import Path

from app.services.repository.detectors.package_manager_detector import (
    PackageManagerDetector,
)


def test_poetry_lock_only(tmp_path: Path) -> None:
    (tmp_path / "poetry.lock").write_text("")

    result = PackageManagerDetector().detect(tmp_path)

    assert result == {"package_managers": ["poetry"]}


def test_poetry_lock_suppresses_pip_even_with_requirements_txt(tmp_path: Path) -> None:
    (tmp_path / "poetry.lock").write_text("")
    (tmp_path / "requirements.txt").write_text("requests==2.0\n")

    result = PackageManagerDetector().detect(tmp_path)

    assert "pip" not in result["package_managers"]
    assert result["package_managers"] == ["poetry"]


def test_requirements_txt_only(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("requests==2.0\n")

    result = PackageManagerDetector().detect(tmp_path)

    assert result == {"package_managers": ["pip"]}


def test_empty_dir_returns_empty_list(tmp_path: Path) -> None:
    result = PackageManagerDetector().detect(tmp_path)

    assert result == {"package_managers": []}
