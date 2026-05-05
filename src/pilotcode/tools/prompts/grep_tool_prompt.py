"""Grep tool prompts."""

# =============================================================================


def get_simple_prompt() -> str:
    """Get basic Grep tool description."""
    return """## Grep Tool

Searches for text patterns in files across the codebase.

**Parameters:**
- pattern: Regular expression pattern to search for
- path: File path or glob pattern to search in
- ignore_case: Case insensitive (default: false)

**Example:**
- `Grep(pattern="def hello", path="*.py")`
- `Grep(pattern="TODO", ignore_case=true)`"""


def get_best_practices() -> str:
    """Get best practices."""
    return """## Best practices

**Combine with FileRead:**
1. Use Grep to find relevant files
2. Use FileRead to examine the matches
3. Then provide analysis

**CodeSearch vs Grep:**
- For large codebases: use CodeSearch first (more intelligent)
- Grep is good for simple regex patterns"""


def get_prompt() -> str:
    """Get complete prompt."""
    return "\n\n".join([get_simple_prompt(), get_best_practices()])


TOOL_NAME = "Grep"
