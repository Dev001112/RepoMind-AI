import zipfile

import pytest

from app.services.repository.clone.zip_extractor import ZipExtractor

# GithubCloner.clone() does a real network `git clone` -- no network access in
# tests, so it isn't exercised here. Its behavior is a thin, easily-reviewed
# wrapper around GitPython that this test suite intentionally skips.


def _make_zip(zip_path, files: dict[str, str]) -> None:
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)


def test_extracts_flat_zip(tmp_path):
    zip_path = tmp_path / "flat.zip"
    _make_zip(zip_path, {"README.md": "hello", "src/main.py": "print(1)"})
    dest = tmp_path / "out"

    result = ZipExtractor().clone(str(zip_path), dest)

    assert result == dest
    assert (result / "README.md").read_text() == "hello"
    assert (result / "src" / "main.py").read_text() == "print(1)"


def test_unwraps_single_top_level_directory(tmp_path):
    zip_path = tmp_path / "github-style.zip"
    _make_zip(
        zip_path,
        {
            "myrepo-main/README.md": "hello",
            "myrepo-main/src/main.py": "print(1)",
        },
    )
    dest = tmp_path / "out"

    result = ZipExtractor().clone(str(zip_path), dest)

    assert result == dest / "myrepo-main"
    assert (result / "README.md").read_text() == "hello"


def test_rejects_zip_slip(tmp_path):
    zip_path = tmp_path / "evil.zip"
    _make_zip(zip_path, {"../../evil.txt": "pwned"})
    dest = tmp_path / "out"

    with pytest.raises(ValueError, match="unsafe zip"):
        ZipExtractor().clone(str(zip_path), dest)

    # nothing should have been extracted
    assert not dest.exists() or not any(dest.iterdir())


def test_empty_zip_returns_dest(tmp_path):
    zip_path = tmp_path / "empty.zip"
    _make_zip(zip_path, {})
    dest = tmp_path / "out"

    result = ZipExtractor().clone(str(zip_path), dest)

    assert result == dest
