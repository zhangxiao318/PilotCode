"""FileWrite tool prompts.

Reference: Claude Code src/tools/FileWriteTool/prompt.ts
"""

# =============================================================================
# Core FileWrite Instructions
# =============================================================================


def get_simple_prompt() -> str:
    """Get basic FileWrite tool description."""
    return """## FileWrite Tool

Creates a new file with the specified content.

**Key behaviors:**
- Creates the file if it doesn't exist
- Overwrites the file if it already exists
- Use EXACT file paths - NEVER add '_new', '_backup', '_fixed' suffixes

**Parameters:**
- path: The file path to write to
- content: The content to write (as string)

**Example:**
```
FileWrite(path="new_file.py", content='''
def hello():
    print("Hello, World!")
''')
```"""


def get_best_practices() -> str:
    """Get best practices for file writing."""
    return """## Best practices

**When to use FileWrite:**
- Creating new files
- Overwriting existing files completely
- Writing generated code, scripts, configs

**When NOT to use FileWrite:**
- For small edits to existing files -> use FileEdit instead
- For code modifications -> use FileEdit for precise changes

**File path rules:**
- Always use EXACT original path from the user request
- NEVER create files with '_new', '_backup', '_v2', etc. suffixes
- Write directly to the target file path

**Directory creation:**
- If the directory doesn't exist, create it first with Bash: `Bash(command="mkdir -p path/to/dir")`"""


# =============================================================================
# Complete prompt
# =============================================================================


def get_prompt() -> str:
    """Get complete FileWrite tool prompt."""
    return "\n\n".join(
        [
            get_simple_prompt(),
            get_best_practices(),
        ]
    )


TOOL_NAME = "FileWrite"
