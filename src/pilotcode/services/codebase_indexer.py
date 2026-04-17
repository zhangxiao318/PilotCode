"""Codebase Indexer - Unified code indexing and retrieval system.

Provides enterprise-grade code indexing capabilities:
- Incremental indexing with file watching
- Semantic search using embeddings
- Symbol-based navigation
- Dependency graph analysis
- Context-aware code retrieval

Architecture:
    ┌─────────────────────────────────────────┐
    │         CodebaseIndexer                 │
    ├─────────────────────────────────────────┤
    │  ┌──────────┐  ┌──────────┐  ┌────────┐ │
    │  │  Symbol  │  │ Semantic │  │  AST   │ │
    │  │  Index   │  │  Search  │  │ Analysis│ │
    │  └──────────┘  └──────────┘  └────────┘ │
    │  ┌──────────┐  ┌──────────┐             │
    │  │ File     │  │Dependency│             │
    │  │ Metadata │  │  Graph   │             │
    │  └──────────┘  └──────────┘             │
    └─────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
from collections import defaultdict
import fnmatch

from .code_index import CodeIndexer, Symbol, get_code_indexer
from .advanced_code_analyzer import ASTCodeAnalyzer, ModuleInfo, get_analyzer
from .embedding_service import EmbeddingService, SearchResult, get_embedding_service
from .file_metadata_cache import FileMetadataCache, get_file_metadata_cache


@dataclass
class CodeSnippet:
    """A code snippet with metadata for retrieval."""

    id: str
    content: str
    file_path: str
    start_line: int
    end_line: int
    language: str
    symbol_name: Optional[str] = None
    symbol_type: Optional[str] = None
    embedding: Optional[list[float]] = None
    relevance_score: float = 0.0


@dataclass
class SearchQuery:
    """Structured search query."""

    text: str
    query_type: str = "semantic"  # semantic, symbol, file, regex
    file_pattern: Optional[str] = None
    language: Optional[str] = None
    max_results: int = 10
    include_content: bool = True


@dataclass
class CodebaseStats:
    """Statistics about the indexed codebase."""

    total_files: int = 0
    total_symbols: int = 0
    total_snippets: int = 0
    languages: dict[str, int] = field(default_factory=dict)
    last_indexed: float = 0.0
    index_size_bytes: int = 0


@dataclass
class ContextWindow:
    """A window of code context for LLM."""

    snippets: list[CodeSnippet]
    total_tokens: int
    total_chars: int
    source_files: list[str]


class CodebaseIndexer:
    """Unified codebase indexer with semantic and symbol search.

    This is the main entry point for code indexing and retrieval.
    It coordinates multiple specialized services:
    - CodeIndexer: Symbol extraction and lookup
    - ASTCodeAnalyzer: Deep code analysis
    - EmbeddingService: Semantic search
    - FileMetadataCache: File tracking and change detection
    """

    # File extensions to index
    SUPPORTED_EXTENSIONS = {
        # Python
        ".py",
        ".pyw",
        ".pyi",
        # JavaScript/TypeScript
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
        # C/C++
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".cc",
        ".hh",
        ".cxx",
        ".hxx",
        ".c++",
        ".h++",
        # Go, Rust, Java
        ".go",
        ".rs",
        ".java",
        # Ruby, PHP, Swift, Kotlin
        ".rb",
        ".php",
        ".swift",
        ".kt",
        # Scala, R, Objective-C, C#
        ".scala",
        ".r",
        ".m",
        ".mm",
        ".cs",
        # F#, Elm
        ".fs",
        ".fsx",
        ".elm",
    }

    # Directories to ignore
    IGNORE_DIRS = {
        ".git",
        ".svn",
        ".hg",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        "env",
        ".env",
        "dist",
        "build",
        "target",
        ".tox",
        ".pytest_cache",
        ".mypy_cache",
        "*.egg-info",
        ".idea",
        ".vscode",
        ".vs",
        "out",
        "bin",
        "obj",
    }

    def __init__(
        self,
        root_path: str | Path,
        embedding_service: Optional[EmbeddingService] = None,
        enable_file_watcher: bool = True,
    ):
        self.root_path = Path(root_path).resolve()
        self.embedding_service = embedding_service or get_embedding_service()

        # Initialize sub-services
        self._symbol_indexer = get_code_indexer()
        self._ast_analyzer = get_analyzer()
        self._file_cache = get_file_metadata_cache()

        # State
        self._is_indexing = False
        self._indexed_files: set[str] = set()
        self._file_hashes: dict[str, str] = {}  # path -> content hash
        self._stats = CodebaseStats()

        # Context management
        self._recently_accessed: list[str] = []  # LRU cache of file paths
        self._max_recent_files = 50

        # Event callbacks
        self._on_index_progress: Optional[Callable[[str, int, int], None]] = None

        # Persistent cache path
        self._cache_path = self.root_path / ".pilotcode_index_cache.json"

        # Try to load cached index
        try:
            if self._cache_path.exists():
                self.import_index(str(self._cache_path))
        except Exception:
            pass  # Ignore cache load errors

    def set_progress_callback(self, callback: Callable[[str, int, int], None]) -> None:
        """Set callback for indexing progress: (file_path, current, total)."""
        self._on_index_progress = callback

    async def index_codebase(
        self,
        incremental: bool = True,
        max_files: Optional[int] = None,
    ) -> CodebaseStats:
        """Index the entire codebase.

        Args:
            incremental: Only index changed files if True
            max_files: Maximum number of files to index (None for all)

        Returns:
            Statistics about the indexed codebase
        """
        self._is_indexing = True
        start_time = time.time()

        try:
            # Find all source files
            files_to_index = self._find_source_files(max_files)

            if incremental:
                files_to_index = self._filter_unchanged_files(files_to_index)

            total = len(files_to_index)
            indexed = 0

            # Index files in batches for better performance
            batch_size = 10
            for i in range(0, total, batch_size):
                batch = files_to_index[i : i + batch_size]
                await asyncio.gather(*[self._index_single_file(f) for f in batch])
                indexed += len(batch)

                if self._on_index_progress:
                    for f in batch:
                        self._on_index_progress(str(f), indexed, total)

            # Update stats
            self._stats.total_files = len(self._indexed_files)
            self._stats.total_symbols = len(self._symbol_indexer._index.symbols)
            self._stats.last_indexed = time.time()

            # Persist index to disk for reuse across subprocesses
            try:
                self.export_index(str(self._cache_path))
            except Exception:
                pass  # Ignore cache write errors

            return self._stats

        finally:
            self._is_indexing = False

    def _find_source_files(self, max_files: Optional[int] = None) -> list[Path]:
        """Find all source files in the codebase."""
        files = []

        try:
            for path in self.root_path.rglob("*"):
                try:
                    if not path.is_file():
                        continue

                    # Skip symlinks to avoid loops
                    if path.is_symlink():
                        continue

                    # Check if should ignore
                    if self._should_ignore(path):
                        continue

                    # Check extension
                    if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                        continue

                    files.append(path)

                    if max_files and len(files) >= max_files:
                        break
                except (OSError, PermissionError):
                    # Skip files we can't access
                    continue
        except Exception as e:
            print(f"Error finding source files: {e}")

        return sorted(files)

    def _should_ignore(self, path: Path) -> bool:
        """Check if path should be ignored."""
        path_str = str(path)

        # Get relative path from root
        try:
            rel_path = path.relative_to(self.root_path)
            rel_str = str(rel_path)
        except ValueError:
            rel_str = path_str

        # Check ignore directories (in full path for safety, and relative)
        for ignore_dir in self.IGNORE_DIRS:
            if ignore_dir in path_str:
                return True

        # Check hidden files/directories (only in relative path, not full path)
        # This avoids ignoring files in paths like /home/user/.local/...
        rel_parts = rel_path.parts if isinstance(rel_path, Path) else Path(rel_str).parts
        for part in rel_parts:
            if part.startswith(".") and part not in (".", ".."):
                return True

        # Check file size (skip files > 1MB)
        try:
            if path.stat().st_size > 1_000_000:
                return True
        except OSError:
            return True

        return False

    def _filter_unchanged_files(self, files: list[Path]) -> list[Path]:
        """Filter out files that haven't changed since last index."""
        changed = []

        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                current_hash = hashlib.sha256(content.encode()).hexdigest()

                path_str = str(file_path)
                if path_str not in self._file_hashes or self._file_hashes[path_str] != current_hash:
                    changed.append(file_path)
                    self._file_hashes[path_str] = current_hash
            except Exception:
                # If we can't read, include it anyway
                changed.append(file_path)

        return changed

    async def _index_single_file(self, file_path: Path | str) -> None:
        """Index a single file across all services."""
        if isinstance(file_path, str):
            file_path = Path(file_path)
        path_str = str(file_path)

        try:
            # Read content
            content = file_path.read_text(encoding="utf-8", errors="ignore")

            # 1. Index symbols
            await self._symbol_indexer.index_file(path_str)

            # 2. AST analysis (Python only for now)
            if file_path.suffix == ".py":
                self._ast_analyzer.analyze_file(file_path)

            # 3. Create and embed code snippets
            await self._index_code_snippets(file_path, content)

            # 4. Update file cache (skip if method not available)
            try:
                if hasattr(self._file_cache, "set"):
                    self._file_cache.set(
                        path_str,
                        {
                            "language": self._detect_language(file_path),
                            "lines": len(content.split("\n")),
                            "last_indexed": time.time(),
                        },
                    )
            except Exception:
                pass

            self._indexed_files.add(path_str)

            # Update language stats
            lang = self._detect_language(file_path)
            self._stats.languages[lang] = self._stats.languages.get(lang, 0) + 1

        except Exception as e:
            # Log error but don't stop indexing
            print(f"Error indexing {file_path}: {e}")

    async def _index_code_snippets(self, file_path: Path, content: str) -> None:
        """Create and index code snippets for semantic search."""
        # Split content into chunks (functions, classes, or fixed-size blocks)
        chunks = self._chunk_code(content, file_path.suffix)

        for chunk in chunks:
            snippet_id = f"{file_path}:{chunk['start_line']}"

            # Create snippet
            snippet = CodeSnippet(
                id=snippet_id,
                content=chunk["content"],
                file_path=str(file_path),
                start_line=chunk["start_line"],
                end_line=chunk["end_line"],
                language=self._detect_language(file_path),
                symbol_name=chunk.get("symbol_name"),
                symbol_type=chunk.get("symbol_type"),
            )

            # Embed and store
            try:
                await self.embedding_service.embed_code(
                    code=snippet.content,
                    file_path=snippet.file_path,
                    language=snippet.language,
                )
                self._stats.total_snippets += 1
            except Exception:
                # Embedding might fail, continue anyway
                pass

    def _chunk_code(
        self,
        content: str,
        file_extension: str,
        max_chunk_size: int = 100,
        overlap: int = 10,
    ) -> list[dict]:
        """Split code into chunks for embedding.

        Strategy:
        1. Try to chunk by symbols (functions, classes)
        2. Fall back to fixed-size sliding windows
        """
        lines = content.split("\n")
        chunks = []

        if file_extension == ".py":
            # Python: chunk by function/class definitions
            import ast

            try:
                tree = ast.parse(content)
                for node in ast.iter_child_nodes(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        start_line = node.lineno
                        end_line = (
                            node.end_lineno if hasattr(node, "end_lineno") else start_line + 50
                        )
                        chunk_content = "\n".join(lines[start_line - 1 : end_line])

                        chunks.append(
                            {
                                "content": chunk_content,
                                "start_line": start_line,
                                "end_line": end_line,
                                "symbol_name": node.name,
                                "symbol_type": (
                                    "class" if isinstance(node, ast.ClassDef) else "function"
                                ),
                            }
                        )
            except SyntaxError:
                pass

        # If no symbol chunks or other languages, use sliding window
        if not chunks:
            for i in range(0, len(lines), max_chunk_size - overlap):
                start = i
                end = min(i + max_chunk_size, len(lines))
                chunk_content = "\n".join(lines[start:end])

                chunks.append(
                    {
                        "content": chunk_content,
                        "start_line": start + 1,
                        "end_line": end,
                    }
                )

        return chunks

    def _detect_language(self, file_path: Path) -> str:
        """Detect programming language from file extension."""
        ext_map = {
            # Python
            ".py": "python",
            ".pyw": "python",
            ".pyi": "python",
            # JavaScript/TypeScript
            ".js": "javascript",
            ".jsx": "javascript",
            ".mjs": "javascript",
            ".cjs": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
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
            # Go, Rust, Java
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            # Ruby, PHP, Swift, Kotlin
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".kts": "kotlin",
        }
        return ext_map.get(file_path.suffix.lower(), "unknown")

    async def search(self, query: SearchQuery) -> list[CodeSnippet]:
        """Search the codebase using various strategies.

        Args:
            query: SearchQuery with text, type, and filters

        Returns:
            List of code snippets sorted by relevance
        """
        results = []

        if query.query_type == "semantic":
            results = await self._semantic_search(query)
        elif query.query_type == "symbol":
            results = self._symbol_search(query)
        elif query.query_type == "regex":
            results = self._regex_search(query)
        elif query.query_type == "file":
            results = self._file_search(query)

        # Apply filters
        if query.file_pattern:
            results = [r for r in results if fnmatch.fnmatch(r.file_path, query.file_pattern)]

        if query.language:
            results = [r for r in results if r.language == query.language]

        # Sort by relevance and limit
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results[: query.max_results]

    async def _semantic_search(self, query: SearchQuery) -> list[CodeSnippet]:
        """Semantic search using embeddings."""
        try:
            search_results = await self.embedding_service.search(
                query.text,
                top_k=query.max_results * 2,  # Get more for filtering
            )

            snippets = []
            for result in search_results:
                meta = result.vector.metadata

                snippet = CodeSnippet(
                    id=result.vector.id,
                    content=result.vector.text,
                    file_path=meta.get("file_path", "unknown"),
                    start_line=meta.get("start_line", 1),
                    end_line=meta.get("end_line", 1),
                    language=meta.get("language", "unknown"),
                    relevance_score=result.score,
                )
                snippets.append(snippet)

            return snippets

        except Exception as e:
            print(f"Semantic search error: {e}")
            return []

    def _symbol_search(self, query: SearchQuery) -> list[CodeSnippet]:
        """Search by symbol name."""
        symbols = self._symbol_indexer.search_symbols(query.text)

        snippets = []
        for symbol in symbols:
            # Read the symbol's content
            try:
                content = self._read_symbol_content(symbol)
                snippet = CodeSnippet(
                    id=f"{symbol.file_path}:{symbol.line_number}",
                    content=content,
                    file_path=symbol.file_path,
                    start_line=symbol.line_number,
                    end_line=symbol.line_number + content.count("\n"),
                    language=self._detect_language(Path(symbol.file_path)),
                    symbol_name=symbol.name,
                    symbol_type=symbol.symbol_type,
                    relevance_score=1.0,  # Exact symbol match
                )
                snippets.append(snippet)
            except Exception:
                continue

        return snippets

    def _regex_search(self, query: SearchQuery) -> list[CodeSnippet]:
        """Search using regex pattern."""
        import re

        try:
            pattern = re.compile(query.text, re.IGNORECASE)
        except re.error:
            return []

        snippets = []
        for file_path in self._indexed_files:
            try:
                content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
                lines = content.split("\n")

                for i, line in enumerate(lines, 1):
                    if pattern.search(line):
                        snippet = CodeSnippet(
                            id=f"{file_path}:{i}",
                            content=line.strip(),
                            file_path=file_path,
                            start_line=i,
                            end_line=i,
                            language=self._detect_language(Path(file_path)),
                            relevance_score=0.5,
                        )
                        snippets.append(snippet)
            except Exception:
                continue

        return snippets

    def _file_search(self, query: SearchQuery) -> list[CodeSnippet]:
        """Search by file name pattern."""
        snippets = []

        for file_path in self._indexed_files:
            if query.text.lower() in Path(file_path).name.lower():
                try:
                    content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
                    snippet = CodeSnippet(
                        id=file_path,
                        content=content[:2000] if len(content) > 2000 else content,
                        file_path=file_path,
                        start_line=1,
                        end_line=content.count("\n"),
                        language=self._detect_language(Path(file_path)),
                        relevance_score=0.8,
                    )
                    snippets.append(snippet)
                except Exception:
                    continue

        return snippets

    def _read_symbol_content(self, symbol: Symbol, context_lines: int = 5) -> str:
        """Read content around a symbol."""
        try:
            with open(symbol.file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            start = max(0, symbol.line_number - 1 - context_lines)
            end = min(len(lines), symbol.line_number + context_lines)

            return "".join(lines[start:end])
        except Exception:
            return symbol.signature or ""

    async def build_context(
        self,
        query: str,
        max_tokens: int = 4000,
        include_related: bool = True,
    ) -> ContextWindow:
        """Build a context window for LLM from query.

        This is the main method for RAG (Retrieval Augmented Generation).
        It retrieves the most relevant code snippets and formats them for LLM consumption.

        Args:
            query: The user's query
            max_tokens: Maximum tokens for context
            include_related: Whether to include related symbols

        Returns:
            ContextWindow with snippets and metadata
        """
        snippets = []

        # 1. Semantic search
        semantic_results = await self.search(
            SearchQuery(
                text=query,
                query_type="semantic",
                max_results=5,
            )
        )
        snippets.extend(semantic_results)

        # 2. Symbol search (if query looks like a symbol name)
        if self._looks_like_symbol(query):
            symbol_results = self.search(
                SearchQuery(
                    text=query,
                    query_type="symbol",
                    max_results=3,
                )
            )
            snippets.extend(symbol_results)

        # 3. Get related symbols (call graph)
        if include_related:
            for snippet in list(snippets):
                if snippet.symbol_name:
                    related = self._get_related_symbols(snippet)
                    snippets.extend(related)

        # Deduplicate and sort
        seen = set()
        unique_snippets = []
        for s in snippets:
            key = f"{s.file_path}:{s.start_line}"
            if key not in seen:
                seen.add(key)
                unique_snippets.append(s)

        unique_snippets.sort(key=lambda x: x.relevance_score, reverse=True)

        # Build context within token budget
        selected = []
        total_chars = 0
        max_chars = max_tokens * 4  # Rough estimate: 4 chars per token

        for snippet in unique_snippets:
            snippet_chars = len(snippet.content)
            if total_chars + snippet_chars > max_chars:
                break
            selected.append(snippet)
            total_chars += snippet_chars

        return ContextWindow(
            snippets=selected,
            total_tokens=total_chars // 4,
            total_chars=total_chars,
            source_files=list(set(s.file_path for s in selected)),
        )

    def _looks_like_symbol(self, text: str) -> bool:
        """Check if text looks like a symbol name (CamelCase or snake_case)."""
        import re

        # Match CamelCase or snake_case patterns
        return bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", text.strip()))

    def _get_related_symbols(self, snippet: CodeSnippet) -> list[CodeSnippet]:
        """Get symbols related to a snippet (same file, same class, etc.)."""
        related = []

        # Get other symbols from the same file
        file_symbols = self._symbol_indexer.find_in_file(snippet.file_path)

        for symbol in file_symbols:
            if symbol.name != snippet.symbol_name:
                try:
                    content = self._read_symbol_content(symbol, context_lines=3)
                    related.append(
                        CodeSnippet(
                            id=f"{symbol.file_path}:{symbol.line_number}",
                            content=content,
                            file_path=symbol.file_path,
                            start_line=symbol.line_number,
                            end_line=symbol.line_number + content.count("\n"),
                            language=snippet.language,
                            symbol_name=symbol.name,
                            symbol_type=symbol.symbol_type,
                            relevance_score=0.3,  # Lower score for related
                        )
                    )
                except Exception:
                    continue

        return related[:3]  # Limit related symbols

    def get_stats(self) -> CodebaseStats:
        """Get current indexing statistics."""
        # Update language stats
        lang_counts = defaultdict(int)
        for file_path in self._indexed_files:
            lang = self._detect_language(Path(file_path))
            lang_counts[lang] += 1

        self._stats.languages = dict(lang_counts)

        return self._stats

    async def remove_file(self, file_path: str) -> None:
        """Remove a file from the index."""
        await self._symbol_indexer.remove_file(file_path)
        self._indexed_files.discard(file_path)
        self._file_hashes.pop(file_path, None)

    def clear_index(self) -> None:
        """Clear all indexed data."""
        self._symbol_indexer.clear_index()
        self._indexed_files.clear()
        self._file_hashes.clear()
        self._stats = CodebaseStats()

    def export_index(self, output_path: str) -> None:
        """Export index to file."""
        data = {
            "root_path": str(self.root_path),
            "stats": {
                "total_files": self._stats.total_files,
                "total_symbols": self._stats.total_symbols,
                "last_indexed": self._stats.last_indexed,
            },
            "indexed_files": list(self._indexed_files),
            "file_hashes": self._file_hashes,
        }

        Path(output_path).write_text(json.dumps(data, indent=2))

        # Also export symbol index
        symbol_cache_path = str(Path(output_path).with_suffix(".symbols.json"))
        try:
            self._symbol_indexer.export_index(symbol_cache_path)
        except Exception:
            pass

    def import_index(self, input_path: str) -> None:
        """Import index from file."""
        data = json.loads(Path(input_path).read_text())

        self._indexed_files = set(data.get("indexed_files", []))
        self._file_hashes = data.get("file_hashes", {})

        stats = data.get("stats", {})
        self._stats.total_files = stats.get("total_files", 0)
        self._stats.total_symbols = stats.get("total_symbols", 0)
        self._stats.last_indexed = stats.get("last_indexed", 0)

        # Also import symbol index
        symbol_cache_path = str(Path(input_path).with_suffix(".symbols.json"))
        try:
            if Path(symbol_cache_path).exists():
                self._symbol_indexer.import_index(symbol_cache_path)
        except Exception:
            pass


# Global indexer instances (per root path)
_global_indexers: dict[str, CodebaseIndexer] = {}


def get_codebase_indexer(root_path: Optional[str] = None) -> CodebaseIndexer:
    """Get or create codebase indexer for the given root path.

    Each root path has its own indexer instance.
    """
    global _global_indexers

    if root_path is None:
        root_path = str(Path.cwd())

    # Normalize path
    root_path = str(Path(root_path).resolve())

    if root_path not in _global_indexers:
        _global_indexers[root_path] = CodebaseIndexer(root_path)

    return _global_indexers[root_path]


def reset_codebase_indexer(root_path: Optional[str] = None) -> None:
    """Reset indexer for a specific path or all indexers."""
    global _global_indexers

    if root_path is None:
        _global_indexers.clear()
    else:
        root_path = str(Path(root_path).resolve())
        _global_indexers.pop(root_path, None)
