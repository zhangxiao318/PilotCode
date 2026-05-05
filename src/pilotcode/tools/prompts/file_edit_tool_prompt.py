"""FileEdit tool prompts.

Reference: Claude Code src/tools/FileEditTool/prompt.ts
"""

# =============================================================================
# Core FileEdit Instructions
# =============================================================================


def get_simple_prompt() -> str:
    """Get basic FileEdit tool description."""
    return """## FileEdit Tool

Modifies existing files by replacing specific text strings.

**Key behaviors:**
- Replaces the first occurrence of `old_string` with `new_string`
- The file must already exist
- Use EXACT string matching including all spaces, tabs, and newlines

**Parameters:**
- path: The file path to edit
- old_string: The exact text to find and replace
- new_string: The replacement text

**Example:**
```
FileEdit(
    path="app.py",
    old_string="def hello():\n    print('Hello')",
    new_string="def hello():\n    print('Hello, World!')"
)
```"""


def get_failure_fallback() -> str:
    """Get failure fallback guidance."""
    return """## If FileEdit fails

**Common error: "String not found" or mismatch**

**Immediate actions:**
1. Re-read the file with FileRead to get the EXACT current text
2. Copy old_string precisely (including whitespace)
3. Retry FileEdit

**If it fails AGAIN:**
- For small files (< 40 lines): switch to FileWrite
- For larger files: use SmartEditPlanner tool"""


def get_best_practices() -> str:
    """Get best practices for file editing."""
    return """## Best practices

**EXACT MATCH:**
- old_string must match file content EXACTLY
- Double-check spaces, tabs, newlines
- If unsure, re-read the file

**Indentation:**
- Python is indentation-sensitive
- Maintain correct indentation level
- Be careful with mixed tabs/spaces

**After editing:**
- Run syntax check: `Bash(command="python -m py_compile ")`
- For Python files, verify no syntax errors

**Multi-file changes:**
- Use a checklist, edit one at a time
- Check each off before declaring completion
- Review with `Bash(command="git diff")` before finishing"""


# =============================================================================
# Complete prompt
# =============================================================================


def get_prompt() -> str:
    """Get complete FileEdit tool prompt."""
    return "\n\n".join(
        [
            get_simple_prompt(),
            get_failure_fallback(),
            get_best_practices(),
        ]
    )


TOOL_NAME = "FileEdit"
