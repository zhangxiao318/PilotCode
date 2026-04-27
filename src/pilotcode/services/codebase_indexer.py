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
from typing import Callable, Optional
from collections import defaultdict
import fnmatch

from .code_index import Symbol, get_code_indexer
from .advanced_code_analyzer import get_analyzer
from .embedding_service import EmbeddingService, get_embedding_service
from .file_metadata_cache import get_file_metadata_cache
from .hierarchical_index import HierarchicalIndexBuilder
from .memory_kb import get_memory_kb, MemoryEntry


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
        "extracted",
        "temp",
        "tmp",
        "_temp",
        "_tmp",
        # C/C++ build artifacts (Linux kernel, embedded, etc.)
        "*.d",  # dependency files
        "*.cmd",  # kernel build cmd files
        "*.o",  # object files
        "*.ko",  # kernel modules
        "*.mod",  # module files
        "*.mod.c",  # generated module C files
        "*.order",  # module order files
        "*.symvers",  # symbol versions
        "*.a",  # static libraries
        "*.so",  # shared libraries
        "*.dll",  # Windows DLLs
        "*.exe",  # executables
        "*.elf",  # ELF binaries
        "*.hex",  # hex firmware
        "*.bin",  # binary firmware
        "*.map",  # linker map files
        "*.lst",  # listing files
        "*.srec",  # S-record files
        "*.ihex",  # Intel hex
        # Java/Gradle/Maven build
        "*.class",
        "*.jar",
        "*.war",
        "*.ear",
        "gradle",
        ".gradle",
        # Rust build
        "Cargo.lock",
        # Go build
        "go.sum",
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

        # Hierarchical index
        self._hierarchical_builder: HierarchicalIndexBuilder | None = None
        self._hierarchical_cache_path: Path | None = None

        # Project memory / knowledge base
        self._memory_kb = get_memory_kb(self.root_path)

        # Context management
        self._recently_accessed: list[str] = []  # LRU cache of file paths
        self._max_recent_files = 50

        # Event callbacks
        self._on_index_progress: Optional[Callable[[str, int, int], None]] = None

        # Console progress (auto-enabled for long operations)
        self._console_progress_enabled = False

        # Persistent cache path (outside git workspace to avoid polluting diffs)
        import hashlib

        cache_dir = Path.home() / ".cache" / "pilotcode" / "index_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_key = hashlib.md5(str(self.root_path.resolve()).encode()).hexdigest()[:16]
        self._cache_path = cache_dir / f"{cache_key}.json"
        self._hierarchical_cache_path = cache_dir / f"{cache_key}_hierarchical.json"

        # Try to load cached index
        try:
            if self._cache_path.exists():
                self.import_index(str(self._cache_path))
        except Exception:
            pass  # Ignore cache load errors

        # Try to load cached hierarchical index
        try:
            if self._hierarchical_cache_path.exists():
                self._hierarchical_builder = HierarchicalIndexBuilder(self.root_path)
                self._hierarchical_builder.load(self._hierarchical_cache_path)
        except Exception:
            pass  # Ignore hierarchical cache load errors

    def set_progress_callback(self, callback: Callable[[str, int, int], None] | None) -> None:
        """Set callback for indexing progress: (file_path, current, total)."""
        self._on_index_progress = callback
        # If an external callback is provided, disable console progress
        # to avoid duplicate output.
        if callback is not None:
            self._console_progress_enabled = False

    async def index_codebase(
        self,
        incremental: bool = True,
        max_files: Optional[int] = None,
    ) -> CodebaseStats:
        """Index the entire codebase.

        Args:
            incremental: Only index changed files if True. When True, max_files
                is ignored and all files on disk are scanned (then filtered by
                content hash). This ensures modifications in any part of the
                repo are discovered.
            max_files: Maximum number of files to index. Only applies when
                incremental=False (full reindex).

        Returns:
            Statistics about the indexed codebase
        """
        self._is_indexing = True
        start_time = time.time()

        try:
            # Bugfix: incremental mode must scan ALL files on disk to discover
            # changes anywhere in the repo. max_files only limits full reindex.
            scan_max = None if incremental else max_files
            all_source_files = self._find_source_files(scan_max)

            if incremental:
                # Filter to only changed files
                files_to_index = self._filter_unchanged_files(all_source_files)

                # Bugfix: detect files that were deleted since last index
                current_files = {str(f) for f in all_source_files}
                deleted_files = self._indexed_files - current_files
                if deleted_files:
                    for df in deleted_files:
                        await self.remove_file(df)
                        # Also clear old embeddings for this file
                        try:
                            self.embedding_service.delete_by_file_path(df)
                        except Exception:
                            pass
            else:
                files_to_index = all_source_files

            total = len(files_to_index)
            indexed = 0

            # Time estimation & auto-enable console progress for large batches
            estimated_seconds = self._estimate_indexing_time(files_to_index)
            if estimated_seconds > 30 and not self._on_index_progress:
                self._console_progress_enabled = True
                print(
                    f"[CodeIndex] Estimated indexing time: {estimated_seconds:.0f}s "
                    f"for {total} files. Progress will be shown."
                )

            # Index files in batches for better performance
            batch_size = 10
            checkpoint_interval = 50  # Save progress every 500 files
            batches_since_checkpoint = 0
            console_report_interval = max(1, total // 20)  # Report ~20 times

            for i in range(0, total, batch_size):
                batch = files_to_index[i : i + batch_size]
                await asyncio.gather(*[self._index_single_file(f) for f in batch])
                indexed += len(batch)
                batches_since_checkpoint += 1

                if self._on_index_progress:
                    for f in batch:
                        self._on_index_progress(str(f), indexed, total)

                if self._console_progress_enabled and indexed % console_report_interval == 0:
                    pct = indexed / total * 100
                    elapsed = time.time() - start_time
                    remaining = (elapsed / indexed) * (total - indexed) if indexed else 0
                    print(
                        f"[CodeIndex] {indexed}/{total} ({pct:.0f}%) "
                        f"~{remaining:.0f}s remaining"
                    )

                # Checkpoint: periodically save intermediate state so that
                # a crash or cancellation doesn't lose all progress.
                if batches_since_checkpoint >= checkpoint_interval:
                    batches_since_checkpoint = 0
                    try:
                        self._save_checkpoint()
                    except Exception:
                        pass  # Non-critical, continue indexing

            # Update stats
            self._stats.total_files = len(self._indexed_files)
            self._stats.total_symbols = len(self._symbol_indexer._index.symbols)
            self._stats.last_indexed = time.time()

            # Build hierarchical index for large codebases (incremental)
            try:
                self._build_hierarchical_index()
            except Exception:
                pass  # Non-critical, continue if it fails

            # Final persist
            try:
                self.export_index(str(self._cache_path))
            except Exception:
                pass  # Ignore cache write errors

            return self._stats

        finally:
            self._is_indexing = False
            self._console_progress_enabled = False

    def _find_source_files(self, max_files: Optional[int] = None) -> list[Path]:
        """Find all source files in the codebase.

        Uses ``git ls-files`` when inside a git repository (10-100x faster
        than ``rglob`` for large projects like Linux kernel). Falls back to
        ``rglob`` for non-git directories.
        """
        files: list[Path] = []

        # Fast path: use git ls-files for tracked source files
        if (self.root_path / ".git").exists():
            try:
                git_files = self._find_source_files_via_git()
                if git_files:
                    files = git_files
                    if max_files and len(files) > max_files:
                        files = files[:max_files]
                    return sorted(files)
            except Exception:
                pass  # Fall back to rglob

        # Fallback: recursive filesystem walk
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

    def _find_source_files_via_git(self) -> list[Path]:
        """Use git ls-files for fast file discovery inside a git repo."""
        import subprocess

        # Build extension patterns for git ls-files
        extensions = self.SUPPORTED_EXTENSIONS
        patterns = [f"*{ext}" for ext in extensions]

        # Run git ls-files for tracked files + untracked but not ignored files
        all_paths: set[str] = set()

        try:
            result = subprocess.run(
                ["git", "-C", str(self.root_path), "ls-files", "-z"] + patterns,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                for p in result.stdout.split("\0"):
                    if p:
                        all_paths.add(p)
        except Exception:
            pass

        # Also include untracked source files (but respect .gitignore)
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.root_path),
                    "ls-files",
                    "-z",
                    "--others",
                    "--exclude-standard",
                ]
                + patterns,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                for p in result.stdout.split("\0"):
                    if p:
                        all_paths.add(p)
        except Exception:
            pass

        # Convert to Path objects and apply ignore filter
        files: list[Path] = []
        for rel_str in all_paths:
            path = self.root_path / rel_str
            if path.is_file() and not self._should_ignore(path):
                files.append(path)

        return files

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

    def _estimate_indexing_time(self, files: list[Path]) -> float:
        """Estimate total indexing time in seconds.

        Uses per-language heuristics based on measured performance:
        - Python (regex): ~3ms per file
        - Tree-sitter languages: ~12ms per file
        - Overhead (embed + file I/O): ~2ms per file
        """
        python_count = 0
        ts_count = 0
        for f in files:
            if f.suffix.lower() == ".py":
                python_count += 1
            else:
                ts_count += 1
        # Conservative estimate: include a small fixed overhead for parser init
        init_overhead = 0.1 if ts_count > 0 else 0.0
        return init_overhead + python_count * 0.003 + ts_count * 0.014

    def _save_checkpoint(self) -> None:
        """Save a lightweight checkpoint during long indexing runs.

        Only saves file hashes and the indexed-files set (cheap).
        Symbols and embeddings are already persisted by their
        respective sub-services.
        """
        try:
            self.export_index(str(self._cache_path))
        except Exception:
            pass

    def _build_hierarchical_index(self) -> None:
        """Build or rebuild the hierarchical index from current state.

        Uses a lightweight incremental check: if the set of indexed files
        hasn't changed since the last build, skip reconstruction.
        """
        if len(self._indexed_files) < 10:
            # Not enough files to benefit from hierarchical indexing
            return

        # Incremental check: skip if indexed files haven't changed
        if (
            self._hierarchical_builder is not None
            and self._hierarchical_builder.get_master_index() is not None
        ):
            last_indexed = set(
                self._hierarchical_builder.get_master_index().total_files and [] or []
            )
            # We don't have the exact file set stored in the old master index,
            # so we use a hash of the sorted file list as a cheap fingerprint.
            current_fingerprint = hashlib.sha256(
                "\n".join(sorted(self._indexed_files)).encode()
            ).hexdigest()[:16]
            stored_fingerprint = getattr(self._hierarchical_builder, "_file_fingerprint", None)
            if stored_fingerprint == current_fingerprint:
                return  # No changes, skip rebuild
            # Store fingerprint for next time
            self._hierarchical_builder._file_fingerprint = current_fingerprint

        # Prepare AST cache and symbol index (use relative paths as keys)
        def _dataclass_to_dict(obj: Any) -> Any:
            """Recursively convert dataclass instances to plain dicts."""
            if hasattr(obj, "__dataclass_fields__"):
                return {k: _dataclass_to_dict(v) for k, v in obj.__dict__.items()}
            if isinstance(obj, list):
                return [_dataclass_to_dict(v) for v in obj]
            if isinstance(obj, dict):
                return {k: _dataclass_to_dict(v) for k, v in obj.items()}
            return obj

        ast_cache: dict[str, Any] = {}
        for path_str, module in self._ast_analyzer._cache.items():
            ast_cache[path_str] = _dataclass_to_dict(module)

        symbol_index: dict[str, list[dict]] = {}
        for symbol in self._symbol_indexer._index.symbols:
            fp = symbol.file_path
            # Normalize to relative path for matching
            rel_fp = fp
            try:
                rel_fp = str(Path(fp).relative_to(self.root_path)).replace("\\", "/")
            except ValueError:
                pass
            if rel_fp not in symbol_index:
                symbol_index[rel_fp] = []
            symbol_index[rel_fp].append(
                {
                    "name": symbol.name,
                    "type": symbol.symbol_type,
                    "line": symbol.line_number,
                    "signature": symbol.signature or "",
                    "parent": symbol.parent or "",
                }
            )

        self._hierarchical_builder = HierarchicalIndexBuilder(self.root_path)
        self._hierarchical_builder.build(
            files=list(self._indexed_files),
            ast_cache=ast_cache,
            symbol_index=symbol_index,
        )

        # Persist
        if self._hierarchical_cache_path:
            try:
                self._hierarchical_builder.save(self._hierarchical_cache_path)
            except Exception:
                pass

    def get_master_index_text(self, max_subgraphs: int | None = None) -> str:
        """Get the formatted master index text (Tier 1)."""
        if self._hierarchical_builder is None:
            return ""
        return self._hierarchical_builder.format_master_index(max_subgraphs=max_subgraphs)

    def get_subgraph_text(self, subgraph_id: str, max_symbols: int = 100) -> str:
        """Get formatted detail for a specific subgraph (Tier 2)."""
        if self._hierarchical_builder is None:
            return f"# Subgraph not found: {subgraph_id}\n(Hierarchical index not built yet)"
        return self._hierarchical_builder.format_subgraph_detail(
            subgraph_id, max_symbols=max_symbols
        )

    def list_subgraphs(self) -> list[dict[str, Any]]:
        """List available subgraphs with basic info."""
        if (
            self._hierarchical_builder is None
            or self._hierarchical_builder.get_master_index() is None
        ):
            return []
        master = self._hierarchical_builder.get_master_index()
        return [
            {
                "id": sg.id,
                "name": sg.name,
                "path": sg.path,
                "file_count": sg.file_count,
                "symbol_count": sg.symbol_count,
            }
            for sg in master.subgraphs
        ]

    def _filter_unchanged_files(self, files: list[Path]) -> list[Path]:
        """Filter out files that haven't changed since last index.

        Uses a two-layer check for speed:
        1. mtime comparison (fast, no I/O for unchanged files)
        2. SHA256 content hash (slow but accurate, catches content edits
           that preserve mtime)
        """
        changed = []
        # Layer 1: fast mtime check
        for file_path in files:
            path_str = str(file_path)
            try:
                stat = file_path.stat()
                mtime = stat.st_mtime
                mtime_key = f"{path_str}:mtime"
                stored_mtime = self._file_hashes.get(mtime_key)
                # If mtime unchanged and we have a stored hash, skip reading
                if stored_mtime == str(mtime) and path_str in self._file_hashes:
                    continue  # File unchanged
                # mtime changed or no prior record -> need hash check
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                current_hash = hashlib.sha256(content.encode()).hexdigest()
                if self._file_hashes.get(path_str) != current_hash:
                    changed.append(file_path)
                    self._file_hashes[path_str] = current_hash
                # Update mtime regardless (so next check is fast)
                self._file_hashes[mtime_key] = str(mtime)
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

            # Store hash immediately so incremental filtering can use it
            current_hash = hashlib.sha256(content.encode()).hexdigest()
            self._file_hashes[path_str] = current_hash

            # 0. Clear old embeddings for this file before re-indexing
            # (prevents ghost vectors from outdated code)
            try:
                self.embedding_service.delete_by_file_path(path_str)
            except Exception:
                pass

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

            # Store mtime for fast incremental filtering
            try:
                mtime = file_path.stat().st_mtime
                self._file_hashes[f"{path_str}:mtime"] = str(mtime)
            except Exception:
                pass

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
        subgraph_filter: Optional[str] = None,
        use_hierarchy: bool = True,
    ) -> ContextWindow:
        """Build a context window for LLM from query.

        This is the main method for RAG (Retrieval Augmented Generation).
        It retrieves the most relevant code snippets and formats them for LLM consumption.

        For large codebases, supports hierarchical indexing:
        - Tier 1: Master index with subgraph overviews
        - Tier 2: Detailed subgraph symbols
        - Tier 3: Full code via semantic search

        Args:
            query: The user's query
            max_tokens: Maximum tokens for context
            include_related: Whether to include related symbols
            subgraph_filter: If set, return detailed info for this subgraph
            use_hierarchy: Whether to use hierarchical index for large codebases

        Returns:
            ContextWindow with snippets and metadata
        """
        # --- Tier 2: Subgraph detail mode ---
        if subgraph_filter and self._hierarchical_builder is not None:
            detail_text = self.get_subgraph_text(subgraph_filter, max_symbols=100)
            snippet = CodeSnippet(
                id=f"subgraph:{subgraph_filter}",
                content=detail_text,
                file_path=f"subgraph:{subgraph_filter}",
                start_line=1,
                end_line=detail_text.count("\n"),
                language="markdown",
                symbol_name=subgraph_filter,
                symbol_type="subgraph",
                relevance_score=1.0,
            )
            return ContextWindow(
                snippets=[snippet],
                total_tokens=len(detail_text) // 4,
                total_chars=len(detail_text),
                source_files=[],
            )

        # --- Tier 1: Master index for large codebases ---
        # Threshold: use hierarchical mode when > 100 files or > 500 symbols
        is_large_codebase = self._stats.total_files > 100 or self._stats.total_symbols > 500

        if use_hierarchy and is_large_codebase and self._hierarchical_builder is not None:
            master_text = self.get_master_index_text(max_subgraphs=30)

            # Also do a lightweight semantic search to find relevant subgraphs
            semantic_results = await self.search(
                SearchQuery(
                    text=query,
                    query_type="semantic",
                    max_results=3,
                )
            )

            # Try to match query to a subgraph name for extra relevance
            matched_subgraph = self._match_query_to_subgraph(query)
            extra_snippets: list[CodeSnippet] = []

            if matched_subgraph:
                subgraph_preview = self.get_subgraph_text(matched_subgraph, max_symbols=30)
                extra_snippets.append(
                    CodeSnippet(
                        id=f"subgraph_preview:{matched_subgraph}",
                        content=f"\n## Likely Relevant Subgraph: {matched_subgraph}\n\n{subgraph_preview[:2000]}",
                        file_path=f"subgraph:{matched_subgraph}",
                        start_line=1,
                        end_line=1,
                        language="markdown",
                        symbol_name=matched_subgraph,
                        symbol_type="subgraph_preview",
                        relevance_score=0.9,
                    )
                )

            # Combine master index + preview + top semantic results
            context_text = f"""# Hierarchical Codebase Index

The codebase is large ({self._stats.total_files} files, {self._stats.total_symbols} symbols).
Use the subgraph names below to drill down with `subgraph="<name>"` if you need details.

{master_text}
"""

            snippets: list[CodeSnippet] = [
                CodeSnippet(
                    id="master_index",
                    content=context_text,
                    file_path="master_index",
                    start_line=1,
                    end_line=context_text.count("\n"),
                    language="markdown",
                    symbol_name="master_index",
                    symbol_type="index",
                    relevance_score=1.0,
                )
            ]

            snippets.extend(extra_snippets)
            snippets.extend(semantic_results)

            return self._truncate_snippets_to_budget(snippets, max_tokens, query)

        # --- Fallback: traditional flat RAG ---
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

        return self._truncate_snippets_to_budget(unique_snippets, max_tokens, query)

    def _truncate_snippets_to_budget(
        self,
        snippets: list[CodeSnippet],
        max_tokens: int,
        query: str = "",
    ) -> ContextWindow:
        """Truncate snippets to fit within token budget.

        Also injects relevant project memory entries at the front of the
        context window so accumulated knowledge (bugs, decisions, QA) is
        visible to the LLM before code snippets.
        """
        # --- Inject project memory ---
        memory_snippets: list[CodeSnippet] = []
        if query:
            try:
                memory_entries = self._memory_kb.search(query, top_k=3)
                for entry in memory_entries:
                    memory_snippets.append(
                        CodeSnippet(
                            id=f"memory:{entry.id}",
                            content=self._format_memory_entry(entry),
                            file_path=f"memory:{entry.category}",
                            start_line=1,
                            end_line=1,
                            language="markdown",
                            symbol_name=entry.category,
                            symbol_type="memory",
                            relevance_score=0.95,
                        )
                    )
            except Exception:
                pass  # Memory is best-effort

        all_snippets = memory_snippets + snippets

        # --- Truncate to token budget ---
        selected: list[CodeSnippet] = []
        total_chars = 0
        max_chars = max_tokens * 4  # Rough estimate: 4 chars per token

        for snippet in all_snippets:
            snippet_chars = len(snippet.content)
            remaining = max_chars - total_chars
            if remaining <= 0:
                break
            if snippet_chars > remaining:
                # Truncate this snippet rather than skipping it entirely
                truncated_content = snippet.content[:remaining]
                selected.append(
                    CodeSnippet(
                        id=snippet.id,
                        content=truncated_content,
                        file_path=snippet.file_path,
                        start_line=snippet.start_line,
                        end_line=snippet.end_line,
                        language=snippet.language,
                        symbol_name=snippet.symbol_name,
                        symbol_type=snippet.symbol_type,
                        relevance_score=snippet.relevance_score,
                    )
                )
                total_chars += len(truncated_content)
                break
            selected.append(snippet)
            total_chars += snippet_chars

        return ContextWindow(
            snippets=selected,
            total_tokens=total_chars // 4,
            total_chars=total_chars,
            source_files=list(set(s.file_path for s in selected)),
        )

    def _format_memory_entry(self, entry: MemoryEntry) -> str:
        """Format a memory entry as markdown text for LLM consumption."""
        lines: list[str] = []
        lines.append(f"## Project Memory: {entry.category.upper()}")
        lines.append("")
        lines.append(entry.content)
        if entry.tags:
            lines.append("")
            lines.append(f"*Tags: {', '.join(entry.tags)}*")
        if entry.metadata:
            for key, value in entry.metadata.items():
                if value:
                    lines.append(f"- **{key}**: {value}")
        lines.append("")
        return "\n".join(lines)

    def _match_query_to_subgraph(self, query: str) -> Optional[str]:
        """Try to match a query string to a subgraph name/id."""
        if self._hierarchical_builder is None:
            return None
        master = self._hierarchical_builder.get_master_index()
        if master is None:
            return None

        query_lower = query.lower()
        # Exact match
        for sg in master.subgraphs:
            if sg.name.lower() == query_lower or sg.id.lower() == query_lower:
                return sg.id
        # Substring match
        for sg in master.subgraphs:
            if sg.name.lower() in query_lower or query_lower in sg.name.lower():
                return sg.id
        # Path match
        for sg in master.subgraphs:
            if query_lower in sg.path.lower():
                return sg.id
        return None

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
        # Also remove embeddings for this file
        try:
            self.embedding_service.delete_by_file_path(file_path)
        except Exception:
            pass

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
