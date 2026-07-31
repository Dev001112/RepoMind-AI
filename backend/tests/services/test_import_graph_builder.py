from pathlib import Path

from app.services.repository.parser.import_graph_builder import ImportGraphBuilder


def test_extracts_python_imports(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text(
        "import os\nfrom app.core.config import get_settings\nfrom . import utils\n"
    )

    graph = ImportGraphBuilder().build(tmp_path)

    assert set(graph["app.py"]) == {"os", "app.core.config", "."}


def test_extracts_js_imports(tmp_path: Path) -> None:
    (tmp_path / "index.js").write_text(
        "import React from 'react';\nconst fs = require('fs');\n"
    )

    graph = ImportGraphBuilder().build(tmp_path)

    assert set(graph["index.js"]) == {"react", "fs"}


def test_skips_excluded_dirs_and_files_with_no_imports(tmp_path: Path) -> None:
    (tmp_path / "plain.py").write_text("x = 1\n")
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    (node_modules / "lib.js").write_text("import 'vendored';\n")

    graph = ImportGraphBuilder().build(tmp_path)

    assert "plain.py" not in graph
    assert not any("node_modules" in path for path in graph)


def test_empty_repo_returns_empty_graph(tmp_path: Path) -> None:
    assert ImportGraphBuilder().build(tmp_path) == {}


def test_missing_path_returns_empty_graph(tmp_path: Path) -> None:
    assert ImportGraphBuilder().build(tmp_path / "nope") == {}


def test_nested_file_path_is_forward_slash_even_on_windows(tmp_path: Path) -> None:
    # Same class of bug as chunk_builder.py's CodeChunk.file_path -- str(Path) uses
    # backslashes on Windows, which silently broke exact-match lookups elsewhere.
    nested = tmp_path / "src" / "flask"
    nested.mkdir(parents=True)
    (nested / "cli.py").write_text("import os\n")

    graph = ImportGraphBuilder().build(tmp_path)

    assert "src/flask/cli.py" in graph
    assert not any("\\" in path for path in graph)
