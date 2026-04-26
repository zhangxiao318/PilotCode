"""Message type definitions."""

from typing import Literal, Any
from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class ContentBlock(BaseModel):
    """Base class for content blocks."""

    pass


class TextBlock(ContentBlock):
    """Text content block."""

    type: Literal["text"] = "text"
    text: str


class ToolUseBlock(ContentBlock):
    """Tool use block (model requests tool execution)."""

    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict[str, Any]


class ToolResultBlock(ContentBlock):
    """Tool result block (tool execution result)."""

    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str | list[ContentBlock]
    is_error: bool = False


class ImageBlock(ContentBlock):
    """Image content block."""

    type: Literal["image"] = "image"
    source: dict[str, Any]  # {type: "base64", media_type: str, data: str}


class Message(BaseModel):
    """Base message class."""

    uuid: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.now)


class UserMessage(Message):
    """User message."""

    type: Literal["user"] = "user"
    content: str | list[ContentBlock]


class AssistantMessage(Message):
    """Assistant message."""

    type: Literal["assistant"] = "assistant"
    content: str | list[ContentBlock]
    reasoning_content: str | None = None  # DeepSeek requires echoing reasoning back


class SystemMessage(Message):
    """System message."""

    type: Literal["system"] = "system"
    content: str


class ToolUseMessage(Message):
    """Tool use message."""

    type: Literal["tool_use"] = "tool_use"
    tool_use_id: str
    name: str
    input: dict[str, Any]


class ToolResultMessage(Message):
    """Tool result message."""

    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str | dict[str, Any]
    is_error: bool = False


class ProgressMessage(Message):
    """Progress message for long-running operations."""

    type: Literal["progress"] = "progress"
    message: str
    progress: float | None = None  # 0.0 to 1.0


class AttachmentMessage(Message):
    """File attachment message."""

    type: Literal["attachment"] = "attachment"
    file_path: str
    content: str


# Union type for all messages
MessageType = (
    UserMessage
    | AssistantMessage
    | SystemMessage
    | ToolUseMessage
    | ToolResultMessage
    | ProgressMessage
    | AttachmentMessage
)


_MESSAGE_TYPE_MAP: dict[str, type[Message]] = {
    "user": UserMessage,
    "assistant": AssistantMessage,
    "system": SystemMessage,
    "tool_use": ToolUseMessage,
    "tool_result": ToolResultMessage,
    "progress": ProgressMessage,
    "attachment": AttachmentMessage,
}


def serialize_messages(messages: list[MessageType]) -> list[dict[str, Any]]:
    """Serialize messages to plain dicts."""
    return [msg.model_dump(mode="json") for msg in messages]


def deserialize_messages(data: list[dict[str, Any]]) -> list[MessageType]:
    """Deserialize messages from plain dicts."""
    result: list[MessageType] = []
    for item in data:
        msg_type = item.get("type")
        cls = _MESSAGE_TYPE_MAP.get(msg_type)
        if cls is None:
            continue
        result.append(cls.model_validate(item))
    return result


def to_api_format(messages: list[MessageType]) -> list[dict[str, Any]]:
    """Convert internal Pydantic messages to OpenAI-compatible API dict format.

    This bridges the internal message type system (types/message.py) and the
    API client (utils/model_client.py), eliminating ad-hoc conversion logic
    scattered across callers.

    Handles DeepSeek-critical invariants:
    - AssistantMessage + following ToolUseMessages → merged single assistant msg
    - Empty user messages are skipped (DeepSeek rejects them)
    - reasoning_content is preserved on assistant messages
    """
    import json

    result: list[dict[str, Any]] = []
    pending_assistant: dict[str, Any] | None = None
    pending_tool_calls: list[dict[str, Any]] = []

    def _flush_assistant() -> None:
        nonlocal pending_assistant, pending_tool_calls
        if pending_tool_calls:
            if pending_assistant is not None:
                pending_assistant["tool_calls"] = pending_tool_calls
                result.append(pending_assistant)
            else:
                result.append(
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": pending_tool_calls,
                    }
                )
            pending_tool_calls = []
            pending_assistant = None
        elif pending_assistant is not None:
            result.append(pending_assistant)
            pending_assistant = None

    for msg in messages:
        if isinstance(msg, SystemMessage):
            _flush_assistant()
            result.append({"role": "system", "content": msg.content})
        elif isinstance(msg, UserMessage):
            _flush_assistant()
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if content.strip():
                result.append({"role": "user", "content": content})
        elif isinstance(msg, AssistantMessage):
            _flush_assistant()
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            pending_assistant = {
                "role": "assistant",
                "content": content,
            }
            if msg.reasoning_content:
                pending_assistant["reasoning_content"] = msg.reasoning_content
        elif isinstance(msg, ToolUseMessage):
            pending_tool_calls.append(
                {
                    "id": msg.tool_use_id,
                    "type": "function",
                    "function": {"name": msg.name, "arguments": json.dumps(msg.input)},
                }
            )
        elif isinstance(msg, ToolResultMessage):
            _flush_assistant()
            result.append(
                {
                    "role": "tool",
                    "content": (
                        msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
                    ),
                    "tool_call_id": msg.tool_use_id,
                }
            )

    _flush_assistant()
    return result
