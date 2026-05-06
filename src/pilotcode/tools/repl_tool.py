"""REPL tool for interactive programming environments."""

import asyncio
from typing import Any
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class REPLInput(BaseModel):
    """Input for REPL tool."""

    language: str = Field(description="Programming language: python, node, etc.")
    code: str = Field(description="Code to execute")
    timeout: int = Field(default=30, description="Timeout in seconds")


class REPLOutput(BaseModel):
    """Output from REPL tool."""

    language: str
    stdout: str
    stderr: str
    exit_code: int


# Language configurations
REPL_CONFIGS = {
    "python": {"command": "python3", "args": ["-c"], "extension": ".py"},
    "node": {"command": "node", "args": ["-e"], "extension": ".js"},
    "bash": {"command": "bash", "args": ["-c"], "extension": ".sh"},
    "ruby": {"command": "ruby", "args": ["-e"], "extension": ".rb"},
    "perl": {"command": "perl", "args": ["-e"], "extension": ".pl"},
}


async def repl_call(
    input_data: REPLInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[REPLOutput]:
    """Execute code in REPL."""

    config = REPL_CONFIGS.get(input_data.language)

    if not config:
        return ToolResult(
            data=REPLOutput(language=input_data.language, stdout="", stderr="", exit_code=-1),
            error=f"Unsupported language: {input_data.language}. Supported: {', '.join(REPL_CONFIGS.keys())}",
        )

    try:
        # Run the code asynchronously to avoid blocking the event loop
        cmd = [config["command"]] + config["args"] + [input_data.code]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=input_data.timeout
            )
        except asyncio.TimeoutError:
            try:
                process.kill()
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except Exception:
                pass
            return ToolResult(
                data=REPLOutput(
                    language=input_data.language,
                    stdout="",
                    stderr=f"Timeout after {input_data.timeout} seconds",
                    exit_code=-1,
                ),
                error=f"Timeout after {input_data.timeout} seconds",
            )

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        return ToolResult(
            data=REPLOutput(
                language=input_data.language,
                stdout=stdout,
                stderr=stderr,
                exit_code=process.returncode or 0,
            )
        )

    except Exception as e:
        return ToolResult(
            data=REPLOutput(language=input_data.language, stdout="", stderr=str(e), exit_code=-1),
            error=str(e),
        )


REPLTool = build_tool(
    name="REPL",
    description=lambda x, o: f"Execute {x.language} code",
    input_schema=REPLInput,
    output_schema=REPLOutput,
    call=repl_call,
    aliases=["repl", "exec", "run_code"],
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: False,
)

register_tool(REPLTool)
