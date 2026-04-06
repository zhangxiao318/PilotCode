"""Integration tests for full conversation + tool execution flows."""

import pytest

from pilotcode.query_engine import QueryEngineConfig
from pilotcode.query_engine import QueryEngine as QE
from pilotcode.tools.registry import get_all_tools
from pilotcode.types.message import AssistantMessage, ToolUseMessage
from tests.mock_llm import MockLLMResponse


class TestBasicConversation:
    """Tests for basic LLM conversation without tools."""

    @pytest.mark.asyncio
    async def test_simple_text_response(self, mock_model_client, query_engine_factory):
        """Engine returns a simple text response."""
        mock_model_client.set_responses(
            [
                MockLLMResponse.with_text("Hello, world!"),
            ]
        )

        engine = query_engine_factory()
        chunks = []
        async for result in engine.submit_message("Say hello"):
            msg = result.message
            if isinstance(msg, AssistantMessage):
                chunks.append(msg.content)

        assert "Hello, world!" in "".join(chunks)
        assert mock_model_client.call_count == 1

    @pytest.mark.asyncio
    async def test_multiple_turns_no_tools(self, mock_model_client, query_engine_factory):
        """Multiple user messages without tools."""
        mock_model_client.set_responses(
            [
                MockLLMResponse.with_text("First reply"),
                MockLLMResponse.with_text("Second reply"),
            ]
        )

        engine = query_engine_factory()

        async for result in engine.submit_message("First"):
            pass
        async for result in engine.submit_message("Second"):
            pass

        assert mock_model_client.call_count == 2
        last_msgs = mock_model_client.get_last_messages()
        assert any("Second" in str(m.content) for m in last_msgs)


class TestToolCallFlow:
    """Tests for single-tool and multi-tool execution flows."""

    @pytest.mark.asyncio
    async def test_bash_tool_execution(
        self, mock_model_client, query_engine_factory, auto_allow_permissions
    ):
        """LLM calls Bash tool, we execute it, and LLM responds to the result."""
        tools = get_all_tools()
        mock_model_client.set_responses(
            [
                MockLLMResponse.with_tool_call("Bash", {"command": "echo integration_test"}),
                MockLLMResponse.with_text("The output says integration_test"),
            ]
        )

        engine = query_engine_factory(tools=tools)

        # First turn: yields tool call
        tool_msgs = []
        async for result in engine.submit_message("Run a bash command"):
            if isinstance(result.message, ToolUseMessage):
                tool_msgs.append(result.message)

        assert len(tool_msgs) == 1
        assert tool_msgs[0].name == "Bash"

        # Simulate tool execution
        engine.add_tool_result(tool_msgs[0].tool_use_id, "integration_test\n")

        # Second turn: LLM responds to result
        async for result in engine.submit_message("Please continue"):
            if isinstance(result.message, AssistantMessage) and result.is_complete:
                assert "integration_test" in result.message.content

        assert mock_model_client.call_count == 2

    @pytest.mark.asyncio
    async def test_file_write_then_read(
        self, mock_model_client, query_engine_factory, auto_allow_permissions, temp_dir
    ):
        """LLM writes a file then reads it back."""
        tools = get_all_tools()
        test_file = str(temp_dir / "test_factorial.c")

        mock_model_client.set_responses(
            [
                MockLLMResponse.with_tool_call(
                    "FileWrite",
                    {
                        "file_path": test_file,
                        "content": "int factorial(int n) { return n <= 1 ? 1 : n * factorial(n-1); }",
                    },
                ),
                MockLLMResponse.with_tool_call(
                    "FileRead",
                    {"file_path": test_file},
                ),
                MockLLMResponse.with_text("The file contains a factorial function."),
            ]
        )

        engine = query_engine_factory(tools=tools, cwd=temp_dir)

        # Turn 1: FileWrite
        turn1_tools = []
        async for result in engine.submit_message("Write factorial.c"):
            if isinstance(result.message, ToolUseMessage):
                turn1_tools.append(result.message)

        assert len(turn1_tools) == 1
        assert turn1_tools[0].name == "FileWrite"

        # We need to actually execute the tool to create the file
        from pilotcode.permissions.tool_executor import ToolExecutor

        executor = ToolExecutor()
        from pilotcode.tools.base import ToolUseContext

        ctx = ToolUseContext()
        exec_result = await executor.execute_tool_by_name(
            turn1_tools[0].name, turn1_tools[0].input, ctx
        )
        assert exec_result.success  # ToolExecutionResult has success
        engine.add_tool_result(turn1_tools[0].tool_use_id, str(exec_result.result.data))

        # Turn 2: FileRead
        turn2_tools = []
        async for result in engine.submit_message("Read it back"):
            if isinstance(result.message, ToolUseMessage):
                turn2_tools.append(result.message)

        assert len(turn2_tools) == 1
        assert turn2_tools[0].name == "FileRead"

        exec_result2 = await executor.execute_tool_by_name(
            turn2_tools[0].name, turn2_tools[0].input, ctx
        )
        assert exec_result2.success  # ToolExecutionResult has success
        engine.add_tool_result(turn2_tools[0].tool_use_id, str(exec_result2.result.data))

        # Turn 3: final text
        final_text = ""
        async for result in engine.submit_message("Summarize"):
            if isinstance(result.message, AssistantMessage) and result.is_complete:
                final_text = result.message.content

        assert "factorial" in final_text.lower()
        assert mock_model_client.call_count == 3

    @pytest.mark.asyncio
    async def test_multi_tool_single_turn(
        self, mock_model_client, query_engine_factory, auto_allow_permissions
    ):
        """LLM calls multiple tools in one turn."""
        tools = get_all_tools()
        mock_model_client.set_responses(
            [
                MockLLMResponse(
                    content="I'll run two commands.",
                    tool_calls=[
                        {
                            "id": "call_001",
                            "type": "function",
                            "function": {
                                "name": "Bash",
                                "arguments": '{"command": "echo first"}',
                            },
                        },
                        {
                            "id": "call_002",
                            "type": "function",
                            "function": {
                                "name": "Bash",
                                "arguments": '{"command": "echo second"}',
                            },
                        },
                    ],
                    finish_reason="tool_calls",
                ),
                MockLLMResponse.with_text("Done with both commands."),
            ]
        )

        engine = query_engine_factory(tools=tools)

        tool_msgs = []
        async for result in engine.submit_message("Run two commands"):
            if isinstance(result.message, ToolUseMessage):
                tool_msgs.append(result.message)

        assert len(tool_msgs) == 2
        assert tool_msgs[0].name == "Bash"
        assert tool_msgs[1].name == "Bash"

        # Execute both and feed back
        from pilotcode.permissions.tool_executor import ToolExecutor
        from pilotcode.tools.base import ToolUseContext

        executor = ToolExecutor()
        ctx = ToolUseContext()

        for tm in tool_msgs:
            res = await executor.execute_tool_by_name(tm.name, tm.input, ctx)
            assert res.success  # ToolExecutionResult has success
            engine.add_tool_result(tm.tool_use_id, str(res.result.data))

        async for result in engine.submit_message("Continue"):
            if isinstance(result.message, AssistantMessage) and result.is_complete:
                assert "Done" in result.message.content

        assert mock_model_client.call_count == 2


class TestToolInputNormalization:
    """Tests that tool inputs are normalized correctly."""

    @pytest.mark.asyncio
    async def test_path_to_file_path_mapping(self, auto_allow_permissions):
        """LLM may send 'path' instead of 'file_path' for file tools."""
        from pilotcode.permissions.tool_executor import ToolExecutor
        from pilotcode.tools.base import ToolUseContext
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = tmpdir + "/norm_test.txt"
            executor = ToolExecutor()
            ctx = ToolUseContext()

            # Simulate LLM sending 'path' instead of 'file_path'
            result = await executor.execute_tool_by_name(
                "FileWrite",
                {"path": test_path, "content": "normalized"},
                ctx,
            )
            assert result.success, result.message  # ToolExecutionResult has success

            result2 = await executor.execute_tool_by_name(
                "FileRead",
                {"path": test_path},
                ctx,
            )
            assert result2.success  # ToolExecutionResult has success
            assert "normalized" in str(result2.result.data)
