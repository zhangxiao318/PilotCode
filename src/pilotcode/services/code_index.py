"""Code indexing service for semantic code search.

Provides fast symbol lookup and code navigation capabilities:
- Symbol indexing (classes, functions, variables)
- Definition and reference tracking
- File content indexing
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

try:
    from tree_sitter import Language, Parser

    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False


# Module-level cache for tree-sitter parsers
_tsp_parsers: dict[str, Parser] = {}
_tsp_node_maps: dict[str, dict[str, str]] = {
    "python": {"class_definition": "class", "function_definition": "function"},
    "c": {"function_definition": "function", "struct_specifier": "struct"},
    "cpp": {
        "class_specifier": "class",
        "struct_specifier": "struct",
        "function_definition": "function",
        "namespace_definition": "namespace",
    },
    "javascript": {
        "class_declaration": "class",
        "function_declaration": "function",
        "method_definition": "method",
    },
    "typescript": {
        "class_declaration": "class",
        "interface_declaration": "interface",
        "function_declaration": "function",
        "method_definition": "method",
    },
    "go": {
        "function_declaration": "function",
        "method_declaration": "method",
        "type_declaration": "class",
    },
    "rust": {
        "function_item": "function",
        "struct_item": "struct",
        "trait_item": "trait",
        "enum_item": "enum",
        "impl_item": "class",
    },
    "java": {
        "class_declaration": "class",
        "interface_declaration": "interface",
        "method_declaration": "method",
    },
}


@dataclass
class Symbol:
    """Code symbol (function, class, variable, etc.)."""

    name: str
    symbol_type: str  # 'class', 'function', 'method', 'variable', etc.
    file_path: str
    line_number: int
    column: int
    signature: str | None = None
    docstring: str | None = None
    parent: str | None = None  # Parent class/module


@dataclass
class CodeIndex:
    """Index of code symbols and content."""

    symbols: list[Symbol] = field(default_factory=list)
    symbols_by_file: dict[str, list[Symbol]] = field(default_factory=dict)
    symbols_by_name: dict[str, list[Symbol]] = field(default_factory=dict)
    file_index: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_updated: float = field(default_factory=time.time)

    def find_symbol(self, name: str, symbol_type: str | None = None) -> list[Symbol]:
        """Find symbols by name."""
        # Fast path: exact match via bucket
        if self.symbols_by_name and name in self.symbols_by_name:
            results = []
            for symbol in self.symbols_by_name[name]:
                if symbol_type is None or symbol.symbol_type == symbol_type:
                    results.append(symbol)
            return results

        # Fallback: partial match linear scan
        results = []
        for symbol in self.symbols:
            if name in symbol.name:
                if symbol_type is None or symbol.symbol_type == symbol_type:
                    results.append(symbol)
        return results

    def find_in_file(self, file_path: str) -> list[Symbol]:
        """Find all symbols in a file."""
        if self.symbols_by_file:
            return self.symbols_by_file.get(file_path, [])
        return [s for s in self.symbols if s.file_path == file_path]

    def get_file_info(self, file_path: str) -> dict[str, Any] | None:
        """Get indexed info for a file."""
        return self.file_index.get(file_path)


class CodeIndexer:
    """Indexes code for fast symbol search."""

    # Language patterns for symbol extraction
    PATTERNS = {
        "python": {
            "class": re.compile(r"^class\s+(\w+)\s*(?:\([^)]*\))?:", re.MULTILINE),
            "function": re.compile(r"^def\s+(\w+)\s*\([^)]*\)(?:\s*->[^:]+)?:", re.MULTILINE),
            "method": re.compile(r"^\s+def\s+(\w+)\s*\(self[^)]*\)(?:\s*->[^:]+)?:", re.MULTILINE),
            "variable": re.compile(r"^(\w+)\s*=", re.MULTILINE),
        },
        "javascript": {
            "class": re.compile(r"^class\s+(\w+)", re.MULTILINE),
            "function": re.compile(
                r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\()",
                re.MULTILINE,
            ),
            "method": re.compile(r"^(\w+)\s*\([^)]*\)\s*\{", re.MULTILINE),
        },
        "typescript": {
            "class": re.compile(r"^class\s+(\w+)", re.MULTILINE),
            "interface": re.compile(r"^interface\s+(\w+)", re.MULTILINE),
            "function": re.compile(
                r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*:?\s*=\s*(?:async\s*)?\()",
                re.MULTILINE,
            ),
        },
        "c": {
            "function": re.compile(r"^\s*(?:\w+\s+)+(\w+)\s*\([^)]*\)\s*\{", re.MULTILINE),
            "struct": re.compile(r"^\s*struct\s+(\w+)", re.MULTILINE),
            "typedef": re.compile(r"^\s*typedef\s+.*\s+(\w+)\s*;", re.MULTILINE),
            "macro": re.compile(r"^\s*#define\s+(\w+)", re.MULTILINE),
        },
        "cpp": {
            "class": re.compile(r"^\s*class\s+(\w+)", re.MULTILINE),
            "struct": re.compile(r"^\s*struct\s+(\w+)", re.MULTILINE),
            "function": re.compile(
                r"^\s*(?:\w+[\s*&]+)+(\w+)\s*\([^)]*\)(?:\s*const)?\s*(?:\{|\{)", re.MULTILINE
            ),
            "method": re.compile(
                r"^\s*(?:virtual\s+)?(?:\w+[\s*&]+)+(\w+)\s*\([^)]*\)(?:\s*const)?\s*\{",
                re.MULTILINE,
            ),
            "namespace": re.compile(r"^\s*namespace\s+(\w+)", re.MULTILINE),
            "template": re.compile(
                r"^\s*template\s*<[^>]+>\s*\n\s*(?:class|struct)\s+(\w+)", re.MULTILINE
            ),
        },
    }

    def __init__(self):
        self._index = CodeIndex()
        self._indexed_files: set[str] = set()
        self._lock = asyncio.Lock()

    def _get_language(self, file_path: str) -> str | None:
        """Detect language from file extension."""
        ext = Path(file_path).suffix.lower()

        language_map = {
            # Python
            ".py": "python",
            # JavaScript/TypeScript
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            # Java, Go, Rust
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            # C
            ".c": "c",
            ".h": "c",
            # C++
            ".cpp": "cpp",
            ".hpp": "cpp",
            ".cc": "cpp",
            ".hh": "cpp",
            ".cxx": "cpp",
            ".hxx": "cpp",
            ".c++": "cpp",
            ".h++": "cpp",
        }

        return language_map.get(ext)

    @staticmethod
    def _get_tsp_parser(language: str) -> Parser | None:
        """Get or create a cached Tree-sitter parser for a language."""
        if language in _tsp_parsers:
            return _tsp_parsers[language]

        module_map = {
            "python": "tree_sitter_python",
            "javascript": "tree_sitter_javascript",
            "typescript": "tree_sitter_javascript",
            "c": "tree_sitter_c",
            "cpp": "tree_sitter_cpp",
            "go": "tree_sitter_go",
            "rust": "tree_sitter_rust",
            "java": "tree_sitter_java",
        }

        module_name = module_map.get(language)
        if not module_name:
            return None

        try:
            mod = __import__(module_name)
            parser = Parser(Language(mod.language()))
            _tsp_parsers[language] = parser
            return parser
        except Exception:
            return None

    def _extract_with_treesitter(self, content: str, file_path: str, language: str) -> list[Symbol]:
        """Extract symbols using Tree-sitter AST parsing."""
        parser = self._get_tsp_parser(language)
        if parser is None:
            return []

        try:
            tree = parser.parse(content.encode("utf-8"))
        except Exception:
            return []

        symbols: list[Symbol] = []
        node_map = _tsp_node_maps.get(language, {})

        def _find_name(node):
            """Recursively find the first identifier-like child node."""
            if node.type in (
                "identifier",
                "type_identifier",
                "field_identifier",
                "property_identifier",
            ):
                text = node.text
                if text:
                    return text.decode("utf-8", errors="ignore")
            for child in node.children:
                name = _find_name(child)
                if name:
                    return name
            return None

        def _walk(node):
            symbol_type = node_map.get(node.type)
            if symbol_type:
                name = _find_name(node)
                if name:
                    first_line = ""
                    if node.text:
                        first_line = node.text.decode("utf-8", errors="ignore").splitlines()[0]
                    symbols.append(
                        Symbol(
                            name=name,
                            symbol_type=symbol_type,
                            file_path=file_path,
                            line_number=node.start_point[0] + 1,
                            column=node.start_point[1],
                            signature=first_line,
                        )
                    )
            for child in node.children:
                _walk(child)

        try:
            _walk(tree.root_node)
        except Exception:
            return []

        return symbols

    def _extract_python_symbols(self, content: str, file_path: str) -> list[Symbol]:
        """Extract Python symbols from content."""
        symbols = []
        patterns = self.PATTERNS.get("python", {})

        lines = content.split("\n")
        current_class = None

        for line_num, line in enumerate(lines, 1):
            # Check for class definition
            class_match = patterns.get("class", re.compile("")).match(line)
            if class_match:
                current_class = class_match.group(1)
                symbols.append(
                    Symbol(
                        name=current_class,
                        symbol_type="class",
                        file_path=file_path,
                        line_number=line_num,
                        column=line.index("class") + 7,
                        signature=line.strip(),
                    )
                )
                continue

            # Check for method (indented function in class)
            if current_class and line.startswith("    def "):
                method_match = patterns.get("method", re.compile("")).match(line)
                if method_match:
                    symbols.append(
                        Symbol(
                            name=method_match.group(1),
                            symbol_type="method",
                            file_path=file_path,
                            line_number=line_num,
                            column=line.index("def") + 4,
                            signature=line.strip(),
                            parent=current_class,
                        )
                    )
                    continue

            # Check for function (not indented)
            if line.startswith("def "):
                func_match = patterns.get("function", re.compile("")).match(line)
                if func_match:
                    symbols.append(
                        Symbol(
                            name=func_match.group(1),
                            symbol_type="function",
                            file_path=file_path,
                            line_number=line_num,
                            column=line.index("def") + 4,
                            signature=line.strip(),
                        )
                    )
                    current_class = None

        return symbols

    def _extract_js_ts_symbols(self, content: str, file_path: str, language: str) -> list[Symbol]:
        """Extract JavaScript/TypeScript symbols."""
        symbols = []
        patterns = self.PATTERNS.get(language, {})

        for pattern_type, pattern in patterns.items():
            for match in pattern.finditer(content):
                # Get the first non-None group
                name = next((g for g in match.groups() if g is not None), None)
                if name:
                    # Calculate line number
                    line_num = content[: match.start()].count("\n") + 1
                    column = match.start() - content.rfind("\n", 0, match.start())

                    symbols.append(
                        Symbol(
                            name=name,
                            symbol_type=pattern_type,
                            file_path=file_path,
                            line_number=line_num,
                            column=column,
                        )
                    )

        return symbols

    def _extract_c_cpp_symbols(self, content: str, file_path: str, language: str) -> list[Symbol]:
        """Extract C/C++ symbols using regex patterns."""
        symbols = []
        patterns = self.PATTERNS.get(language, {})

        for pattern_type, pattern in patterns.items():
            for match in pattern.finditer(content):
                # Get the first non-None group
                name = next((g for g in match.groups() if g is not None), None)
                if name:
                    # Calculate line number
                    line_num = content[: match.start()].count("\n") + 1
                    column = match.start() - content.rfind("\n", 0, match.start())

                    symbols.append(
                        Symbol(
                            name=name,
                            symbol_type=pattern_type,
                            file_path=file_path,
                            line_number=line_num,
                            column=column,
                        )
                    )

        return symbols

    async def index_file(self, file_path: str) -> list[Symbol]:
        """Index a single file.

        Args:
            file_path: Path to file

        Returns:
            List of extracted symbols
        """
        language = self._get_language(file_path)
        if not language:
            return []

        try:
            content = await asyncio.to_thread(
                Path(file_path).read_text, encoding="utf-8", errors="ignore"
            )
        except (IOError, OSError):
            return []

        # Extract symbols based on language
        if language == "python":
            # Python: regex is 10x faster and accurate enough
            symbols = self._extract_python_symbols(content, file_path)
        elif HAS_TREE_SITTER and language in _tsp_node_maps:
            # Try tree-sitter first for non-Python languages
            symbols = self._extract_with_treesitter(content, file_path, language)
            if not symbols:
                # Fall back to regex if tree-sitter returns nothing
                if language in ("javascript", "typescript"):
                    symbols = self._extract_js_ts_symbols(content, file_path, language)
                elif language in ("c", "cpp"):
                    symbols = self._extract_c_cpp_symbols(content, file_path, language)
        else:
            # No tree-sitter support: use regex fallbacks
            if language in ("javascript", "typescript"):
                symbols = self._extract_js_ts_symbols(content, file_path, language)
            elif language in ("c", "cpp"):
                symbols = self._extract_c_cpp_symbols(content, file_path, language)
            else:
                symbols = []

        # Update index
        async with self._lock:
            # Remove old symbols for this file from buckets
            old_symbols = self._index.symbols_by_file.pop(file_path, [])
            self._index.symbols = [s for s in self._index.symbols if s.file_path != file_path]
            for symbol in old_symbols:
                if symbol.name in self._index.symbols_by_name:
                    self._index.symbols_by_name[symbol.name].remove(symbol)
                    if not self._index.symbols_by_name[symbol.name]:
                        del self._index.symbols_by_name[symbol.name]

            # Add new symbols to flat list and buckets
            self._index.symbols.extend(symbols)
            self._index.symbols_by_file[file_path] = symbols
            for symbol in symbols:
                self._index.symbols_by_name.setdefault(symbol.name, []).append(symbol)

            # Update file info
            self._index.file_index[file_path] = {
                "language": language,
                "symbol_count": len(symbols),
                "last_indexed": time.time(),
                "line_count": len(content.split("\n")),
            }

            self._indexed_files.add(file_path)
            self._index.last_updated = time.time()

        return symbols

    async def index_directory(
        self,
        directory: str,
        pattern: str = "*.py",
        progress_callback: Callable[[str, int, int], Any] | None = None,
    ) -> int:
        """Index all files in a directory.

        Args:
            directory: Directory to index
            pattern: File glob pattern
            progress_callback: Called with (file_path, current, total)

        Returns:
            Number of files indexed
        """
        from pathlib import Path

        files = list(Path(directory).rglob(pattern))
        files = [f for f in files if f.is_file()]

        indexed = 0
        for i, file_path in enumerate(files, 1):
            await self.index_file(str(file_path))
            indexed += 1

            if progress_callback:
                progress_callback(str(file_path), i, len(files))

        return indexed

    async def remove_file(self, file_path: str) -> None:
        """Remove a file from the index."""
        async with self._lock:
            # Remove from buckets
            old_symbols = self._index.symbols_by_file.pop(file_path, [])
            self._index.symbols = [s for s in self._index.symbols if s.file_path != file_path]
            for symbol in old_symbols:
                if symbol.name in self._index.symbols_by_name:
                    self._index.symbols_by_name[symbol.name].remove(symbol)
                    if not self._index.symbols_by_name[symbol.name]:
                        del self._index.symbols_by_name[symbol.name]

            self._index.file_index.pop(file_path, None)
            self._indexed_files.discard(file_path)

    def search_symbols(
        self, query: str, symbol_type: str | None = None, file_pattern: str | None = None
    ) -> list[Symbol]:
        """Search for symbols.

        Args:
            query: Search query (substring match)
            symbol_type: Optional symbol type filter
            file_pattern: Optional file path pattern

        Returns:
            Matching symbols
        """
        results = []

        # Fast path: exact symbol name match via bucket
        if self._index.symbols_by_name and query in self._index.symbols_by_name:
            for symbol in self._index.symbols_by_name[query]:
                if symbol_type and symbol.symbol_type != symbol_type:
                    continue
                if file_pattern and not fnmatch.fnmatch(symbol.file_path, file_pattern):
                    continue
                results.append(symbol)
            return results

        # Fast path: query looks like a file path via bucket
        if (
            self._index.symbols_by_file
            and ("/" in query or "\\" in query or "." in query)
            and query in self._index.symbols_by_file
        ):
            for symbol in self._index.symbols_by_file[query]:
                if symbol_type and symbol.symbol_type != symbol_type:
                    continue
                if file_pattern and not fnmatch.fnmatch(symbol.file_path, file_pattern):
                    continue
                results.append(symbol)
            return results

        # Fallback: substring scan over flat list
        query_lower = query.lower()
        for symbol in self._index.symbols:
            # Check name match
            if query_lower not in symbol.name.lower():
                continue

            # Check type filter
            if symbol_type and symbol.symbol_type != symbol_type:
                continue

            # Check file pattern
            if file_pattern and not fnmatch.fnmatch(symbol.file_path, file_pattern):
                continue

            results.append(symbol)

        return results

    def get_index_stats(self) -> dict[str, Any]:
        """Get index statistics."""
        return {
            "total_symbols": len(self._index.symbols),
            "indexed_files": len(self._indexed_files),
            "last_updated": self._index.last_updated,
            "symbol_types": self._get_symbol_type_counts(),
        }

    def _get_symbol_type_counts(self) -> dict[str, int]:
        """Get count of symbols by type."""
        counts: dict[str, int] = {}
        for symbol in self._index.symbols:
            counts[symbol.symbol_type] = counts.get(symbol.symbol_type, 0) + 1
        return counts

    def clear_index(self) -> None:
        """Clear the index."""
        self._index = CodeIndex()
        self._indexed_files.clear()

    def export_index(self, output_path: str) -> None:
        """Export index to JSON file."""
        data = {
            "symbols": [
                {
                    "name": s.name,
                    "type": s.symbol_type,
                    "file": s.file_path,
                    "line": s.line_number,
                    "column": s.column,
                    "parent": s.parent,
                }
                for s in self._index.symbols
            ],
            "files": self._index.file_index,
            "exported_at": time.time(),
        }

        Path(output_path).write_text(json.dumps(data, indent=2))

    def import_index(self, input_path: str) -> None:
        """Import index from JSON file."""
        data = json.loads(Path(input_path).read_text())

        self._index.symbols = [
            Symbol(
                name=s["name"],
                symbol_type=s["type"],
                file_path=s["file"],
                line_number=s["line"],
                column=s["column"],
                parent=s.get("parent"),
            )
            for s in data.get("symbols", [])
        ]

        self._index.file_index = data.get("files", {})
        self._indexed_files = set(self._index.file_index.keys())

        # Rebuild bucket indexes from flat list
        self._index.symbols_by_file = {}
        self._index.symbols_by_name = {}
        for symbol in self._index.symbols:
            self._index.symbols_by_file.setdefault(symbol.file_path, []).append(symbol)
            self._index.symbols_by_name.setdefault(symbol.name, []).append(symbol)


# Global indexer instance
_global_indexer: CodeIndexer | None = None


def get_code_indexer() -> CodeIndexer:
    """Get global code indexer."""
    global _global_indexer
    if _global_indexer is None:
        _global_indexer = CodeIndexer()
    return _global_indexer
