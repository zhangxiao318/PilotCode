"""Bash tool for executing shell commands."""

import asyncio
import shlex
import os
from typing import Any
from dataclasses import dataclass
from pydantic import BaseModel, Field

from .base import Tool, ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class BashProgress(BaseModel):
    """Progress for bash command execution."""
    stdout: str = ""
    stderr: str = ""


class BashInput(BaseModel):
    """Input for Bash tool."""
    command: str = Field(description="The bash command to execute")
    timeout: int = Field(default=600, description="Timeout in seconds")
    description: str | None = Field(
        default=None, 
        description="Description of what the command does (for clarity)"
    )
    working_dir: str | None = Field(
        default=None,
        description="Working directory for the command"
    )
    run_in_background: bool = Field(
        default=False,
        description="Run command in background"
    )


class BashOutput(BaseModel):
    """Output from Bash tool."""
    stdout: str
    stderr: str
    exit_code: int
    command: str


async def execute_bash(
    command: str,
    cwd: str | None = None,
    timeout: int = 600,
    env: dict[str, str] | None = None
) -> BashOutput:
    """Execute a bash command."""
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
            env=process_env
        )
        
        # Wait for completion with timeout
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout
        )
        
        return BashOutput(
            stdout=stdout.decode('utf-8', errors='replace'),
            stderr=stderr.decode('utf-8', errors='replace'),
            exit_code=process.returncode or 0,
            command=command
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
            command=command
        )
    except Exception as e:
        return BashOutput(
            stdout="",
            stderr=str(e),
            exit_code=-1,
            command=command
        )


async def bash_call(
    input_data: BashInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any
) -> ToolResult[BashOutput]:
    """Execute bash command."""
    # Check permissions
    permission = await can_use_tool("BashTool", input_data)
    if isinstance(permission, dict):
        if permission.get("behavior") == "deny":
            return ToolResult(
                data=BashOutput(stdout="", stderr="Permission denied", exit_code=-1, command=input_data.command),
                error="Permission denied"
            )
    elif hasattr(permission, "behavior") and permission.behavior == "deny":
        return ToolResult(
            data=BashOutput(stdout="", stderr="Permission denied", exit_code=-1, command=input_data.command),
            error="Permission denied"
        )
    
    # Determine working directory
    cwd = input_data.working_dir
    if cwd is None and context.get_app_state:
        app_state = context.get_app_state()
        cwd = getattr(app_state, 'cwd', os.getcwd())
    
    # Execute command
    result = await execute_bash(
        input_data.command,
        cwd=cwd,
        timeout=input_data.timeout
    )
    
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
        'ls', 'cat', 'echo', 'pwd', 'whoami', 'id', 'uname', 'date',
        'head', 'tail', 'less', 'more', 'grep', 'find', 'which',
        'ps', 'top', 'htop', 'df', 'du', 'free', 'uptime', 'env',
        'git status', 'git log', 'git diff', 'git show', 'git branch',
        'python --version', 'node --version', 'npm --version',
        'curl -I', 'curl --head', 'wget --spider',
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
    is_read_only=lambda x: is_read_only_command(x.command),
    is_concurrency_safe=lambda x: is_read_only_command(x.command),
    user_facing_name=bash_user_facing_name,
)

# Register the tool
register_tool(BashTool)
