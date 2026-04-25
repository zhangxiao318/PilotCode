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
