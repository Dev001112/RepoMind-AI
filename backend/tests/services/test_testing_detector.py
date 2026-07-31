from pathlib import Path

from app.services.repository.detectors.testing_detector import TestingDetector


def test_pytest_dependency_and_test_dir_detected(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("pytest==8.0.0\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_foo.py").write_text("def test_x(): pass\n")

    result = TestingDetector().detect(tmp_path)

    assert "pytest" in result.frameworks
    assert result.has_tests is True
    assert result.test_file_count == 1


def test_empty_repo_has_no_tests(tmp_path: Path) -> None:
    result = TestingDetector().detect(tmp_path)

    assert result.frameworks == []
    assert result.has_tests is False
    assert result.test_file_count == 0
