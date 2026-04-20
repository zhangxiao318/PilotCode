"""Bash tool for executing shell commands."""

import asyncio
import re
import os
import sys
from typing import Any
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

    # rm [-rf] FILE/DIR -> del /q FILE or rmdir /s /q DIR
    rm_match = re.match(r"^rm\s+(-\w*\s+)?(.+)$", cmd_stripped)
    if rm_match:
        flags = rm_match.group(1) or ""
        target = rm_match.group(2).strip()
        # Check if it's a directory removal
        if "-r" in flags or "-R" in flags or "-rf" in flags or "-fr" in flags:
            return f"rmdir /s /q {target}"
        return f"del /q {target}"

    # cp [-r] SRC DEST -> copy SRC DEST or xcopy /e /i /y SRC DEST
    cp_match = re.match(r"^cp\s+(-\w*\s+)?(.+?)\s+(.+)$", cmd_stripped)
    if cp_match:
        flags = cp_match.group(1) or ""
        src = cp_match.group(2).strip()
        dest = cp_match.group(3).strip()
        if "-r" in flags or "-R" in flags or "-a" in flags:
            return f"xcopy /e /i /y {src} {dest}"
        return f"copy /y {src} {dest}"

    # mv SRC DEST -> move SRC DEST
    mv_match = re.match(r"^mv\s+(.+?)\s+(.+)$", cmd_stripped)
    if mv_match:
        src = mv_match.group(1).strip()
        dest = mv_match.group(2).strip()
        return f"move /y {src} {dest}"

    # touch FILE -> type nul > FILE
    touch_match = re.match(r"^touch\s+(.+)$", cmd_stripped)
    if touch_match:
        files = touch_match.group(1)
        # For multiple files, create each
        return f"powershell -Command \"{'; '.join(f'New-Item -ItemType File -Path {f.strip()} -Force' for f in files.split())}\""

    # mkdir [-p] DIR -> mkdir DIR (Windows mkdir doesn't have -p but creates intermediates)
    mkdir_match = re.match(r"^mkdir\s+(-p\s+)?(.+)$", cmd_stripped)
    if mkdir_match:
        dirs = mkdir_match.group(2).strip()
        return f"mkdir {dirs}"

    # rmdir DIR -> rmdir /q DIR
    rmdir_match = re.match(r"^rmdir\s+(.+)$", cmd_stripped)
    if rmdir_match:
        dirs = rmdir_match.group(1).strip()
        return f"rmdir /q {dirs}"

    # which CMD -> where CMD
    which_match = re.match(r"^which\s+(.+)$", cmd_stripped)
    if which_match:
        cmd = which_match.group(1).strip()
        return f"where {cmd}"

    # clear -> cls
    if cmd_stripped == "clear":
        return "cls"

    # uname -> ver
    if cmd_stripped == "uname":
        return "ver"

    # ln -s TARGET LINK -> mklink LINK TARGET
    ln_match = re.match(r"^ln\s+-s\s+(.+?)\s+(.+)$", cmd_stripped)
    if ln_match:
        target = ln_match.group(1).strip()
        link = ln_match.group(2).strip()
        return f"mklink {link} {target}"

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
    # Windows dangerous patterns
    (r"\bdel\s+(/[fqsa]\s*)+\s*C:\\\\", "recursive delete on system drive"),
    (r"\bformat\s+[a-zA-Z]:", "format drive"),
    (r"\brd\s+(/[sq]\s*)+\s*C:\\\\", "recursive delete on system drive"),
    (r"\brmdir\s+(/[sq]\s*)+\s*C:\\\\", "recursive delete on system drive"),
    (r"\bxcopy\s+/.*\s+C:\\\\.*\s+/[ey]*", "dangerous xcopy on system drive"),
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
    # Force UTF-8 encoding for child processes
    process_env["PYTHONIOENCODING"] = "utf-8"

    try:
        # Hide window on Windows
        import subprocess

        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            # Set UTF-8 code page for cmd.exe to avoid GBK encoding issues
            command = f"chcp 65001 >nul 2>&1 && {command}"

        # Create subprocess
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=process_env,
            startupinfo=startupinfo,
        )

        # Wait for completion with timeout
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)

        # Try multiple encodings for Windows compatibility
        # UTF-8 is tried first because we set chcp 65001 and PYTHONIOENCODING.
        # GBK/cp936 is tried as fallback for legacy tools.
        def decode_output(data: bytes) -> str:
            for encoding in ["utf-8", "gbk", "gb2312", "cp936", "latin-1"]:
                try:
                    return data.decode(encoding, errors="strict")
                except UnicodeDecodeError:
                    continue
            return data.decode("utf-8", errors="replace")

        return BashOutput(
            stdout=decode_output(stdout),
            stderr=decode_output(stderr),
            exit_code=process.returncode or 0,
            command=command,
        )
    except asyncio.TimeoutError:
        # Kill the process if timeout
        try:
            process.kill()
            await process.wait()
        except Exception:
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
