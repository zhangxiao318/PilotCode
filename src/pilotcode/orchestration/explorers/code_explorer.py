"""Quick codebase exploration before mission planning."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

from ..project_memory import ProjectMemory

logger = logging.getLogger(__name__)


async def explore_codebase(
    user_request: str, project_memory: ProjectMemory, cwd: str | None = None
) -> dict[str, Any]:
    """Quickly explore the codebase to understand structure before planning.

    Enhanced with tree-sitter symbol indexing, semantic-like symbol search,
    lightweight call graph analysis, and architecture pattern detection.

    Args:
        user_request: The user's natural language request.
        project_memory: Shared project memory to record findings.
        cwd: Working directory to explore. Defaults to the current process directory.

    Returns:
        A dict with keys: files, conventions, architecture_notes, symbols,
        call_graph, patterns.
    """
    import glob as pyglob

    base_dir = cwd or os.getcwd()
    exploration: dict[str, Any] = {
        "files": [],
        "conventions": {},
        "architecture_notes": [],
        "symbols": [],
        "call_graph": {},
        "patterns": [],
    }

    # ------------------------------------------------------------------
    # Phase 1: Quick file scan
    # ------------------------------------------------------------------
    try:
        py_files = await asyncio.to_thread(
            pyglob.glob, os.path.join(base_dir, "**/*.py"), recursive=True
        )
        # Strip base_dir prefix for consistent relative paths
        exploration["files"] = [os.path.relpath(f, base_dir) for f in py_files[:50]]
    except Exception:
        logger.debug("Exploration glob failed", exc_info=True)

    # Try to find key files mentioned in request
    keywords = [w for w in user_request.lower().split() if len(w) > 3]
    key_files_found = []
    for keyword in keywords[:5]:
        for fpath in exploration["files"]:
            if keyword in fpath.lower() and fpath not in key_files_found:
                key_files_found.append(fpath)
                if len(key_files_found) >= 10:
                    break
        if len(key_files_found) >= 10:
            break

    # Read top-level files to understand project structure
    top_level_files = [
        "README.md",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "requirements.txt",
    ]
    for fname in top_level_files:
        fpath = os.path.join(base_dir, fname)
        try:
            exists = await asyncio.to_thread(os.path.exists, fpath)
            if not exists:
                continue
            content = await asyncio.to_thread(
                lambda p: open(p, "r", encoding="utf-8").read(), fpath
            )
            project_memory.record_file_read(
                fname, content, summary=content[:200].replace("\n", " ")
            )
            if fname == "pyproject.toml":
                if "fastapi" in content.lower():
                    project_memory.record_convention("framework", "FastAPI")
                elif "django" in content.lower():
                    project_memory.record_convention("framework", "Django")
                elif "flask" in content.lower():
                    project_memory.record_convention("framework", "Flask")
        except Exception:
            logger.debug("Exploration file read failed for %s", fname, exc_info=True)

    # ------------------------------------------------------------------
    # Phase 2: Tree-sitter symbol indexing + semantic-like search
    # ------------------------------------------------------------------
    try:
        from ...services.code_index import get_code_indexer

        indexer = get_code_indexer()
        # Index up to 20 most relevant files (key files + first files)
        files_to_index = key_files_found + exploration["files"]
        files_to_index = files_to_index[:20]
        for rel_path in files_to_index:
            abs_path = os.path.join(base_dir, rel_path)
            await indexer.index_file(abs_path)

        # Search for symbols matching user request keywords
        matched_symbols = []
        for keyword in keywords[:5]:
            results = indexer.search_symbols(keyword)
            for sym in results[:5]:
                matched_symbols.append(
                    {
                        "name": sym.name,
                        "type": sym.symbol_type,
                        "file": os.path.relpath(sym.file_path, base_dir),
                        "line": sym.line_number,
                        "signature": sym.signature,
                    }
                )
        # Deduplicate
        seen = set()
        exploration["symbols"] = []
        for s in matched_symbols:
            key = (s["name"], s["file"], s["line"])
            if key not in seen:
                seen.add(key)
                exploration["symbols"].append(s)

        # ------------------------------------------------------------------
        # Phase 3: Lightweight call graph (reference search)
        # ------------------------------------------------------------------
        call_graph: dict[str, list[dict[str, Any]]] = {}
        for sym in exploration["symbols"][:10]:
            if sym["type"] not in ("function", "method"):
                continue
            refs = []
            # Grep for calls to this symbol in indexed files
            pattern = rf"\b{re.escape(sym['name'])}\s*\("
            for file_path in files_to_index:
                abs_path = os.path.join(base_dir, file_path)
                try:
                    text = await asyncio.to_thread(
                        lambda p: open(p, "r", encoding="utf-8", errors="ignore").read(),
                        abs_path,
                    )
                    for i, line in enumerate(text.splitlines(), 1):
                        if sym["name"] in line and "def " not in line:
                            import re as _re

                            if _re.search(pattern, line):
                                refs.append(
                                    {
                                        "file": file_path,
                                        "line": i,
                                        "context": line.strip()[:80],
                                    }
                                )
                                if len(refs) >= 3:
                                    break
                except Exception:
                    pass
            if refs:
                call_graph[sym["name"]] = refs
        exploration["call_graph"] = call_graph

        # ------------------------------------------------------------------
        # Phase 4: Architecture pattern extraction
        # ------------------------------------------------------------------
        patterns = _detect_patterns(base_dir, exploration["files"])
        exploration["patterns"] = patterns
        for p in patterns:
            project_memory.record_convention("architecture", p["name"])
            exploration["architecture_notes"].append(p["description"])

    except Exception:
        logger.debug("Enhanced exploration failed", exc_info=True)

    exploration["key_files"] = key_files_found
    return exploration


def _detect_patterns(base_dir: str, files: list[str]) -> list[dict[str, Any]]:
    """Detect common architecture patterns from file structure."""
    import os

    patterns = []
    dirs = set()
    for f in files:
        parts = f.split(os.sep)
        if len(parts) > 1:
            dirs.add(parts[0])

    # MVC pattern
    has_models = any("model" in d.lower() for d in dirs)
    has_views = any("view" in d.lower() for d in dirs)
    has_controllers = any(d.lower() in ("controller", "controllers", "ctrl") for d in dirs)
    if has_models and has_views and has_controllers:
        patterns.append({"name": "MVC", "description": "Model-View-Controller pattern detected"})
    elif has_models and has_views:
        patterns.append({"name": "MV-like", "description": "Model-View structure detected"})

    # Layered architecture
    has_domain = any("domain" in d.lower() for d in dirs)
    has_service = any("service" in d.lower() for d in dirs)
    has_repo = any(d.lower() in ("repository", "repositories", "repo", "repos") for d in dirs)
    if has_domain and has_service and has_repo:
        patterns.append(
            {"name": "Layered", "description": "Domain-Service-Repository layered architecture"}
        )

    # Plugin architecture
    has_plugins = any("plugin" in d.lower() for d in dirs)
    if has_plugins:
        patterns.append({"name": "Plugin", "description": "Plugin/extension architecture detected"})

    # Microservices / service-oriented
    service_dirs = [d for d in dirs if d.lower() in ("services", "svc", "microservices")]
    if service_dirs and len(dirs) > 3:
        patterns.append({"name": "Services", "description": "Multi-service directory structure"})

    # Tests co-located or separated
    has_test_dir = any(d.lower() in ("tests", "test") for d in dirs)
    has_test_files = any("test_" in f or "_test.py" in f for f in files)
    if has_test_dir:
        patterns.append({"name": "SeparatedTests", "description": "Tests in dedicated directory"})
    elif has_test_files:
        patterns.append(
            {"name": "CoLocatedTests", "description": "Tests co-located with source files"}
        )

    return patterns
