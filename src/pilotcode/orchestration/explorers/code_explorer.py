"""Quick codebase exploration before mission planning."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from ..project_memory import ProjectMemory

logger = logging.getLogger(__name__)


async def explore_codebase(user_request: str, project_memory: ProjectMemory) -> dict[str, Any]:
    """Quickly explore the codebase to understand structure before planning.

    Returns a dict with keys: files, conventions, architecture_notes.
    """
    import glob as pyglob

    exploration: dict[str, Any] = {"files": [], "conventions": {}, "architecture_notes": []}

    # Quick scan of Python files (offload sync I/O to thread)
    try:
        py_files = await asyncio.to_thread(pyglob.glob, "**/*.py", recursive=True)
        exploration["files"] = py_files[:50]
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
        fpath = os.path.join(os.getcwd(), fname)
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

    exploration["key_files"] = key_files_found
    return exploration
