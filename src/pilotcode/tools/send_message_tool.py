"""SendMessage Tool for agent-to-agent communication.

Reference: Claude Code src/tools/SendMessageTool/SendMessageTool.ts

Allows a running agent to send messages to:
- Another agent in the same team
- The user (main thread)
- Broadcast to all team members
"""

from typing import Any
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool
from ..agent import get_agent_manager, write_to_mailbox, broadcast_to_team


class SendMessageInput(BaseModel):
    """Input for SendMessage tool."""

    to: str = Field(description="Recipient agent name, user, or '*' for broadcast")
    content: str = Field(description="Message content to send")
    subject: str | None = Field(default=None, description="Optional message subject/label")
    urgency: str | None = Field(
        default=None,
        description="'high' or 'normal'",
    )


class SendMessageOutput(BaseModel):
    """Output from SendMessage tool."""

    success: bool
    recipients: int = 0
    error: str | None = None


async def send_message_call(
    input_data: SendMessageInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[SendMessageOutput]:
    """Send a message to an agent or team."""
    manager = get_agent_manager()
    # Get sender info from app state
    app_state = context.get_app_state() if context.get_app_state else None
    sender_id = getattr(app_state, "agent_id", None) or "user"
    sender_name = sender_id

    recipient = input_data.to
    text = input_data.content

    # Handle broadcast to team
    if recipient == "*":
        # Find sender's team
        sender = manager.get_agent(sender_id)
        if sender and sender.team_name:
            count = broadcast_to_team(
                sender.team_name,
                exclude=sender_name,
                message={
                    "from": sender_name,
                    "text": text,
                    "subject": input_data.subject or "",
                    "urgency": input_data.urgency or "normal",
                },
            )
            return ToolResult(data=SendMessageOutput(success=True, recipients=count))
        return ToolResult(
            data=SendMessageOutput(success=False, error="No team found"),
        )

    # Send to specific recipient
    success = write_to_mailbox(
        recipient=recipient,
        team_name=input_data.subject or "default",
        message={
            "from": sender_name,
            "text": text,
            "subject": input_data.subject or "",
            "urgency": input_data.urgency or "normal",
        },
    )

    if success:
        return ToolResult(data=SendMessageOutput(success=True, recipients=1))

    # Also try direct in-process delivery via agent manager
    for aid, agent in manager.agents.items():
        if agent.definition.name == recipient or aid == recipient:
            agent.inbox.append(
                {
                    "from": sender_name,
                    "text": text,
                    "subject": input_data.subject or "",
                    "urgency": input_data.urgency or "normal",
                }
            )
            manager.update_agent(agent)
            return ToolResult(data=SendMessageOutput(success=True, recipients=1))

    return ToolResult(
        data=SendMessageOutput(success=False, error=f"Recipient '{recipient}' not found"),
    )


async def send_message_description(
    input_data: SendMessageInput,
    options: dict[str, Any],
) -> str:
    """Get description for send_message tool."""
    return f"Sending message to {input_data.to}..."


# Create the SendMessage tool
SendMessageTool = build_tool(
    name="SendMessage",
    description=send_message_description,
    input_schema=SendMessageInput,
    output_schema=SendMessageOutput,
    call=send_message_call,
    aliases=["send_message", "message", "tell"],
    search_hint="Send a message to another agent, user, or broadcast to team",
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: True,
)

register_tool(SendMessageTool)
