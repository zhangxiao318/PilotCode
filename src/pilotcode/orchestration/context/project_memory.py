"""Layer 3: Project Memory (compatibility layer).

This module re-exports ProjectMemory from the main orchestration module.
The original implementation has been merged into project_memory.py.

For new code, import directly from pilotcode.orchestration.project_memory.
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path

from ..project_memory import ProjectMemory


# Maintain backward compatibility for get_project_memory
def get_project_memory(project_path: str | None = None) -> ProjectMemory:
    """Get project memory for a project path."""
    if project_path is None:
        project_path = os.getcwd()

    # Load from the canonical location if it exists
    memory_path = Path(project_path) / ".pilotcode" / "project_memory.json"
    if memory_path.exists():
        try:
            return ProjectMemory.load(str(memory_path))
        except Exception:
            import logging

            logging.getLogger(__name__).debug(
                "Project memory load failed for %s", project_path, exc_info=True
            )

    return ProjectMemory(project_path=project_path)


__all__ = ["ProjectMemory", "get_project_memory"]
