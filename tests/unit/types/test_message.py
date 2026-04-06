"""Tests for message types module."""

import pytest
from datetime import datetime
from uuid import UUID

from pilotcode.types.message import (
    ContentBlock,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    ImageBlock,
    Message,
    UserMessage,
    AssistantMessage,
    SystemMessage,
    ToolUseMessage,
    ToolResultMessage,
)


class TestContentBlock:
    """Tests for ContentBlock base class."""
    
    def test_base_class(self):
        """Test ContentBlock can be instantiated."""
        block = ContentBlock()
        assert isinstance(block, ContentBlock)


class TestTextBlock:
    """Tests for TextBlock."""
    
    def test_creation(self):
        """Test creating TextBlock."""
        block = TextBlock(text="Hello, world!")
        
        assert block.type == "text"
        assert block.text == "Hello, world!"
    
    def test_default_type(self):
        """Test type is set by default."""
        block = TextBlock(text="Test")
        
        assert block.type == "text"


class TestToolUseBlock:
    """Tests for ToolUseBlock."""
    
    def test_creation(self):
        """Test creating ToolUseBlock."""
        block = ToolUseBlock(
            id="call_123",
            name="Bash",
            input={"command": "echo hello"}
        )
        
        assert block.type == "tool_use"
        assert block.id == "call_123"
        assert block.name == "Bash"
        assert block.input == {"command": "echo hello"}
    
    def test_complex_input(self):
        """Test ToolUseBlock with complex input."""
        block = ToolUseBlock(
            id="call_456",
            name="FileWrite",
            input={
                "file_path": "/tmp/test.txt",
                "content": "test content",
                "options": {"overwrite": True}
            }
        )
        
        assert block.input["file_path"] == "/tmp/test.txt"
        assert block.input["options"]["overwrite"] is True


class TestToolResultBlock:
    """Tests for ToolResultBlock."""
    
    def test_creation(self):
        """Test creating ToolResultBlock."""
        block = ToolResultBlock(
            tool_use_id="call_123",
            content="Hello from bash"
        )
        
        assert block.type == "tool_result"
        assert block.tool_use_id == "call_123"
        assert block.content == "Hello from bash"
        assert block.is_error is False
    
    def test_error_result(self):
        """Test ToolResultBlock with error."""
        block = ToolResultBlock(
            tool_use_id="call_456",
            content="Command not found",
            is_error=True
        )
        
        assert block.is_error is True
    
    def test_content_as_list(self):
        """Test ToolResultBlock with content as list."""
        text_block = TextBlock(text="Result")
        block = ToolResultBlock(
            tool_use_id="call_789",
            content=[text_block]
        )
        
        assert isinstance(block.content, list)
        assert len(block.content) == 1


class TestImageBlock:
    """Tests for ImageBlock."""
    
    def test_creation(self):
        """Test creating ImageBlock."""
        block = ImageBlock(
            source={
                "type": "base64",
                "media_type": "image/png",
                "data": "iVBORw0KGgo="
            }
        )
        
        assert block.type == "image"
        assert block.source["type"] == "base64"
        assert block.source["media_type"] == "image/png"


class TestMessage:
    """Tests for Message base class."""
    
    def test_has_uuid(self):
        """Test Message has UUID."""
        msg = UserMessage(content="Hello")
        
        assert hasattr(msg, "uuid")
        assert isinstance(msg.uuid, UUID)
    
    def test_has_timestamp(self):
        """Test Message has timestamp."""
        msg = UserMessage(content="Hello")
        
        assert hasattr(msg, "timestamp")
        assert isinstance(msg.timestamp, datetime)
    
    def test_unique_uuids(self):
        """Test each message has unique UUID."""
        msg1 = UserMessage(content="Hello")
        msg2 = UserMessage(content="World")
        
        assert msg1.uuid != msg2.uuid


class TestUserMessage:
    """Tests for UserMessage."""
    
    def test_creation_with_string(self):
        """Test creating UserMessage with string content."""
        msg = UserMessage(content="Hello")
        
        assert msg.type == "user"
        assert msg.content == "Hello"
    
    def test_creation_with_blocks(self):
        """Test creating UserMessage with content blocks."""
        text_block = TextBlock(text="Hello")
        image_block = ImageBlock(source={"type": "base64", "media_type": "image/png", "data": "..."})
        
        msg = UserMessage(content=[text_block, image_block])
        
        assert msg.type == "user"
        assert len(msg.content) == 2
        assert isinstance(msg.content[0], TextBlock)
        assert isinstance(msg.content[1], ImageBlock)


class TestAssistantMessage:
    """Tests for AssistantMessage."""
    
    def test_creation_with_string(self):
        """Test creating AssistantMessage with string content."""
        msg = AssistantMessage(content="I can help you!")
        
        assert msg.type == "assistant"
        assert msg.content == "I can help you!"
    
    def test_creation_with_blocks(self):
        """Test creating AssistantMessage with tool use blocks."""
        tool_block = ToolUseBlock(
            id="call_1",
            name="Bash",
            input={"command": "ls"}
        )
        
        msg = AssistantMessage(content=[tool_block])
        
        assert msg.type == "assistant"
        assert len(msg.content) == 1
        assert isinstance(msg.content[0], ToolUseBlock)


class TestSystemMessage:
    """Tests for SystemMessage."""
    
    def test_creation(self):
        """Test creating SystemMessage."""
        msg = SystemMessage(content="You are a helpful assistant")
        
        assert msg.type == "system"
        assert msg.content == "You are a helpful assistant"
    
    def test_content_is_string(self):
        """Test SystemMessage content is always string."""
        msg = SystemMessage(content="System prompt")
        
        assert isinstance(msg.content, str)


class TestToolUseMessage:
    """Tests for ToolUseMessage."""
    
    def test_creation(self):
        """Test creating ToolUseMessage."""
        msg = ToolUseMessage(
            tool_use_id="call_123",
            name="Bash",
            input={"command": "echo test"}
        )
        
        assert msg.type == "tool_use"
        assert msg.tool_use_id == "call_123"
        assert msg.name == "Bash"
        assert msg.input == {"command": "echo test"}


class TestToolResultMessage:
    """Tests for ToolResultMessage."""
    
    def test_creation_with_string(self):
        """Test creating ToolResultMessage with string content."""
        msg = ToolResultMessage(
            tool_use_id="call_123",
            content="Command output"
        )
        
        assert msg.type == "tool_result"
        assert msg.tool_use_id == "call_123"
        assert msg.content == "Command output"
        assert msg.is_error is False
    
    def test_creation_with_dict(self):
        """Test creating ToolResultMessage with dict content."""
        msg = ToolResultMessage(
            tool_use_id="call_456",
            content={"result": "success", "data": [1, 2, 3]}
        )
        
        assert isinstance(msg.content, dict)
        assert msg.content["result"] == "success"
    
    def test_error_result(self):
        """Test ToolResultMessage with error."""
        msg = ToolResultMessage(
            tool_use_id="call_789",
            content="Error: File not found",
            is_error=True
        )
        
        assert msg.is_error is True


class TestSerialization:
    """Tests for serialization."""
    
    def test_user_message_to_dict(self):
        """Test serializing UserMessage to dict."""
        msg = UserMessage(content="Hello")
        data = msg.dict()
        
        assert data["type"] == "user"
        assert data["content"] == "Hello"
        assert "uuid" in data
        assert "timestamp" in data
    
    def test_message_roundtrip(self):
        """Test serializing and deserializing message."""
        original = ToolUseMessage(
            tool_use_id="call_1",
            name="Bash",
            input={"command": "ls"}
        )
        
        data = original.dict()
        restored = ToolUseMessage(**data)
        
        assert restored.tool_use_id == original.tool_use_id
        assert restored.name == original.name
        assert restored.input == original.input


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
