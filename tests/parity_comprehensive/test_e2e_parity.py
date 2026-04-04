"""End-to-end parity tests simulating original Claude Code conversation flows."""

import asyncio
import pytest

from pilotcode.query_engine import QueryEngine, QueryEngineConfig
from pilotcode.tools.base import ToolUseContext
from pilotcode.tools.registry import get_all_tools
from pilotcode.types.message import AssistantMessage, ToolUseMessage
from pilotcode.permissions.tool_executor import ToolExecutor
from tests.mock_llm import MockLLMResponse


# ---------------------------------------------------------------------------
# Full conversation loops
# ---------------------------------------------------------------------------
class TestE2EConversation:
    @pytest.mark.asyncio
    async def test_e2e_single_turn_text(self, mock_model_client, query_engine_factory):
        mock_model_client.set_responses([
            MockLLMResponse.with_text("Hello from parity test."),
        ])
        engine = query_engine_factory()
        text = ""
        async for result in engine.submit_message("Hi"):
            if isinstance(result.message, AssistantMessage) and result.is_complete:
                text = result.message.content
        assert "Hello" in text

    @pytest.mark.asyncio
    async def test_e2e_file_write_and_read(self, mock_model_client, query_engine_factory, auto_allow_permissions, tmp_path):
        tools = get_all_tools()
        file_path = str(tmp_path / "parity.py")
        mock_model_client.set_responses([
            MockLLMResponse.with_tool_call(
                "FileWrite",
                {"file_path": file_path, "content": "x = 1\n"},
            ),
            MockLLMResponse.with_tool_call(
                "FileRead",
                {"file_path": file_path},
            ),
            MockLLMResponse.with_text("File verified."),
        ])
        engine = query_engine_factory(tools=tools, cwd=str(tmp_path))
        executor = ToolExecutor()
        ctx = ToolUseContext()

        # Turn 1: FileWrite
        t1 = []
        async for result in engine.submit_message("Write parity.py"):
            if isinstance(result.message, ToolUseMessage):
                t1.append(result.message)
        assert len(t1) == 1 and t1[0].name == "FileWrite"
        r1 = await executor.execute_tool_by_name(t1[0].name, t1[0].input, ctx)
        assert r1.success
        engine.add_tool_result(t1[0].tool_use_id, str(r1.result.data))

        # Turn 2: FileRead
        t2 = []
        async for result in engine.submit_message("Read it back"):
            if isinstance(result.message, ToolUseMessage):
                t2.append(result.message)
        assert len(t2) == 1 and t2[0].name == "FileRead"
        r2 = await executor.execute_tool_by_name(t2[0].name, t2[0].input, ctx)
        assert r2.success
        engine.add_tool_result(t2[0].tool_use_id, str(r2.result.data))

        # Turn 3: final text
        text = ""
        async for result in engine.submit_message("Summarize"):
            if isinstance(result.message, AssistantMessage) and result.is_complete:
                text = result.message.content
        assert "File verified." in text

    @pytest.mark.asyncio
    async def test_e2e_bash_then_git_status(self, mock_model_client, query_engine_factory, auto_allow_permissions):
        tools = get_all_tools()
        mock_model_client.set_responses([
            MockLLMResponse.with_tool_call("Bash", {"command": "git --version"}),
            MockLLMResponse.with_tool_call("GitStatus", {"repo_path": "."}),
            MockLLMResponse.with_text("All good."),
        ])
        engine = query_engine_factory(tools=tools)
        executor = ToolExecutor()
        ctx = ToolUseContext()

        for expected_tool in ("Bash", "GitStatus"):
            t = []
            async for result in engine.submit_message("Run command"):
                if isinstance(result.message, ToolUseMessage):
                    t.append(result.message)
            assert len(t) == 1 and t[0].name == expected_tool, f"Expected {expected_tool}, got {[m.name for m in t]}"
            r = await executor.execute_tool_by_name(t[0].name, t[0].input, ctx)
            assert r.success
            engine.add_tool_result(t[0].tool_use_id, str(r.result.data))

        text = ""
        async for result in engine.submit_message("Continue"):
            if isinstance(result.message, AssistantMessage) and result.is_complete:
                text = result.message.content
        assert "All good." in text

    @pytest.mark.asyncio
    async def test_e2e_multi_tool_turn(self, mock_model_client, query_engine_factory, auto_allow_permissions):
        tools = get_all_tools()
        mock_model_client.set_responses([
            MockLLMResponse(
                content="Parallel read.",
                tool_calls=[
                    {"id": "c1", "type": "function",
                     "function": {"name": "Glob", "arguments": '{"pattern": "*.py"}'}},
                    {"id": "c2", "type": "function",
                     "function": {"name": "GitStatus", "arguments": '{"repo_path": "."}'}},
                ],
                finish_reason="tool_calls",
            ),
            MockLLMResponse.with_text("Done."),
        ])
        engine = query_engine_factory(tools=tools)
        executor = ToolExecutor()
        ctx = ToolUseContext()

        t = []
        async for result in engine.submit_message("Scan repo"):
            if isinstance(result.message, ToolUseMessage):
                t.append(result.message)
        assert len(t) == 2
        for tm in t:
            r = await executor.execute_tool_by_name(tm.name, tm.input, ctx)
            assert r.success
            engine.add_tool_result(tm.tool_use_id, str(r.result.data))

        text = ""
        async for result in engine.submit_message("Continue"):
            if isinstance(result.message, AssistantMessage) and result.is_complete:
                text = result.message.content
        assert "Done." in text


# ---------------------------------------------------------------------------
# REPL-level parity
# ---------------------------------------------------------------------------
class TestREPLParity:
    def test_repl_imports(self):
        from pilotcode.components.repl import REPL
        assert REPL is not None

    def test_headless_repl_exists(self):
        from pilotcode.components.repl import run_headless
        assert callable(run_headless)
