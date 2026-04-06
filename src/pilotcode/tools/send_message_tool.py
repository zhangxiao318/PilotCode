"""SendMessage tool for agent communication."""

from typing import Any
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
from datetime import datetime

from .base import Tool, ToolResult, ToolUseContext, build_tool
from .registry import register_tool


@dataclass
class Message:
    """Message between agents."""

    from_id: str
    to_id: str
    content: str
    timestamp: str
    message_type: str = "text"


# Message bus - in-memory storage
_message_bus: dict[str, list[Message]] = {}


class SendMessageInput(BaseModel):
    """Input for SendMessage tool."""

    to: str = Field(description="Recipient agent ID or 'broadcast'")
    content: str = Field(description="Message content")
    message_type: str = Field(default="text", description="Message type")
    from_id: str | None = Field(default=None, description="Sender ID (auto if not set)")


class SendMessageOutput(BaseModel):
    """Output from SendMessage tool."""

    to: str
    content: str
    delivered: bool
    message_id: str


async def send_message_call(
    input_data: SendMessageInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[SendMessageOutput]:
    """Send message to agent."""

    sender = input_data.from_id or "system"

    msg = Message(
        from_id=sender,
        to_id=input_data.to,
        content=input_data.content,
        timestamp=datetime.now().isoformat(),
        message_type=input_data.message_type,
    )

    # Store message
    if input_data.to not in _message_bus:
        _message_bus[input_data.to] = []

    _message_bus[input_data.to].append(msg)

    # Generate message ID
    message_id = f"msg_{datetime.now().timestamp()}"

    return ToolResult(
        data=SendMessageOutput(
            to=input_data.to,
            content=(
                input_data.content[:100] + "..."
                if len(input_data.content) > 100
                else input_data.content
            ),
            delivered=True,
            message_id=message_id,
        )
    )


class ReceiveMessageInput(BaseModel):
    """Input for ReceiveMessage tool."""

    agent_id: str = Field(description="Agent ID to check messages for")
    mark_read: bool = Field(default=True, description="Mark messages as read")


class ReceiveMessageOutput(BaseModel):
    """Output from ReceiveMessage tool."""

    agent_id: str
    messages: list[dict]
    count: int


async def receive_message_call(
    input_data: ReceiveMessageInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[ReceiveMessageOutput]:
    """Receive messages for agent."""

    messages = _message_bus.get(input_data.agent_id, [])

    message_list = [
        {"from": m.from_id, "content": m.content, "timestamp": m.timestamp, "type": m.message_type}
        for m in messages
    ]

    # Clear if mark_read
    if input_data.mark_read:
        _message_bus[input_data.agent_id] = []

    return ToolResult(
        data=ReceiveMessageOutput(
            agent_id=input_data.agent_id, messages=message_list, count=len(message_list)
        )
    )


# Register tools
SendMessageTool = build_tool(
    name="SendMessage",
    description=lambda x, o: f"Send message to {x.to}: {x.content[:30]}...",
    input_schema=SendMessageInput,
    output_schema=SendMessageOutput,
    call=send_message_call,
    aliases=["send", "message"],
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: True,
)

ReceiveMessageTool = build_tool(
    name="ReceiveMessage",
    description=lambda x, o: f"Receive messages for {x.agent_id}",
    input_schema=ReceiveMessageInput,
    output_schema=ReceiveMessageOutput,
    call=receive_message_call,
    aliases=["receive", "inbox"],
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
)

register_tool(SendMessageTool)
register_tool(ReceiveMessageTool)
