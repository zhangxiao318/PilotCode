"""Shared constants and utilities for the orchestration package.

Extracted to eliminate duplication across orchestrator, adapter, and verifier modules.
"""

from __future__ import annotations

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
