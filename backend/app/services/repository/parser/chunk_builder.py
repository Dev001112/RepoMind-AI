"""Turns parsed source (tree-sitter nodes, or raw text when no grammar is
available) into embeddable CodeChunks.
"""

from dataclasses import dataclass
from pathlib import Path

# Chunk cap keeps embedding cost/time bounded for a single repo scan. 400 turned out
# too small in practice: a handful of large classes (e.g. Flask's own `Flask` class,
# recursed into per-method) can alone consume the whole budget before files that sort
# later alphabetically -- even ones under src/, even with the priority fix in
# tree_sitter_parser.py -- get a turn. Verified empirically against a real repo.
# Local embeddings have no rate limit/cost, so a more generous cap just costs time.
MAX_CHUNKS = 1000

# Node types tree-sitter uses for top-level function/class-like definitions,
# across the languages TreeSitterParser hands us. Covers most mainstream
# languages; anything else falls back to line-window chunking below.
_DEFINITION_NODE_TYPES = {
    "function_definition",  # python, c, cpp
    "class_definition",  # python
    "function_declaration",  # javascript, typescript, go
    "class_declaration",  # javascript, typescript, java, c_sharp
    "method_declaration",  # java, c_sharp, go (interface methods)
    "interface_declaration",  # typescript, java
    "type_alias_declaration",  # typescript
    "function_item",  # rust
    "struct_item",  # rust
    "impl_item",  # rust
    "enum_item",  # rust
    "trait_item",  # rust
    "type_declaration",  # go (struct/interface types)
}

# Containers worth recursing one level into (to find methods) when they're large.
_CONTAINER_NODE_TYPES = {"class_declaration", "class_definition", "impl_item"}

_LARGE_CONTAINER_LINES = 80
_WINDOW_LINES = 60
_WINDOW_OVERLAP = 10


@dataclass
class CodeChunk:
    file_path: str
    content: str
    start_line: int
    end_line: int
    language: str
    # The function/class/etc name for a definition chunk (via tree-sitter's
    # "name" field, consistent across every grammar we tested: python, js, ts,
    # go, rust, java). None for line-window fallback chunks -- there's no
    # single symbol a text window corresponds to.
    symbol_name: str | None = None


@dataclass
class ParsedFile:
    """One file's parse result, handed from TreeSitterParser to ChunkBuilder."""

    path: Path
    language: str
    source: bytes
    tree: object | None  # tree_sitter.Tree, or None if no grammar / parse failed


def _unwrap_export(node):
    """TS/JS wrap exported declarations in an export_statement -- look one level in."""
    if node.type == "export_statement":
        for child in node.children:
            if child.type in _DEFINITION_NODE_TYPES:
                return child
    return node


def _node_text(source: bytes, node) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _symbol_name(source: bytes, node) -> str | None:
    """The definition's identifier via tree-sitter's "name" field -- verified
    consistent across python/js/ts/go/rust/java grammars. None if the node
    type doesn't expose one (uncommon, but not every grammar's every node does)."""
    try:
        name_node = node.child_by_field_name("name")
    except Exception:
        return None
    return _node_text(source, name_node) if name_node is not None else None


def _line_window_chunks(rel_path: str, text: str, language: str) -> list[CodeChunk]:
    lines = text.splitlines()
    if not lines:
        return []
    chunks = []
    start = 0
    step = _WINDOW_LINES - _WINDOW_OVERLAP
    while start < len(lines):
        end = min(start + _WINDOW_LINES, len(lines))
        content = "\n".join(lines[start:end]).strip()
        if content:
            chunks.append(
                CodeChunk(
                    file_path=rel_path,
                    content=content,
                    start_line=start + 1,
                    end_line=end,
                    language=language,
                )
            )
        if end == len(lines):
            break
        start += step
    return chunks


def _definition_chunks(rel_path: str, source: bytes, tree, language: str) -> list[CodeChunk]:
    chunks: list[CodeChunk] = []
    for raw_child in tree.root_node.children:
        node = _unwrap_export(raw_child)
        if node.type not in _DEFINITION_NODE_TYPES:
            continue

        span_lines = node.end_point[0] - node.start_point[0]
        nested_chunks: list[CodeChunk] = []
        if node.type in _CONTAINER_NODE_TYPES and span_lines > _LARGE_CONTAINER_LINES:
            for member in node.children:
                if member.type not in _DEFINITION_NODE_TYPES:
                    continue
                nested_chunks.append(
                    CodeChunk(
                        file_path=rel_path,
                        content=_node_text(source, member),
                        start_line=member.start_point[0] + 1,
                        end_line=member.end_point[0] + 1,
                        language=language,
                        symbol_name=_symbol_name(source, member),
                    )
                )

        if nested_chunks:
            chunks.extend(nested_chunks)
        else:
            chunks.append(
                CodeChunk(
                    file_path=rel_path,
                    content=_node_text(source, node),
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    language=language,
                    symbol_name=_symbol_name(source, node),
                )
            )
    return chunks


class ChunkBuilder:
    def __init__(self) -> None:
        pass

    def build_chunks(self, repo_path: Path, parsed_files: list[ParsedFile]) -> list[CodeChunk]:
        """Slice each parsed file into CodeChunks: definition-level chunks where
        tree-sitter found top-level functions/classes, line-window chunks
        otherwise. Stops once MAX_CHUNKS is reached (repo-wide cap)."""
        all_chunks: list[CodeChunk] = []

        for parsed in parsed_files:
            if len(all_chunks) >= MAX_CHUNKS:
                break

            # .as_posix() (not str()) -- on Windows, str(Path) uses backslashes, but URLs
            # (and the eventual Linux/Docker deployment) use forward slashes. Storing
            # backslash paths made file_path an exact-match lookup that silently found
            # nothing whenever it was queried with the forward-slash form.
            rel_path = parsed.path.relative_to(repo_path).as_posix()
            text = parsed.source.decode("utf-8", errors="replace")

            file_chunks: list[CodeChunk] = []
            if parsed.tree is not None:
                try:
                    file_chunks = _definition_chunks(rel_path, parsed.source, parsed.tree, parsed.language)
                except Exception:
                    file_chunks = []

            if not file_chunks:
                file_chunks = _line_window_chunks(rel_path, text, parsed.language)

            remaining = MAX_CHUNKS - len(all_chunks)
            all_chunks.extend(file_chunks[:remaining])

        return all_chunks
