"""Bash tool prompts.

Reference: Claude Code src/tools/BashTool/prompt.ts
"""

# =============================================================================
# Core Bash Instructions
# =============================================================================


def get_simple_prompt() -> str:
    """Get basic Bash tool description."""
    return """## Bash Tool

Executes a given bash command and returns its output.

**Key behaviors:**
- The working directory persists between commands, but shell state does not
- Each call runs in a separate subprocess
- Default timeout: 60 seconds (configurable up to 10 minutes)

**Usage guidelines:**
- Use absolute paths, avoid `cd`
- Quote paths with spaces: `cd "path with spaces/file.txt"`
- Prefer dedicated tools (FileRead, FileEdit) over `cat`/`sed`"""


def get_background_usage_note() -> str:
    """Get background execution guidance."""
    return """You can use the `run_in_background` parameter to run the command in the background. Only use this if you don't need the result immediately and are OK being notified when the command completes later."""


def get_multiple_commands_guidance() -> str:
    """Get guidance for multiple commands."""
    return """## Running multiple commands

- If commands are independent, run them in parallel with multiple tool calls
- If commands depend on each other, chain with '&&'
- Use ';' only when you don't care if earlier commands fail
- DO NOT use newlines to separate commands (newlines are OK in quoted strings)"""


def get_git_guidance() -> str:
    """Get git operations guidance."""
    return """## Git operations

**Safety Protocol:**
- NEVER run destructive commands (push --force, reset --hard, checkout ., clean -f, branch -D) unless explicitly asked
- NEVER skip hooks (--no-verify, --no-gpg-sign) unless explicitly asked
- Always create NEW commits rather than amending
- NEVER commit unless explicitly asked

**Process:**
1. Run git status (shows untracked files)
2. Run git diff (shows staged + unstaged changes)
3. Run git log (recent commit messages for style)
4. Analyze staged changes, draft commit message
5. Add files, create commit, verify with git status

**Dangerous commands to confirm first:**
- Destructive: deleting files/branches, dropping tables
- Hard-to-reverse: force-push, git reset --hard
- Visible to others: push, create PR"""


# =============================================================================
# Complete prompt
# =============================================================================


def get_prompt() -> str:
    """Get complete Bash tool prompt."""
    return "\n\n".join(
        [
            get_simple_prompt(),
            get_background_usage_note(),
            get_multiple_commands_guidance(),
            get_git_guidance(),
        ]
    )


TOOL_NAME = "Bash"
