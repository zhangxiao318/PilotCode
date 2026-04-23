"""Tests for QueryEngine streaming, tool parsing, and message handling."""

import pytest

from pilotcode.types.message import (
    AssistantMessage,
    ToolUseMessage,
    ToolResultMessage,
)
from tests.mock_llm import MockLLMResponse


class TestQueryEngineBasics:
    """Tests for basic QueryEngine behavior."""

    @pytest.mark.asyncio
    async def test_empty_tools_list(self, mock_model_client, query_engine_factory):
        """Engine works with no tools registered."""
        mock_model_client.set_responses(
            [
                MockLLMResponse.with_text("Hello!"),
            ]
        )
        engine = query_engine_factory(tools=[])

        texts = []
        async for result in engine.submit_message("Hi"):
            if isinstance(result.message, AssistantMessage):
                texts.append(result.message.content)

        assert "Hello!" in "".join(texts)

    @pytest.mark.asyncio
    async def test_system_prompt_custom(self, mock_model_client, query_engine_factory):
        """Custom system prompt is included."""
        mock_model_client.set_responses(
            [
                MockLLMResponse.with_text("OK"),
            ]
        )
        engine = query_engine_factory(custom_system_prompt="You are a test assistant.")

        async for result in engine.submit_message("Go"):
            pass

        last = mock_model_client.get_last_messages()
        assert any("test assistant" in str(m.content) for m in last if m.role == "system")

    @pytest.mark.asyncio
    async def test_message_history_accumulates(self, mock_model_client, query_engine_factory):
        """Messages are stored in engine history."""
        mock_model_client.set_responses(
            [
                MockLLMResponse.with_text("A"),
                MockLLMResponse.with_text("B"),
            ]
        )
        engine = query_engine_factory()

        async for result in engine.submit_message("First"):
            pass
        async for result in engine.submit_message("Second"):
            pass

        roles = [type(m).__name__ for m in engine.messages]
        assert roles.count("UserMessage") == 2
        assert roles.count("AssistantMessage") == 2

    @pytest.mark.asyncio
    async def test_clear_history(self, mock_model_client, query_engine_factory):
        """clear_history removes all messages."""
        mock_model_client.set_responses(
            [
                MockLLMResponse.with_text("A"),
            ]
        )
        engine = query_engine_factory()
        async for result in engine.submit_message("Hi"):
            pass

        engine.clear_history()
        assert len(engine.messages) == 0


class TestQueryEngineToolParsing:
    """Tests for tool call parsing from streaming chunks."""

    @pytest.mark.asyncio
    async def test_single_tool_call(self, mock_model_client, query_engine_factory):
        """A single tool call is parsed correctly."""
        mock_model_client.set_responses(
            [
                MockLLMResponse.with_tool_call("Bash", {"command": "echo hi"}),
            ]
        )
        engine = query_engine_factory()

        tools = []
        async for result in engine.submit_message("Run bash"):
            if isinstance(result.message, ToolUseMessage):
                tools.append(result.message)

        assert len(tools) == 1
        assert tools[0].name == "Bash"
        assert tools[0].input["command"] == "echo hi"

    @pytest.mark.asyncio
    async def test_tool_call_with_content(self, mock_model_client, query_engine_factory):
        """Tool call may also have assistant text content."""
        mock_model_client.set_responses(
            [
                MockLLMResponse(
                    content="Let me run that.",
                    tool_calls=[
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "FileRead",
                                "arguments": '{"file_path": "/etc/passwd"}',
                            },
                        }
                    ],
                    finish_reason="tool_calls",
                ),
            ]
        )
        engine = query_engine_factory()

        content = ""
        tools = []
        async for result in engine.submit_message("Read file"):
            if isinstance(result.message, AssistantMessage):
                content += str(result.message.content)
            if isinstance(result.message, ToolUseMessage):
                tools.append(result.message)

        assert "Let me run that." in content
        assert len(tools) == 1
        assert tools[0].name == "FileRead"

    @pytest.mark.asyncio
    async def test_multiple_tool_calls(self, mock_model_client, query_engine_factory):
        """Multiple tool calls in one turn."""
        mock_model_client.set_responses(
            [
                MockLLMResponse(
                    content="",
                    tool_calls=[
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "Bash", "arguments": '{"command":"echo 1"}'},
                        },
                        {
                            "id": "c2",
                            "type": "function",
                            "function": {"name": "Bash", "arguments": '{"command":"echo 2"}'},
                        },
                    ],
                    finish_reason="tool_calls",
                ),
            ]
        )
        engine = query_engine_factory()

        tools = []
        async for result in engine.submit_message("Run two"):
            if isinstance(result.message, ToolUseMessage):
                tools.append(result.message)

        assert len(tools) == 2
        assert {t.input["command"] for t in tools} == {"echo 1", "echo 2"}

    @pytest.mark.asyncio
    async def test_add_tool_result(self, mock_model_client, query_engine_factory):
        """Tool results are added to history."""
        mock_model_client.set_responses(
            [
                MockLLMResponse.with_tool_call("Bash", {"command": "echo x"}),
                MockLLMResponse.with_text("Done"),
            ]
        )
        engine = query_engine_factory()

        tool_msg = None
        async for result in engine.submit_message("Run"):
            if isinstance(result.message, ToolUseMessage):
                tool_msg = result.message

        engine.add_tool_result(tool_msg.tool_use_id, "x\n", is_error=False)

        assert any(
            isinstance(m, ToolResultMessage) and m.tool_use_id == tool_msg.tool_use_id
            for m in engine.messages
        )

        # Second turn should include the tool result
        async for result in engine.submit_message("Continue"):
            if isinstance(result.message, AssistantMessage) and result.is_complete:
                assert result.message.content == "Done"

    @pytest.mark.asyncio
    async def test_streaming_content_chunks(self, mock_model_client, query_engine_factory):
        """Content is delivered in streaming chunks."""
        mock_model_client.set_responses(
            [
                MockLLMResponse.with_text("abcdefghijklmnopqrstuvwxyz"),
            ]
        )
        engine = query_engine_factory()

        chunks = []
        async for result in engine.submit_message("Count"):
            if isinstance(result.message, AssistantMessage) and not result.is_complete:
                chunks.append(result.message.content)

        # Mock client sends chunks of 4 chars
        assert len(chunks) > 1
        assert "".join(chunks) == "abcdefghijklmnopqrstuvwxyz"


class TestQueryEngineMultiTurn:
    """Tests for multi-turn conversations with tool execution loops."""

    @pytest.mark.asyncio
    async def test_two_turn_tool_loop(self, mock_model_client, query_engine_factory):
        """Full two-turn loop: user -> tool call -> result -> assistant."""
        mock_model_client.set_responses(
            [
                MockLLMResponse.with_tool_call("Glob", {"pattern": "*.py"}),
                MockLLMResponse.with_text("Found some Python files."),
            ]
        )
        engine = query_engine_factory()

        # Turn 1
        tool_msg = None
        async for result in engine.submit_message("List py files"):
            if isinstance(result.message, ToolUseMessage):
                tool_msg = result.message

        assert tool_msg is not None
        engine.add_tool_result(tool_msg.tool_use_id, "test.py\n")

        # Turn 2
        final = ""
        async for result in engine.submit_message("Continue"):
            if isinstance(result.message, AssistantMessage) and result.is_complete:
                final = result.message.content

        assert "Found some Python files." in final
        assert mock_model_client.call_count == 2

    @pytest.mark.asyncio
    async def test_three_turns_with_error_result(self, mock_model_client, query_engine_factory):
        """Tool returns error, then assistant responds."""
        mock_model_client.set_responses(
            [
                MockLLMResponse.with_tool_call("Bash", {"command": "badcmd"}),
                MockLLMResponse.with_text("That command failed."),
            ]
        )
        engine = query_engine_factory()

        tool_msg = None
        async for result in engine.submit_message("Run badcmd"):
            if isinstance(result.message, ToolUseMessage):
                tool_msg = result.message

        engine.add_tool_result(tool_msg.tool_use_id, "command not found", is_error=True)

        final = ""
        async for result in engine.submit_message("Continue"):
            if isinstance(result.message, AssistantMessage) and result.is_complete:
                final = result.message.content

        assert "failed" in final.lower()
