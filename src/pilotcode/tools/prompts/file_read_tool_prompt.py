"""FileRead tool prompts.

Reference: Claude Code src/tools/FileReadTool/prompt.ts
"""

# =============================================================================
# Core FileRead Instructions
# =============================================================================


def get_simple_prompt() -> str:
    """Get basic FileRead tool description."""
    return """## FileRead Tool

Reads the contents of a file and returns it as text.

**Key behaviors:**
- Returns up to 2000 lines from the start by default
- Use offset to read later sections
- Works on ANY file the user mentions including external reference files
- Can read binary files (returns as file attachments)

**Usage:**
- `FileRead(path="path/to/file.py")`
- `FileRead(path="path/to/file.py", offset=100)` - start from line 100
- `FileRead(path="path/to/file.py", limit=50)` - read only 50 lines"""


def get_best_practices() -> str:
    """Get best practices for file reading."""
    return """## Best practices

**ALWAYS use FileRead before analyzing or modifying files:**
1. Use Glob/Grep to find relevant files first
2. FileRead each relevant file
3. Then provide analysis

**Large files:**
- Use offset/limit to read in chunks
- Check file size first with Bash: `ls -la`

**Multiple files:**
- Use FileRead multiple times in parallel when files are independent
- Example: "Read app.py and config.py" -> two FileRead calls at once"""


# =============================================================================
# Complete prompt
# =============================================================================


def get_prompt() -> str:
    """Get complete FileRead tool prompt."""
    return "\n\n".join(
        [
            get_simple_prompt(),
            get_best_practices(),
        ]
    )


TOOL_NAME = "FileRead"
