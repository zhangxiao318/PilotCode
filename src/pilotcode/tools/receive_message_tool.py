"""ReceiveMessage Tool - reads incoming mailbox messages.

Reference: Claude Code mailbox/teammate communication protocol.
"""

from typing import Any
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool
from ..agent import read_unread_messages


class ReceiveMessageInput(BaseModel):
    """Input for ReceiveMessage tool."""

    team_name: str | None = Field(default=None, description="Team name to check for messages")
    clear_after_read: bool = Field(default=True, description="Clear messages after reading")


class ReceiveMessageOutput(BaseModel):
    """Output from ReceiveMessage tool."""

    messages: list[dict] = Field(default_factory=list)
    count: int = 0


async def receive_message_call(
    input_data: ReceiveMessageInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[ReceiveMessageOutput]:
    """Read pending messages."""
    app_state = context.get_app_state() if context.get_app_state else None
    agent_name = getattr(app_state, "agent_id", None) or "unknown"
    team = input_data.team_name or "default"

    import os

    inbox_agent = os.environ.get("PILOTCODE_AGENT_NAME", agent_name)
    messages = read_unread_messages(inbox_agent, team, input_data.clear_after_read)

    return ToolResult(data=ReceiveMessageOutput(messages=messages, count=len(messages)))


async def receive_message_description(
    input_data: ReceiveMessageInput,
    options: dict[str, Any],
) -> str:
    return "Checking for incoming messages..."


ReceiveMessageTool = build_tool(
    name="ReceiveMessage",
    description=receive_message_description,
    input_schema=ReceiveMessageInput,
    output_schema=ReceiveMessageOutput,
    call=receive_message_call,
    aliases=["receive_message", "check_mail", "inbox"],
    search_hint="Read pending messages from team members",
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
)

register_tool(ReceiveMessageTool)
