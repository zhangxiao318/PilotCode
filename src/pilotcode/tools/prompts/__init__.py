"""Tool prompts module.

This module exports tool-specific prompts from individual prompt.py files.
Reference: Claude Code src/tools/*/prompt.ts pattern
"""

from pilotcode.tools.prompts.bash_tool_prompt import get_prompt as get_bash_prompt
from pilotcode.tools.prompts.file_read_tool_prompt import get_prompt as get_fileread_prompt
from pilotcode.tools.prompts.file_write_tool_prompt import get_prompt as get_filewrite_prompt
from pilotcode.tools.prompts.file_edit_tool_prompt import get_prompt as get_fileedit_prompt
from pilotcode.tools.prompts.glob_tool_prompt import get_prompt as get_glob_prompt
from pilotcode.tools.prompts.grep_tool_prompt import get_prompt as get_grep_prompt
from pilotcode.tools.prompts.code_search_tool_prompt import get_prompt as get_codesearch_prompt

_TOOL_PROMPTS = {
    "Bash": get_bash_prompt,
    "FileRead": get_fileread_prompt,
    "FileWrite": get_filewrite_prompt,
    "FileEdit": get_fileedit_prompt,
    "Glob": get_glob_prompt,
    "Grep": get_grep_prompt,
    "CodeSearch": get_codesearch_prompt,
}


def get_tool_prompt(tool_name: str):
    """Get tool-specific prompt by name.

    Args:
        tool_name: Name of the tool

    Returns:
        Tool-specific prompt function
    """
    return _TOOL_PROMPTS.get(tool_name)


def get_all_tool_prompts() -> dict[str, str]:
    """Get all tool prompts as dict."""
    return {name: getter() for name, getter in _TOOL_PROMPTS.items()}
