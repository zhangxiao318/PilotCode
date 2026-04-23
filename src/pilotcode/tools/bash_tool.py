"""Bash tool for executing shell commands."""

import asyncio
import re
import os
import sys
from typing import Any
from dataclasses import replace
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
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

    # date -> PowerShell Get-Date (Windows date command waits for input)
    if cmd_stripped == "date":
        return "powershell -Command Get-Date -Format 'ddd MMM dd HH:mm:ss yyyy'"

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
        return "powershell -Command " + f'"for ($i = 1; $i -le {n}; $i++) {{ Write-Output $i }}"'

    # seq START END -> PowerShell equivalent
    if re.match(r"^seq\s+\d+\s+\d+$", cmd_stripped):
        parts = cmd_stripped.split()
        start, end = parts[1], parts[2]
        return (
            "powershell -Command "
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
    # Use negative lookahead to exclude /tmp, /home, etc. - only match root /
    (r"\brm\s+(-[a-zA-Z]*)?-r\w*\s+/(?![a-zA-Z])", "recursive delete on root directory"),
    (r"\brm\s+(-[a-zA-Z]*)?-r\w*\s+~/", "recursive delete on home directory"),
    (r"\brm\s+(-[a-zA-Z]*)?-r\w*\s+~(?:\s|#|\||;|$)", "recursive delete on home directory"),
    (r"\brm\s+(-[a-zA-Z]*)?-r\w*\s+\$HOME", "recursive delete on home directory"),
    # rm -rf / with various suffixes (must be followed by space, comment, pipe, semicolon, or end)
    (r"\brm\s+(-[a-zA-Z]*)?-rf\s+/(?:\s|#|\||;|$)", "force recursive delete on system directory"),
    (r"\brm\s+(-[a-zA-Z]*)?-rf\s+/\*", "recursive delete all files in root"),
    # Handle -- argument separator: rm -rf -- / (common bypass technique)
    (r"\brm\s+(-[a-zA-Z\s]*)--\s+/(?![a-zA-Z])", "recursive delete on root directory"),
    # Handle case where arguments after -- include root: rm -r -- -rf /
    (r"\brm\s+(-[a-zA-Z\s]*)--\s+\S+\s+/(?![a-zA-Z])", "recursive delete on root directory"),
    # Filesystem formatting
    (r"\bmkfs\b", "format filesystem"),
    # Raw disk writes
    (r"\bdd\s+.*of=/dev/", "raw disk write"),
    (r">\s*/dev/sd[a-z]", "overwrite block device"),
    (r">\s*/dev/nvme", "overwrite block device"),
    (r">\s*/dev/hd[a-z]", "overwrite block device"),
    (r">\s*/dev/null\s+of=/dev/", "overwrite block device via /dev/null"),
    # Dangerous chmod - only match root directory, not subdirectories like /tmp
    (r"\bchmod\s+(-R\s+)?777\s+/(?![a-zA-Z0-9])", "chmod 777 on root"),
    (r"\bchmod\s+(-R\s+)?777\s*/(?:\s|#|\||;|$)", "chmod 777 on root"),
    # Fork bomb
    (r":\(\)\s*\{.*:\|:.*\}", "fork bomb"),
    (r":\s*\(\)\s*\{.*:\s*\|\s*:", "fork bomb"),
    # Piping downloads to interpreters (variations)
    (r"\bcurl\b.*\|\s*(sudo\s+)?(bash|sh|zsh|python|perl|ruby)", "pipe download to interpreter"),
    (r"\bwget\b.*\|\s*(sudo\s+)?(bash|sh|zsh|python|perl|ruby)", "pipe download to interpreter"),
    (r"\bcurl\b.*-\s*(sudo\s+)?(bash|sh|zsh|python)", "pipe curl to interpreter via -"),
    # Home directory deletion variations
    (r"\brm\s+(-[a-zA-Z]*)?-rf\s+~/", "force recursive delete on home directory"),
    (r"\brm\s+(-[a-zA-Z]*)?-rf\s+~\b", "force recursive delete on home directory"),
    # System config overwrite
    (
        r">\s*/etc/(?:passwd|shadow|fstab|hosts|sudoers|ssh/sshd_config)\b",
        "overwrite critical system file",
    ),
    # Format device
    (r"\bformat\s+/dev/", "format device"),
    # mv to root or overwrite critical files
    (r"\bmv\s+.*\s+/etc/(?:passwd|shadow)\b", "move file to critical system location"),
    # cp to overwrite critical files
    (r"\bcp\s+.*\s+/etc/(?:passwd|shadow)\b", "copy file to critical system location"),
    # Indirect execution via eval
    (r"\beval\s+.*\brm\b", "indirect rm via eval"),
    (r"\beval\s+.*\bdd\b", "indirect dd via eval"),
    # Systemctl dangerous operations
    (
        r"\bsystemctl\s+(stop|restart|disable)\s+(sshd|ssh|network|systemd|dbus)\b",
        "stop critical system service",
    ),
    # Kill system processes
    (r"\bkillall\s+(systemd|dbus|sshd|ssh)\b", "kill critical system process"),
    (r"\bpkill\s+(systemd|dbus|sshd|ssh)\b", "kill critical system process"),
]


def _normalize_command(command: str) -> str:
    """Normalize command for safer pattern matching.

    Removes common obfuscation techniques:
    - Multiple spaces -> single space
    - Leading/trailing whitespace
    - Common comment patterns
    """
    import re

    # Replace multiple spaces with single space
    normalized = re.sub(r"\s+", " ", command)
    # Remove shell comments (but be careful with # in strings)
    # This is a simplified version - removes # and everything after it
    # A more robust solution would need proper shell parsing
    lines = []
    for line in normalized.split("\n"):
        # Simple comment removal - not perfect but catches common cases
        if "#" in line:
            # Keep # if it's in quotes (simplified check)
            parts = line.split("#")
            if len(parts) > 1:
                # Check if # is likely in a string (preceded by quotes)
                before = parts[0]
                if before.count('"') % 2 == 0 and before.count("'") % 2 == 0:
                    line = before
        lines.append(line)
    normalized = "\n".join(lines)
    return normalized.strip()


def check_dangerous_command(command: str) -> str | None:
    """Check if a command is dangerous.

    Args:
        command: The command to check

    Returns:
        Warning message if dangerous, None if safe
    """
    # Normalize command to catch obfuscated attempts
    normalized = _normalize_command(command)

    # Check both original and normalized command
    commands_to_check = [command, normalized]

    for cmd in commands_to_check:
        for pattern, reason in DANGEROUS_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
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


async def _read_stream(
    stream: asyncio.StreamReader,
    lines: list[str],
    on_progress: Any,
    stream_name: str,
) -> None:
    """Read a stream line-by-line, handling both \n and \r."""
    buffer = b""
    try:
        while True:
            chunk = await stream.read(4096)
            if not chunk:
                break
            buffer += chunk
            while True:
                nl = buffer.find(b"\n")
                cr = buffer.find(b"\r")
                if nl == -1 and cr == -1:
                    break
                if nl == -1:
                    pos, delim = cr, b"\r"
                elif cr == -1:
                    pos, delim = nl, b"\n"
                else:
                    pos, delim = (cr, b"\r") if cr < nl else (nl, b"\n")
                line = buffer[:pos].decode("utf-8", errors="replace")
                buffer = buffer[pos + len(delim) :]
                if not line and delim == b"\r":
                    continue
                lines.append(line)
                if on_progress:
                    on_progress(
                        {
                            "type": "bash_output",
                            "stream": stream_name,
                            "line": line,
                            "is_progress": delim == b"\r",
                        }
                    )
        if buffer:
            line = buffer.decode("utf-8", errors="replace")
            lines.append(line)
            if on_progress:
                on_progress(
                    {
                        "type": "bash_output",
                        "stream": stream_name,
                        "line": line,
                        "is_progress": False,
                    }
                )
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


async def execute_bash(
    command: str,
    cwd: str | None = None,
    timeout: int = 600,
    env: dict[str, str] | None = None,
    on_progress: Any = None,
) -> BashOutput:
    """Execute a bash command with optional real-time progress streaming."""
    command = translate_command_for_windows(command)
    process_env = os.environ.copy()
    if env:
        process_env.update(env)

    try:
        import subprocess

        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            # Set UTF-8 code page for cmd.exe to avoid GBK encoding issues
            command = f"chcp 65001 >nul 2>&1 && {command}"

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=process_env,
            startupinfo=startupinfo,
        )

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        stdout_task = asyncio.create_task(
            _read_stream(process.stdout, stdout_lines, on_progress, "stdout")
        )
        stderr_task = asyncio.create_task(
            _read_stream(process.stderr, stderr_lines, on_progress, "stderr")
        )

        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                process.kill()
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
            for t in (stdout_task, stderr_task):
                if not t.done():
                    t.cancel()
                    try:
                        await t
                    except asyncio.CancelledError:
                        pass
            return BashOutput(
                stdout="\n".join(stdout_lines),
                stderr=f"Command timed out after {timeout} seconds",
                exit_code=-1,
                command=command,
            )
        except asyncio.CancelledError:
            # Handle task cancellation - kill the subprocess
            try:
                process.kill()
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
            for t in (stdout_task, stderr_task):
                if not t.done():
                    t.cancel()
                    try:
                        await t
                    except asyncio.CancelledError:
                        pass
            raise  # Re-raise to propagate cancellation

        await asyncio.gather(stdout_task, stderr_task)

        def decode_lines(lines: list[str]) -> str:
            return "\n".join(lines)

        return BashOutput(
            stdout=decode_lines(stdout_lines),
            stderr=decode_lines(stderr_lines),
            exit_code=process.returncode or 0,
            command=command,
        )
    except Exception as e:
        return BashOutput(stdout="", stderr=str(e), exit_code=-1, command=command)


def _update_cwd_from_cd(command: str, current_cwd: str | None, set_app_state) -> None:
    """Parse cd/Set-Location/chdir and update app_state.cwd if valid."""
    cmd = command.strip()
    if not cmd:
        return
    lower = cmd.lower()
    m = re.match(r'^(?:cd|chdir|set-location)\s+["\']?(.+?)["\']?\s*$', lower)
    if not m:
        if re.match(r"^(?:cd|chdir|set-location)\s*$", lower):
            target = os.path.expanduser("~")
        else:
            return
    else:
        target = m.group(1).strip()
    base = current_cwd or os.getcwd()
    if os.path.isabs(target):
        new_cwd = os.path.normpath(target)
    else:
        new_cwd = os.path.normpath(os.path.join(base, target))
    if os.path.isdir(new_cwd):
        set_app_state(lambda s: replace(s, cwd=new_cwd))


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
    result = await execute_bash(
        input_data.command, cwd=cwd, timeout=input_data.timeout, on_progress=on_progress
    )

    # Track directory changes from cd commands
    if context.set_app_state and result.exit_code == 0:
        _update_cwd_from_cd(input_data.command, cwd, context.set_app_state)

    return ToolResult(data=result)


async def bash_description(input_data: BashInput, options: dict[str, Any]) -> str:
    """Get description for bash tool use."""
    return f"$ {input_data.command[:100]}"


def bash_user_facing_name(input_data: BashInput) -> str:
    """Get user facing name for bash tool."""
    return f"Bash({input_data.command[:50]})"


def is_read_only_command(command: str) -> bool:
    """Check if command is read-only (doesn't modify files)."""
    cmd_lower = command.strip().lower()

    # Destructive substrings that override safe command prefixes
    destructive_markers = [
        # find destructive actions
        " -delete",
        " -exec",
        " -ok",
        # git branch destructive actions
        "git branch -d",
        "git branch -m",
        "git branch -c",
        "git branch --delete",
        "git branch --move",
        "git branch --copy",
        # output redirection (overwrite / append)
        " > ",
        " >> ",
        " 1> ",
        " 2> ",
        " &> ",
        " >| ",
        # piped to destructive commands
        "| xargs rm",
        "| xargs mv",
        "| xargs cp",
        "| sh",
        "| bash",
        # command chaining with destructive commands
        "; rm ",
        "; mv ",
        "; cp ",
        "; chmod ",
        "; chown ",
        "&& rm ",
        "&& mv ",
        "&& cp ",
        "&& chmod ",
        "&& chown ",
    ]
    for marker in destructive_markers:
        if marker in cmd_lower:
            return False

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
        "wc",
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
