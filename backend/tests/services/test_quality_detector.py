from pathlib import Path

from app.services.repository.detectors.quality_detector import QualityDetector


def test_counts_files_lines_and_todos(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("# TODO: fix this\nprint('hi')\n")
    (tmp_path / "b.py").write_text("print('bye')\n")

    result = QualityDetector().detect(tmp_path)

    assert result.total_files == 2
    assert result.total_lines == 3
    assert result.todo_count == 1


def test_empty_repo_returns_zeros(tmp_path: Path) -> None:
    result = QualityDetector().detect(tmp_path)

    assert (result.total_files, result.total_lines, result.todo_count) == (0, 0, 0)
