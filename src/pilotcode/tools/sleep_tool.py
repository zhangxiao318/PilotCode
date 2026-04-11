"""Sleep tool for adding delays."""

import asyncio
from typing import Any
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class SleepInput(BaseModel):
    """Input for Sleep tool."""

    seconds: float = Field(description="Number of seconds to sleep", ge=0, le=3600)
    reason: str | None = Field(default=None, description="Reason for sleeping")


class SleepOutput(BaseModel):
    """Output from Sleep tool."""

    seconds: float
    reason: str | None
    message: str


async def sleep_call(
    input_data: SleepInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[SleepOutput]:
    """Sleep for specified duration."""
    # Check if aborted
    if context.is_aborted():
        return ToolResult(
            data=SleepOutput(seconds=0, reason=input_data.reason, message="Sleep aborted"),
            error="Aborted",
        )

    # Sleep
    await asyncio.sleep(input_data.seconds)

    return ToolResult(
        data=SleepOutput(
            seconds=input_data.seconds,
            reason=input_data.reason,
            message=f"Slept for {input_data.seconds} seconds",
        )
    )


SleepTool = build_tool(
    name="Sleep",
    description=lambda x, o: f"Sleep for {x.seconds}s" + (f" ({x.reason})" if x.reason else ""),
    input_schema=SleepInput,
    output_schema=SleepOutput,
    call=sleep_call,
    aliases=["sleep", "wait", "delay"],
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
)

register_tool(SleepTool)
