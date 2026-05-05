"""Glob tool prompts."""

# =============================================================================


def get_simple_prompt() -> str:
    """Get basic Glob tool description."""
    return """## Glob Tool

Finds files matching patterns in the filesystem.

**Parameters:**
- pattern: Glob pattern (e.g., "*.py", "src/**/*.ts", "**/test_*.py")

**Example:**
- `Glob(pattern="*.py")` - all Python files in current dir
- `Glob(pattern="src/**/*.js")` - all JS files in src and subdirs
- `Glob(pattern="**/*.py")` - all Python files recursively"""


def get_best_practices() -> str:
    """Get best practices."""
    return """## Best practices

**After finding files:**
- Use FileRead to read the content of each relevant file
- DO NOT just list files and say "these files exist"

**Large codebases:**
- Use CodeSearch for intelligent search first
- Use Glob for simple pattern matching

**Combine with other tools:**
- Example: "查看目录有哪些 Python 文件并读取 app.py"
  -> Glob(pattern="*.py") AND FileRead(path="app.py")"""


def get_prompt() -> str:
    """Get complete prompt."""
    return "\n\n".join([get_simple_prompt(), get_best_practices()])


TOOL_NAME = "Glob"
