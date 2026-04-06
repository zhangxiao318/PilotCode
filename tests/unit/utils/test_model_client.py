"""Tests for model_client module."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pilotcode.utils.model_client import (
    ToolCall,
    ToolResult,
    Message,
    ModelClient,
    get_model_client,
)


class TestToolCall:
    """Tests for ToolCall dataclass."""

    def test_creation(self):
        """Test creating ToolCall."""
        tc = ToolCall(id="call_123", name="Bash", arguments={"command": "echo hello"})

        assert tc.id == "call_123"
        assert tc.name == "Bash"
        assert tc.arguments == {"command": "echo hello"}


class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_creation(self):
        """Test creating ToolResult."""
        tr = ToolResult(tool_call_id="call_123", content="hello", is_error=False)

        assert tr.tool_call_id == "call_123"
        assert tr.content == "hello"
        assert tr.is_error is False

    def test_error_result(self):
        """Test creating error ToolResult."""
        tr = ToolResult(tool_call_id="call_456", content="Command not found", is_error=True)

        assert tr.is_error is True


class TestMessage:
    """Tests for Message dataclass."""

    def test_system_message(self):
        """Test creating system message."""
        msg = Message(role="system", content="You are a helpful assistant")

        assert msg.role == "system"
        assert msg.content == "You are a helpful assistant"
        assert msg.tool_calls is None

    def test_user_message(self):
        """Test creating user message."""
        msg = Message(role="user", content="Hello")

        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_assistant_message_with_tool_calls(self):
        """Test creating assistant message with tool calls."""
        tool_calls = [ToolCall(id="call_1", name="Bash", arguments={"command": "ls"})]
        msg = Message(role="assistant", content="", tool_calls=tool_calls)

        assert msg.role == "assistant"
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].name == "Bash"

    def test_tool_message(self):
        """Test creating tool message."""
        msg = Message(role="tool", content="result", tool_call_id="call_1", name="Bash")

        assert msg.role == "tool"
        assert msg.tool_call_id == "call_1"
        assert msg.name == "Bash"


class TestModelClient:
    """Tests for ModelClient."""

    def test_initialization_with_defaults(self, monkeypatch):
        """Test initialization with default config."""
        monkeypatch.setenv("PILOTCODE_API_KEY", "test-key")

        client = ModelClient()

        assert client.api_key == "test-key"
        assert client.model is not None
        assert client.base_url is not None
        assert client.client is not None

    def test_initialization_with_custom_params(self):
        """Test initialization with custom parameters."""
        client = ModelClient(api_key="custom-key", base_url="https://custom.api.com", model="gpt-4")

        assert client.api_key == "custom-key"
        assert client.base_url == "https://custom.api.com"
        assert client.model == "gpt-4"

    def test_convert_messages(self):
        """Test converting messages to API format."""
        client = ModelClient(api_key="test")

        messages = [
            Message(role="system", content="You are helpful"),
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there"),
        ]

        api_messages = client._convert_messages(messages)

        assert len(api_messages) == 3
        assert api_messages[0] == {"role": "system", "content": "You are helpful"}
        assert api_messages[1] == {"role": "user", "content": "Hello"}
        assert api_messages[2] == {"role": "assistant", "content": "Hi there"}

    def test_convert_messages_with_tool_calls(self):
        """Test converting messages with tool calls."""
        client = ModelClient(api_key="test")

        messages = [
            Message(
                role="assistant",
                content="",
                tool_calls=[ToolCall(id="call_1", name="Bash", arguments={"command": "ls"})],
            ),
            Message(
                role="tool", content="file1.txt\nfile2.txt", tool_call_id="call_1", name="Bash"
            ),
        ]

        api_messages = client._convert_messages(messages)

        assert len(api_messages) == 2
        assert "tool_calls" in api_messages[0]
        assert api_messages[0]["tool_calls"][0]["id"] == "call_1"
        assert api_messages[1]["tool_call_id"] == "call_1"

    def test_convert_messages_with_content_list(self):
        """Test converting messages with content as list."""
        client = ModelClient(api_key="test")

        content_list = [{"type": "text", "text": "Hello"}]
        messages = [Message(role="user", content=content_list)]

        api_messages = client._convert_messages(messages)

        assert api_messages[0]["content"] == content_list

    def test_convert_tools(self):
        """Test converting tools to API format."""
        client = ModelClient(api_key="test")

        tools = [
            {
                "name": "Bash",
                "description": "Execute bash commands",
                "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}},
            }
        ]

        api_tools = client._convert_tools(tools)

        assert len(api_tools) == 1
        assert api_tools[0]["type"] == "function"
        assert api_tools[0]["function"]["name"] == "Bash"
        assert api_tools[0]["function"]["description"] == "Execute bash commands"

    @pytest.mark.asyncio
    async def test_chat_completion_non_stream(self):
        """Test non-streaming chat completion."""
        client = ModelClient(api_key="test")

        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {"message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}
            ]
        }
        mock_response.raise_for_status = MagicMock()

        # Mock client.post
        client.client.post = AsyncMock(return_value=mock_response)

        messages = [Message(role="user", content="Hi")]
        chunks = []

        async for chunk in client.chat_completion(messages, stream=False):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0]["choices"][0]["delta"]["content"] == "Hello!"

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing the client."""
        client = ModelClient(api_key="test")
        client.client.aclose = AsyncMock()

        await client.close()

        client.client.aclose.assert_called_once()


class TestGetModelClient:
    """Tests for get_model_client function."""

    def test_returns_singleton(self):
        """Test that get_model_client returns singleton."""
        # Reset global client
        import pilotcode.utils.model_client as mc

        original_client = mc._client
        mc._client = None

        try:
            client1 = get_model_client()
            client2 = get_model_client()

            assert client1 is client2
        finally:
            mc._client = original_client

    def test_creates_new_client_when_none(self):
        """Test creating new client when none exists."""
        # Reset global client
        import pilotcode.utils.model_client as mc

        original_client = mc._client
        mc._client = None

        try:
            client = get_model_client()
            assert isinstance(client, ModelClient)
        finally:
            mc._client = original_client


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
