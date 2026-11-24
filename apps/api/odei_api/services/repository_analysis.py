"""Bounded symbol, reference, import and retrieval-chunk analysis for repository files."""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

_IDENTIFIER = re.compile(r"\b[A-Za-z_$][A-Za-z0-9_$]*\b")
_JS_DEFINITIONS = (
    ("function", re.compile(r"\b(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)")),
    ("class", re.compile(r"\b(?:export\s+)?class\s+([A-Za-z_$][\w$]*)")),
    ("variable", re.compile(r"\b(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)")),
)
_JS_IMPORTS = (
    re.compile(r"\bfrom\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"\bimport\s*\(['\"]([^'\"]+)['\"]\)"),
    re.compile(r"\brequire\s*\(['\"]([^'\"]+)['\"]\)"),
)
_MAX_SYMBOLS_PER_FILE = 2_000
_MAX_REFERENCES_PER_FILE = 5_000
_MAX_IMPORTS_PER_FILE = 500
_MAX_CHUNK_CHARS = 3_000


@dataclass(frozen=True)
class FileAnalysis:
    symbols: tuple[dict[str, Any], ...]
    references: tuple[dict[str, Any], ...]
    imports: tuple[str, ...]
    chunks: tuple[dict[str, Any], ...]


def _python_analysis(path: str, content: str) -> tuple[list[dict], list[tuple[str, int]], list[str]]:
    try:
        tree = ast.parse(content, filename=path)
    except (SyntaxError, ValueError):
        return [], [], []

    symbols: list[dict] = []
    loaded: list[tuple[str, int]] = []
    imports: list[str] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.scope: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef):
            qualified = ".".join([*self.scope, node.name])
            symbols.append({
                "name": node.name, "qualified_name": qualified,
                "kind": "function", "line": node.lineno,
            })
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            qualified = ".".join([*self.scope, node.name])
            symbols.append({
                "name": node.name, "qualified_name": qualified,
                "kind": "function", "line": node.lineno,
            })
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_ClassDef(self, node: ast.ClassDef):
            qualified = ".".join([*self.scope, node.name])
            symbols.append({
                "name": node.name, "qualified_name": qualified,
                "kind": "class", "line": node.lineno,
            })
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_Import(self, node: ast.Import):
            for alias in node.names:
                imports.append(alias.name)

        def visit_ImportFrom(self, node: ast.ImportFrom):
            if node.module:
                imports.append("." * node.level + node.module)

        def visit_Name(self, node: ast.Name):
            if isinstance(node.ctx, ast.Load):
                loaded.append((node.id, node.lineno))
            self.generic_visit(node)

    visitor = Visitor()
    visitor.visit(tree)
    return symbols[:_MAX_SYMBOLS_PER_FILE], loaded[:_MAX_REFERENCES_PER_FILE], imports[:_MAX_IMPORTS_PER_FILE]


def _javascript_analysis(content: str) -> tuple[list[dict], list[str]]:
    symbols: list[dict] = []
    for kind, pattern in _JS_DEFINITIONS:
        for match in pattern.finditer(content):
            symbols.append({
                "name": match.group(1),
                "qualified_name": match.group(1),
                "kind": kind,
                "line": content.count("\n", 0, match.start()) + 1,
            })
            if len(symbols) >= _MAX_SYMBOLS_PER_FILE:
                break
        if len(symbols) >= _MAX_SYMBOLS_PER_FILE:
            break
    imports: list[str] = []
    for pattern in _JS_IMPORTS:
        imports.extend(match.group(1) for match in pattern.finditer(content))
    return symbols, list(dict.fromkeys(imports))[:_MAX_IMPORTS_PER_FILE]


def _chunks(content: str) -> tuple[dict[str, Any], ...]:
    lines = content.splitlines()
    chunks: list[dict[str, Any]] = []
    current: list[str] = []
    current_chars = 0
    start_line = 1
    for line_number, line in enumerate(lines, start=1):
        if current and current_chars + len(line) + 1 > _MAX_CHUNK_CHARS:
            chunks.append({
                "chunk_index": len(chunks),
                "line_start": start_line,
                "text": "\n".join(current),
            })
            current = []
            current_chars = 0
            start_line = line_number
        if len(line) > _MAX_CHUNK_CHARS:
            line = line[:_MAX_CHUNK_CHARS]
        current.append(line)
        current_chars += len(line) + 1
    if current:
        chunks.append({
            "chunk_index": len(chunks),
            "line_start": start_line,
            "text": "\n".join(current),
        })
    return tuple(chunks)


def analyze_repository(files: list[dict[str, Any]], *, max_chunks: int = 500) -> dict[str, Any]:
    """Analyze already-sanitized file records and create bounded cross-file references."""
    if not 1 <= max_chunks <= 2_000:
        raise ValueError("max_chunks must be between 1 and 2000")
    analyses: dict[str, dict[str, Any]] = {}
    global_names: set[str] = set()
    for record in files:
        path, content = record.get("path"), record.get("content")
        if not isinstance(path, str) or not isinstance(content, str):
            continue
        suffix = PurePosixPath(path).suffix.casefold()
        if suffix == ".py":
            symbols, loaded, imports = _python_analysis(path, content)
        elif suffix in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}:
            symbols, imports = _javascript_analysis(content)
            loaded = []
        else:
            symbols, imports, loaded = [], [], []
        for symbol in symbols:
            symbol["path"] = path
            global_names.add(symbol["name"])
        analyses[path] = {
            "symbols": symbols,
            "loaded": loaded,
            "imports": list(dict.fromkeys(imports))[:_MAX_IMPORTS_PER_FILE],
            "chunks": _chunks(content),
            "content": content,
        }

    all_symbols = [
        symbol
        for analysis in analyses.values()
        for symbol in analysis["symbols"]
    ]
    definition_lines = {
        (symbol["path"], symbol["line"], symbol["name"])
        for symbol in all_symbols
    }
    references_by_file: dict[str, list[dict[str, Any]]] = {}
    for path, analysis in analyses.items():
        content = analysis["content"]
        lines = content.splitlines()
        refs: list[dict[str, Any]] = []
        suffix = PurePosixPath(path).suffix.casefold()
        if suffix == ".py":
            candidates = analysis["loaded"]
        else:
            candidates = []
            for line_number, line in enumerate(lines, start=1):
                candidates.extend((match.group(0), line_number) for match in _IDENTIFIER.finditer(line))
        seen: set[tuple[str, int]] = set()
        for name, line_number in candidates:
            key = (name, line_number)
            if (
                name not in global_names
                or key in seen
                or (path, line_number, name) in definition_lines
            ):
                continue
            seen.add(key)
            refs.append({"name": name, "path": path, "line": line_number})
            if len(refs) >= _MAX_REFERENCES_PER_FILE:
                break
        references_by_file[path] = refs

    chunks: list[dict[str, Any]] = []
    for path in sorted(analyses):
        for chunk in analyses[path]["chunks"]:
            if len(chunks) >= max_chunks:
                break
            chunks.append({"path": path, **chunk})
        if len(chunks) >= max_chunks:
            break

    return {
        "symbols": all_symbols,
        "references": [
            reference
            for path in sorted(references_by_file)
            for reference in references_by_file[path]
        ],
        "imports": [
            {"path": path, "module": module}
            for path in sorted(analyses)
            for module in analyses[path]["imports"]
        ],
        "chunks": chunks,
        "chunk_limit_reached": sum(
            len(analysis["chunks"]) for analysis in analyses.values()
        ) > len(chunks),
    }
