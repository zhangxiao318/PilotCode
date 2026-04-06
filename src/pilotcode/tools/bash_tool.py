"""Bash tool for executing shell commands."""

import asyncio
import re
import shlex
import os
import sys
from typing import Any
from dataclasses import dataclass
from pydantic import BaseModel, Field

from .base import Tool, ToolResult, ToolUseContext, build_tool
from .registry import register_tool


def is_windows() -> bool:
    """Check if running on Windows."""
    return sys.platform == "win32"


def translate_command_for_windows(command: str) -> str:
    """Translate common Unix commands to Windows equivalents."""
    if not is_windows():
        return command

    # Handle simple command translations
    cmd_stripped = command.strip()

    # pwd -> cd (Windows equivalent to print working directory)
    if cmd_stripped == "pwd":
        return "cd"

    # cat FILE1 [FILE2...] -> type FILE1 [FILE2...] (Windows equivalent)
    # Handles: cat file.txt, cat file1.txt file2.txt, cat file1 file2 > output.txt
    cat_match = re.match(r"^cat\s+(.+)$", cmd_stripped)
    if cat_match:
        args = cat_match.group(1)
        # Replace cat with type, keep the rest of arguments (files, redirections)
        return f"type {args}"

    # seq N -> PowerShell equivalent
    if re.match(r"^seq\s+\d+$", cmd_stripped):
        n = cmd_stripped.split()[1]
        return f"powershell -Command " + f'"for ($i = 1; $i -le {n}; $i++) {{ Write-Output $i }}"'

    # seq START END -> PowerShell equivalent
    if re.match(r"^seq\s+\d+\s+\d+$", cmd_stripped):
        parts = cmd_stripped.split()
        start, end = parts[1], parts[2]
        return (
            f"powershell -Command "
            + f'"for ($i = {start}; $i -le {end}; $i++) {{ Write-Output $i }}"'
        )

    # sleep N -> PowerShell equivalent
    if re.match(r"^sleep\s+\d+$", cmd_stripped):
        n = cmd_stripped.split()[1]
        return f"powershell -Command Start-Sleep -Seconds {n}"

    # Handle pipe commands with tr (e.g., "echo 'hello world' | tr ' ' '-'")
    if "|" in cmd_stripped and "tr" in cmd_stripped:
        # Try to convert simple tr commands to PowerShell
        # echo 'hello world' | tr ' ' '-' -> echo 'hello world' | ForEach-Object { $_ -replace ' ', '-' }
        match = re.match(
            r"echo\s+['\"](.+)['\"]\s*\|\s*tr\s+['\"](.)['\"]\s+['\"](.)['\"]", cmd_stripped
        )
        if match:
            text, old_char, new_char = match.groups()
            return f"powershell -Command \"echo '{text}' | ForEach-Object {{ $_ -replace '{old_char}', '{new_char}' }}\""

    return command


# Dangerous command patterns (inspired by NanoCoder)
# These patterns could wreck the filesystem or leak secrets
DANGEROUS_PATTERNS = [
    # rm -rf on root directory specifically (not /tmp, /home, etc.)
    (r"\brm\s+(-\w*)?-r\w*\s+/$", "recursive delete on root directory"),
    (r"\brm\s+(-\w*)?-r\w*\s+~\s*$", "recursive delete on home directory"),
    (r"\brm\s+(-\w*)?-r\w*\s+\$HOME", "recursive delete on home directory"),
    # rm -rf / at the start or standalone
    (r"\brm\s+(-\w*)?-rf\s+/(?:\s|$)", "force recursive delete on system directory"),
    # Filesystem formatting
    (r"\bmkfs\b", "format filesystem"),
    # Raw disk writes
    (r"\bdd\s+.*of=/dev/", "raw disk write"),
    (r">\s*/dev/sd[a-z]", "overwrite block device"),
    (r">\s*/dev/nvme", "overwrite block device"),
    (r">\s*/dev/hd[a-z]", "overwrite block device"),
    # Dangerous chmod (only root directory)
    (r"\bchmod\s+(-R\s+)?777\s+/$", "chmod 777 on root"),
    (r"\bchmod\s+(-R\s+)?777\s*/\s*$", "chmod 777 on root"),
    # Fork bomb
    (r":\(\)\s*\{.*:\|:.*\}", "fork bomb"),
    # Piping downloads to bash
    (r"\bcurl\b.*\|\s*(sudo\s+)?bash", "pipe curl to bash"),
    (r"\bwget\b.*\|\s*(sudo\s+)?bash", "pipe wget to bash"),
    # Home directory deletion variations
    (r"\brm\s+(-\w*)?-rf\s+~\s*$", "force recursive delete on home directory"),
    (r"\brm\s+(-\w*)?-rf\s+~/\s*$", "force recursive delete on home directory"),
    # System config overwrite
    (r">\s*/etc/(?:passwd|shadow|fstab|hosts)\s*$", "overwrite critical system file"),
    # Format device
    (r"\bformat\s+/dev/", "format device"),
    # Remove all files in root
    (r"\brm\s+(-\w*)?-rf\s+/\s*\*", "recursive delete all files in root"),
]


def check_dangerous_command(command: str) -> str | None:
    """Check if a command is dangerous.

    Args:
        command: The command to check

    Returns:
        Warning message if dangerous, None if safe
    """
    for pattern, reason in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return f"Dangerous command blocked: {reason}"
    return None


class BashProgress(BaseModel):
    """Progress for bash command execution."""

    stdout: str = ""
    stderr: str = ""


class BashInput(BaseModel):
    """Input for Bash tool."""

    command: str = Field(description="The bash command to execute")
    timeout: int = Field(default=600, description="Timeout in seconds")
    description: str | None = Field(
        default=None, description="Description of what the command does (for clarity)"
    )
    working_dir: str | None = Field(default=None, description="Working directory for the command")
    run_in_background: bool = Field(default=False, description="Run command in background")
    force: bool = Field(
        default=False,
        description="Force execution even if command appears dangerous (use with caution)",
    )


class BashOutput(BaseModel):
    """Output from Bash tool."""

    stdout: str
    stderr: str
    exit_code: int
    command: str


async def execute_bash(
    command: str, cwd: str | None = None, timeout: int = 600, env: dict[str, str] | None = None
) -> BashOutput:
    """Execute a bash command."""
    # Translate command for Windows compatibility
    command = translate_command_for_windows(command)

    # Get current environment
    process_env = os.environ.copy()
    if env:
        process_env.update(env)

    try:
        # Create subprocess
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=process_env,
        )

        # Wait for completion with timeout
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)

        return BashOutput(
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
            exit_code=process.returncode or 0,
            command=command,
        )
    except asyncio.TimeoutError:
        # Kill the process if timeout
        try:
            process.kill()
            await process.wait()
        except:
            pass
        return BashOutput(
            stdout="",
            stderr=f"Command timed out after {timeout} seconds",
            exit_code=-1,
            command=command,
        )
    except Exception as e:
        return BashOutput(stdout="", stderr=str(e), exit_code=-1, command=command)


async def bash_call(
    input_data: BashInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[BashOutput]:
    """Execute bash command."""
    # Check for dangerous commands (unless force flag is set)
    if not input_data.force:
        danger_warning = check_dangerous_command(input_data.command)
        if danger_warning:
            return ToolResult(
                data=BashOutput(
                    stdout="",
                    stderr=f"⚠️  Blocked: {danger_warning}\n\nCommand: {input_data.command}\n\nIf you are certain this is intentional, you can modify the command to be more specific, or use the force parameter (not recommended).",
                    exit_code=-1,
                    command=input_data.command,
                ),
                error=f"Dangerous command blocked: {danger_warning}",
            )

    # Check permissions
    permission = await can_use_tool("BashTool", input_data)
    if isinstance(permission, dict):
        if permission.get("behavior") == "deny":
            return ToolResult(
                data=BashOutput(
                    stdout="", stderr="Permission denied", exit_code=-1, command=input_data.command
                ),
                error="Permission denied",
            )
    elif hasattr(permission, "behavior") and permission.behavior == "deny":
        return ToolResult(
            data=BashOutput(
                stdout="", stderr="Permission denied", exit_code=-1, command=input_data.command
            ),
            error="Permission denied",
        )

    # Determine working directory
    cwd = input_data.working_dir
    if cwd is None and context.get_app_state:
        app_state = context.get_app_state()
        cwd = getattr(app_state, "cwd", os.getcwd())

    # Execute command
    result = await execute_bash(input_data.command, cwd=cwd, timeout=input_data.timeout)

    return ToolResult(data=result)


async def bash_description(input_data: BashInput, options: dict[str, Any]) -> str:
    """Get description for bash tool use."""
    return f"$ {input_data.command[:100]}"


def bash_user_facing_name(input_data: BashInput) -> str:
    """Get user facing name for bash tool."""
    return f"Bash({input_data.command[:50]})"


def is_read_only_command(command: str) -> bool:
    """Check if command is read-only (doesn't modify files)."""
    # List of read-only commands/patterns
    read_only_patterns = [
        "ls",
        "cat",
        "echo",
        "pwd",
        "whoami",
        "id",
        "uname",
        "date",
        "head",
        "tail",
        "less",
        "more",
        "grep",
        "find",
        "which",
        "ps",
        "top",
        "htop",
        "df",
        "du",
        "free",
        "uptime",
        "env",
        "git status",
        "git log",
        "git diff",
        "git show",
        "git branch",
        "python --version",
        "node --version",
        "npm --version",
        "curl -I",
        "curl --head",
        "wget --spider",
    ]

    cmd_lower = command.strip().lower()
    for pattern in read_only_patterns:
        if cmd_lower.startswith(pattern.lower()):
            return True
    return False


# Create the Bash tool
BashTool = build_tool(
    name="Bash",
    description=bash_description,
    input_schema=BashInput,
    output_schema=BashOutput,
    call=bash_call,
    aliases=["bash", "shell"],
    search_hint="Execute bash shell commands",
    max_result_size_chars=50000,
    is_read_only=lambda x: is_read_only_command(x.command) if x else False,
    is_concurrency_safe=lambda x: is_read_only_command(x.command) if x else False,
    user_facing_name=bash_user_facing_name,
)

# Register the tool
register_tool(BashTool)
