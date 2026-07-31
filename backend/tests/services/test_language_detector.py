from pathlib import Path

from app.services.repository.detectors.language_detector import LanguageDetector


def test_ranks_languages_by_file_count_and_skips_vendored_dirs(tmp_path: Path) -> None:
    for i in range(3):
        (tmp_path / f"mod_{i}.py").write_text("print('hi')\n")
    (tmp_path / "index.js").write_text("console.log('hi');\n")

    vendored = tmp_path / "node_modules" / "some_pkg"
    vendored.mkdir(parents=True)
    (vendored / "lib.js").write_text("module.exports = {};\n")

    result = LanguageDetector().detect(tmp_path)

    assert result.languages == ["Python", "JavaScript"]
    assert {stat.name: stat.file_count for stat in result.stats} == {"Python": 3, "JavaScript": 1}


def test_empty_dir_returns_no_languages(tmp_path: Path) -> None:
    assert LanguageDetector().detect(tmp_path).languages == []


def test_missing_path_returns_no_languages(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    assert LanguageDetector().detect(missing).languages == []
