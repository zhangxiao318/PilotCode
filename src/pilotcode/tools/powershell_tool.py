"""PowerShell Tool for Windows PowerShell execution."""

import asyncio
import sys
from typing import Any
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class PowerShellInput(BaseModel):
    """Input for PowerShell tool."""

    command: str = Field(description="The PowerShell command to execute")
    timeout: int = Field(default=600, description="Timeout in seconds")
    description: str | None = Field(default=None, description="Description of the command")
    working_dir: str | None = Field(default=None, description="Working directory for the command")


class PowerShellOutput(BaseModel):
    """Output from PowerShell tool."""

    stdout: str
    stderr: str
    exit_code: int
    command: str


def is_windows() -> bool:
    """Check if running on Windows."""
    return sys.platform == "win32"


async def execute_powershell(command: str, timeout: int = 600, cwd: str | None = None) -> PowerShellOutput:
    """Execute a PowerShell command."""
    if not is_windows():
        # On non-Windows, try to use PowerShell Core (pwsh)
        ps_executable = "pwsh"
    else:
        ps_executable = "powershell.exe"

    try:
        # Hide window on Windows
        import subprocess

        startupinfo = None
        if is_windows():
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE

        process = await asyncio.create_subprocess_exec(
            ps_executable,
            "-Command",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            startupinfo=startupinfo,
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)

        return PowerShellOutput(
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
            exit_code=process.returncode or 0,
            command=command,
        )
    except asyncio.TimeoutError:
        try:
            process.kill()
            await process.wait()
        except Exception:
            pass
        return PowerShellOutput(
            stdout="",
            stderr=f"Command timed out after {timeout} seconds",
            exit_code=-1,
            command=command,
        )
    except Exception as e:
        return PowerShellOutput(stdout="", stderr=str(e), exit_code=-1, command=command)


async def powershell_call(
    input_data: PowerShellInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[PowerShellOutput]:
    """Execute PowerShell command."""
    # Determine working directory
    cwd = input_data.working_dir
    if cwd is None and context.get_app_state:
        app_state = context.get_app_state()
        cwd = getattr(app_state, "cwd", os.getcwd())

    result = await execute_powershell(input_data.command, timeout=input_data.timeout, cwd=cwd)

    return ToolResult(data=result)


async def powershell_description(input_data: PowerShellInput, options: dict[str, Any]) -> str:
    """Get description for PowerShell tool."""
    return f"PS> {input_data.command[:100]}"


def is_read_only_command(command: str) -> bool:
    """Check if PowerShell command is read-only."""
    read_only_patterns = [
        "Get-",
        "Test-",
        "Find-",
        "Select-",
        "Where-",
        "Write-Host",
        "echo",
        "pwd",
        "cd",
    ]

    cmd_lower = command.strip()
    for pattern in read_only_patterns:
        if cmd_lower.startswith(pattern):
            return True
    return False


# Create the PowerShell tool
PowerShellTool = build_tool(
    name="PowerShell",
    description=powershell_description,
    input_schema=PowerShellInput,
    output_schema=PowerShellOutput,
    call=powershell_call,
    aliases=["powershell", "ps", "pwsh"],
    search_hint="Execute PowerShell commands",
    is_read_only=lambda x: is_read_only_command(x.command) if x else False,
    is_concurrency_safe=lambda x: is_read_only_command(x.command) if x else False,
)

register_tool(PowerShellTool)
