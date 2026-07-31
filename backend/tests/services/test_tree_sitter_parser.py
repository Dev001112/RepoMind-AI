from pathlib import Path

from app.services.repository.parser import tree_sitter_parser
from app.services.repository.parser.tree_sitter_parser import TreeSitterParser


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_extracts_python_definitions(tmp_path: Path) -> None:
    _write(
        tmp_path / "app.py",
        "def add(a, b):\n"
        "    return a + b\n"
        "\n"
        "\n"
        "class Greeter:\n"
        "    def hello(self):\n"
        "        return 'hi'\n",
    )

    chunks = TreeSitterParser().parse(tmp_path)

    assert any("def add" in c.content for c in chunks)
    assert any("class Greeter" in c.content for c in chunks)
    assert all(c.file_path == "app.py" for c in chunks)
    assert all(c.language == "python" for c in chunks)

    symbol_names = {c.symbol_name for c in chunks}
    assert "add" in symbol_names
    assert "Greeter" in symbol_names


def test_line_window_fallback_chunks_have_no_symbol_name(tmp_path: Path) -> None:
    _write(tmp_path / "config.js", "\n".join(f"const x{i} = {i};" for i in range(100)))

    chunks = TreeSitterParser().parse(tmp_path)

    assert len(chunks) > 0
    assert all(c.symbol_name is None for c in chunks)


def test_truly_unknown_extension_is_skipped(tmp_path: Path) -> None:
    _write(tmp_path / "data.bin", "\n".join(f"line {i}" for i in range(150)))

    chunks = TreeSitterParser().parse(tmp_path)

    assert len(chunks) == 0


def test_text_only_extensions_still_get_chunked(tmp_path: Path) -> None:
    # No tree-sitter grammar for markdown/JSON/YAML -- these must still reach the
    # line-window fallback (not be silently skipped like a truly unknown extension).
    _write(tmp_path / "README.md", "\n".join(f"line {i}" for i in range(100)))
    _write(tmp_path / "config.yaml", "\n".join(f"key{i}: value{i}" for i in range(100)))
    _write(tmp_path / "Dockerfile", "\n".join(f"RUN step{i}" for i in range(100)))

    chunks = TreeSitterParser().parse(tmp_path)

    file_paths = {c.file_path for c in chunks}
    assert "README.md" in file_paths
    assert "config.yaml" in file_paths
    assert "Dockerfile" in file_paths
    assert all(c.language == "text" for c in chunks)


def test_symlinks_are_not_followed(tmp_path: Path) -> None:
    _write(tmp_path / "real.py", "def kept():\n    pass\n")
    outside = tmp_path.parent / "outside_secret.py"
    _write(outside, "def should_never_be_read():\n    pass\n")
    (tmp_path / "link.py").symlink_to(outside)

    chunks = TreeSitterParser().parse(tmp_path)

    contents = " ".join(c.content for c in chunks)
    assert "def kept" in contents
    assert "def should_never_be_read" not in contents


def test_skips_excluded_directories(tmp_path: Path) -> None:
    _write(tmp_path / "real.py", "def kept():\n    pass\n")
    _write(tmp_path / "node_modules" / "lib.py", "def excluded():\n    pass\n")
    _write(tmp_path / ".git" / "hooks.py", "def also_excluded():\n    pass\n")

    chunks = TreeSitterParser().parse(tmp_path)

    contents = " ".join(c.content for c in chunks)
    assert "def kept" in contents
    assert "def excluded" not in contents
    assert "def also_excluded" not in contents


def test_javascript_line_window_fallback_when_no_definitions(tmp_path: Path) -> None:
    # Plain statements only, no top-level function/class -- should still chunk via
    # the line-window fallback rather than returning nothing.
    _write(tmp_path / "config.js", "\n".join(f"const x{i} = {i};" for i in range(100)))

    chunks = TreeSitterParser().parse(tmp_path)

    assert len(chunks) > 0
    assert all(c.language == "javascript" for c in chunks)


def test_empty_repo_returns_no_chunks(tmp_path: Path) -> None:
    assert TreeSitterParser().parse(tmp_path) == []


def test_real_source_is_prioritized_over_tests_when_file_cap_is_hit(tmp_path, monkeypatch) -> None:
    # Regression: a repo with an extensive test suite (Flask has 30+ test files)
    # could exhaust the file-scan cap on tests/docs before ever reaching the
    # actual library code under src/ -- backwards for a tool whose whole point
    # is understanding real implementation. Force a tiny cap to test this fast.
    monkeypatch.setattr(tree_sitter_parser, "_MAX_FILES_SCANNED", 2)
    _write(tmp_path / "tests" / "test_a.py", "def test_a():\n    pass\n")
    _write(tmp_path / "tests" / "test_b.py", "def test_b():\n    pass\n")
    _write(tmp_path / "tests" / "test_c.py", "def test_c():\n    pass\n")
    _write(tmp_path / "src" / "core.py", "def real_function():\n    pass\n")

    chunks = TreeSitterParser().parse(tmp_path)

    contents = " ".join(c.content for c in chunks)
    assert "def real_function" in contents


def test_nested_file_path_is_forward_slash_even_on_windows(tmp_path: Path) -> None:
    # Regression: str(Path) uses backslashes on Windows, which silently broke
    # exact file_path lookups (URLs and stored metadata need to agree on one
    # separator convention -- forward slash, matching URLs and eventual Linux
    # deployment).
    _write(tmp_path / "src" / "flask" / "cli.py", "def main():\n    pass\n")

    chunks = TreeSitterParser().parse(tmp_path)

    assert any(c.file_path == "src/flask/cli.py" for c in chunks)
    assert not any("\\" in c.file_path for c in chunks)
