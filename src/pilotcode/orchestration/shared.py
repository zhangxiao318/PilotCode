"""Shared constants and utilities for the orchestration package.

Extracted to eliminate duplication across orchestrator, adapter, and verifier modules.
"""

from __future__ import annotations

from .task_spec import ComplexityLevel, TaskSpec

# File extensions recognized as source code files by the orchestration system.
# Used by verifiers to determine when to run compile checks, test runners, etc.
CODE_FILE_EXTENSIONS: tuple[str, ...] = (
    ".py",
    ".c",
    ".cpp",
    ".cc",
    ".cxx",
    ".h",
    ".hpp",
    ".rs",
    ".go",
    ".js",
    ".ts",
    ".java",
)


def is_code_file(path: str) -> bool:
    """Check if a file path has a recognized code extension."""
    return path.endswith(CODE_FILE_EXTENSIONS)


# ---- Worker type selection (single source of truth for #4) ----


def select_worker_type(task: TaskSpec) -> str:
    """Map task complexity to a worker type.

    This is the authoritative mapping — all callers (Orchestrator,
    ContextStrategy, etc.) should use this function rather than
    duplicating the ComplexityLevel → worker_type logic.
    """
    complexity = task.estimated_complexity
    if complexity == ComplexityLevel.VERY_SIMPLE:
        return "simple"
    elif complexity in (ComplexityLevel.SIMPLE, ComplexityLevel.MODERATE):
        return "standard"
    else:
        return "complex"
