"""Language-specific compilation and testing guidance.

Provides the LLM with precise commands to compile/test code in each language.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Language detection by file extension
_LANG_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".rs": "rust",
    ".go": "go",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".sh": "shell",
    ".rs": "rust",
    ".kt": "kotlin",
    ".swift": "swift",
    ".rb": "ruby",
    ".php": "php",
}

# Compilation commands per language (fallback if no build system found)
_COMPILE_COMMANDS: dict[str, list[str]] = {
    "c": ["gcc", "-Wall", "-Wextra", "-fsyntax-only"],
    "cpp": ["g++", "-Wall", "-Wextra", "-fsyntax-only", "-std=c++17"],
    "rust": ["rustc", "--edition", "2021", "--emit=metadata"],
    "go": ["go", "vet"],
    "javascript": ["node", "--check"],
    "typescript": ["tsc", "--noEmit", "--strict"],
    "java": ["javac"],
    "python": [None],  # syntax check via compile()
}

# Test commands per language (can be overridden by build system detection)
_TEST_COMMANDS: dict[str, list[str]] = {
    "python": ["python -m pytest", "python -m pytest -xvs", "python -m unittest discover"],
    "c": ["make test", "make check"],
    "cpp": ["make test", "make check", "cmake --build . && ctest"],
    "rust": ["cargo test"],
    "go": ["go test ./..."],
    "javascript": ["npm test", "npx jest"],
    "typescript": ["npm test", "npx jest"],
    "java": ["mvn test", "gradle test"],
}


_VERIFY_HINTS: dict[str, str] = {
    "python": (
        "After editing Python files, run syntax check: "
        '`Bash(command="python -m py_compile <filepath>")`\n'
        'Then run tests: `Bash(command="python -m pytest -xvs")`'
    ),
    "c": (
        "After editing C files, compile-check with:\n"
        '`Bash(command="gcc -Wall -Wextra -fsyntax-only <filepath>")`\n'
        'Then build: `Bash(command="make")` or appropriate build command.'
    ),
    "cpp": (
        "After editing C++ files, compile-check with:\n"
        '`Bash(command="g++ -Wall -Wextra -fsyntax-only -std=c++17 <filepath>")`\n'
        'Then build: `Bash(command="make")` or `Bash(command="g++ -std=c++17 -o output <filepath>")`'
    ),
    "rust": (
        "After editing Rust files, compile-check with:\n"
        '`Bash(command="rustc --edition 2021 --emit=metadata <filepath>")`\n'
        'Then test: `Bash(command="cargo test")`'
    ),
    "go": (
        "After editing Go files, check with:\n"
        '`Bash(command="go vet <filepath>")`\n'
        'Then test: `Bash(command="go test ./...")`'
    ),
    "javascript": (
        "After editing JS files, syntax-check with:\n"
        '`Bash(command="node --check <filepath>")`\n'
        'Then test: `Bash(command="npm test")` or `Bash(command="npx jest")`'
    ),
    "typescript": (
        "After editing TypeScript files, compile-check with:\n"
        '`Bash(command="tsc --noEmit --strict")`\n'
        'Then test: `Bash(command="npm test")` or `Bash(command="npx jest")`'
    ),
    "java": (
        "After editing Java files, compile-check with:\n"
        '`Bash(command="javac <filepath>")`\n'
        'Then test: `Bash(command="mvn test")` or `Bash(command="gradle test")`'
    ),
}


def detect_languages_from_files(file_paths: list[str]) -> list[str]:
    """Detect programming languages from file paths.

    Args:
        file_paths: List of file paths.

    Returns:
        Sorted unique language names.
    """
    langs = set()
    for fp in file_paths:
        ext = Path(fp).suffix.lower()
        lang = _LANG_BY_EXT.get(ext)
        if lang:
            langs.add(lang)
    return sorted(langs)


def detect_languages_from_text(text: str) -> list[str]:
    """Detect programming languages from text (task objective, user request).

    Args:
        text: Text to scan for language mentions.

    Returns:
        Sorted unique language names.
    """
    lang_keywords = {
        "python": ["python", ".py", "pytest"],
        "c": [".c ", ".c\\", "c code", "c file", "c program"],
        "cpp": [".cpp", ".cc", ".cxx", ".hpp", "c++", "cpp"],
        "rust": [".rs", "rust", "cargo"],
        "go": [".go", "golang", "go lang"],
        "javascript": [".js", "javascript", "node.js", "nodejs"],
        "typescript": [".ts", "typescript"],
        "java": [".java", "java class"],
    }
    text_lower = text.lower()
    detected = set()
    for lang, keywords in lang_keywords.items():
        if any(kw in text_lower for kw in keywords):
            detected.add(lang)
    return sorted(detected)


def get_compile_hint(file_path: str) -> str | None:
    """Get the compile command hint for a specific file.

    Args:
        file_path: Path to the file.

    Returns:
        Compile hint string, or None if no hint for this file type.
    """
    ext = Path(file_path).suffix.lower()
    lang = _LANG_BY_EXT.get(ext)
    if lang and lang in _VERIFY_HINTS:
        return _VERIFY_HINTS[lang]
    return None


def get_compile_hints_for_files(file_paths: list[str]) -> str:
    """Get compile hints for a list of files.

    Args:
        file_paths: List of file paths.

    Returns:
        Combined compile hints string.
    """
    langs = detect_languages_from_files(file_paths)
    hints = []
    for lang in langs:
        hint = _VERIFY_HINTS.get(lang)
        if hint:
            hints.append(hint)

    if hints:
        return "\n\n## Verify your changes\n\n" + "\n\n".join(hints)
    return ""


def get_test_command(lang: str) -> str | None:
    """Get the recommended test command for a language.

    Args:
        lang: Language name.

    Returns:
        Test command string, or None.
    """
    cmds = _TEST_COMMANDS.get(lang, [])
    if not cmds:
        return None

    # Try to find an available command
    import shutil

    for cmd_template in cmds:
        tool = cmd_template.split()[0]
        if shutil.which(tool):
            return cmd_template
    return cmds[0] if cmds else None


def build_verification_section(file_paths: list[str], objective: str) -> str:
    """Build a verification section to inject into worker prompts.

    Args:
        file_paths: Files the task will modify.
        objective: Task objective text.

    Returns:
        Verification guidance string, or empty string.
    """
    from_files = detect_languages_from_files(file_paths)
    from_text = detect_languages_from_text(objective)
    langs = sorted(set(from_files + from_text))

    if not langs:
        return ""

    hints = []
    for lang in langs:
        hint = _VERIFY_HINTS.get(lang)
        if hint:
            hints.append(f"- **{lang.capitalize()}**: {hint.split(chr(10))[0]}")

    if hints:
        return "## Language-Specific Verification\n" + "\n".join(hints)

    return ""
