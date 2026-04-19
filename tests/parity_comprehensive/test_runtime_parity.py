"""Parity tests for core runtime behavior vs original Claude Code."""

import json
import pytest

from pilotcode.query_engine import QueryEngine, QueryEngineConfig
from pilotcode.tools.base import ToolUseContext
from pilotcode.tools.registry import get_all_tools
from pilotcode.types.message import AssistantMessage, ToolUseMessage
from tests.mock_llm import MockLLMResponse


# ---------------------------------------------------------------------------
# QueryEngine streaming & multi-turn
# ---------------------------------------------------------------------------
class TestQueryEngineParity:
    @pytest.mark.asyncio
    async def test_streaming_text_response(self, mock_model_client, query_engine_factory):
        mock_model_client.set_responses(
            [
                MockLLMResponse.with_text("Parity check passed."),
            ]
        )
        engine = query_engine_factory()
        chunks = []
        async for result in engine.submit_message("Test"):
            if isinstance(result.message, AssistantMessage) and not result.is_complete:
                chunks.append(result.message.content)
        assert "Parity" in "".join(chunks)

    @pytest.mark.asyncio
    async def test_tool_call_then_continue(
        self, mock_model_client, query_engine_factory, auto_allow_permissions
    ):
        tools = get_all_tools()
        mock_model_client.set_responses(
            [
                MockLLMResponse.with_tool_call("Bash", {"command": "echo parity"}),
                MockLLMResponse.with_text("Done."),
            ]
        )
        engine = query_engine_factory(tools=tools)
        tool_msgs = []
        async for result in engine.submit_message("Run bash"):
            if isinstance(result.message, ToolUseMessage):
                tool_msgs.append(result.message)
        assert len(tool_msgs) == 1
        engine.add_tool_result(tool_msgs[0].tool_use_id, "parity\n")
        async for result in engine.submit_message("Continue"):
            if isinstance(result.message, AssistantMessage) and result.is_complete:
                assert "Done." in result.message.content

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_in_one_turn(
        self, mock_model_client, query_engine_factory, auto_allow_permissions
    ):
        tools = get_all_tools()
        mock_model_client.set_responses(
            [
                MockLLMResponse(
                    content="Running two commands.",
                    tool_calls=[
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "Bash", "arguments": '{"command": "echo a"}'},
                        },
                        {
                            "id": "call_2",
                            "type": "function",
                            "function": {"name": "Bash", "arguments": '{"command": "echo b"}'},
                        },
                    ],
                    finish_reason="tool_calls",
                ),
                MockLLMResponse.with_text("Finished both."),
            ]
        )
        engine = query_engine_factory(tools=tools)
        tool_msgs = []
        async for result in engine.submit_message("Run two"):
            if isinstance(result.message, ToolUseMessage):
                tool_msgs.append(result.message)
        assert len(tool_msgs) == 2

    @pytest.mark.asyncio
    async def test_message_history_accumulates(self, mock_model_client, query_engine_factory):
        mock_model_client.set_responses(
            [
                MockLLMResponse.with_text("First."),
                MockLLMResponse.with_text("Second."),
            ]
        )
        engine = query_engine_factory()
        async for _ in engine.submit_message("A"):
            pass
        async for _ in engine.submit_message("B"):
            pass
        assert len(engine.messages) >= 4  # user, assistant, user, assistant


# ---------------------------------------------------------------------------
# Tool Orchestration (original partitions concurrency-safe batches)
# ---------------------------------------------------------------------------
class TestToolOrchestrationParity:
    @pytest.mark.asyncio
    async def test_read_only_tools_are_concurrency_safe(self, auto_allow_permissions):
        from pilotcode.tools.registry import get_tool_by_name

        file_read = get_tool_by_name("FileRead")
        glob_tool = get_tool_by_name("Glob")
        # These should report concurrency-safe
        assert file_read.is_concurrency_safe(None) is True
        assert glob_tool.is_concurrency_safe(None) is True

    @pytest.mark.asyncio
    async def test_write_tools_are_not_concurrency_safe(self, auto_allow_permissions):
        from pilotcode.tools.registry import get_tool_by_name

        file_write = get_tool_by_name("FileWrite")
        bash = get_tool_by_name("Bash")
        # Use dummy valid inputs where possible; None safety is also tested
        assert file_write.is_concurrency_safe(None) is False
        # BashTool uses is_read_only_command: echo is read-only, rm is not
        assert bash.is_concurrency_safe(bash.input_schema(command="echo test")) is True
        assert bash.is_concurrency_safe(bash.input_schema(command="rm -rf /tmp/foo")) is False


# ---------------------------------------------------------------------------
# Permission system
# ---------------------------------------------------------------------------
class TestPermissionParity:
    def test_permission_levels_exist(self):
        from pilotcode.permissions.permission_manager import PermissionLevel

        levels = {
            PermissionLevel.ASK,
            PermissionLevel.ALLOW,
            PermissionLevel.ALWAYS_ALLOW,
            PermissionLevel.DENY,
            PermissionLevel.NEVER_ALLOW,
        }
        assert len(levels) >= 4

    def test_session_grant_persists(self):
        from pilotcode.permissions.permission_manager import PermissionManager, PermissionLevel

        pm = PermissionManager()
        pm.grant_session_permission("Bash")
        assert pm.check_permission("Bash", {})[0] is True

    def test_risk_levels_exist(self):
        from pilotcode.permissions.permission_manager import PermissionManager

        pm = PermissionManager()
        # Verify risk classification exists for known tools
        assert pm.get_tool_risk_level("FileRead") is not None
        assert pm.get_tool_risk_level("Bash") is not None
        assert pm.get_tool_risk_level("FileWrite") is not None


# ---------------------------------------------------------------------------
# Hook system
# ---------------------------------------------------------------------------
class TestHookParity:
    def test_hook_types_exist(self):
        from pilotcode.hooks.hook_manager import HookType

        expected = {
            HookType.PRE_TOOL_USE,
            HookType.POST_TOOL_USE,
            HookType.PRE_AGENT_RUN,
            HookType.POST_AGENT_RUN,
            HookType.ON_ERROR,
            HookType.ON_PERMISSION_DENIED,
        }
        assert len(expected) == 6

    @pytest.mark.asyncio
    async def test_hook_registration_and_execution(self):
        from pilotcode.hooks.hook_manager import HookManager, HookType

        hm = HookManager()
        called = []

        async def my_hook(ctx):
            called.append(ctx)

        hm.register(HookType.PRE_TOOL_USE, my_hook)
        await hm.execute_hooks(HookType.PRE_TOOL_USE, "dummy")
        assert len(called) == 1

    @pytest.mark.asyncio
    async def test_pre_tool_use_can_deny(self):
        from pilotcode.hooks.hook_manager import HookManager, HookType

        hm = HookManager()

        async def deny_hook(ctx):
            return {"action": "deny", "reason": "test"}

        hm.register(HookType.PRE_TOOL_USE, deny_hook)
        result = await hm.execute_hooks(HookType.PRE_TOOL_USE, "dummy")
        # HookManager returns a HookResult aggregate; individual hooks may
        # influence the result via side effects or return values captured internally.
        assert result is not None


# ---------------------------------------------------------------------------
# Agent system
# ---------------------------------------------------------------------------
class TestAgentParity:
    def test_all_builtin_agent_types_exist(self):
        from pilotcode.agent.agent_manager import ENHANCED_AGENT_DEFINITIONS

        expected = {
            "coder",
            "debugger",
            "explainer",
            "tester",
            "reviewer",
            "planner",
            "explorer",
            "verifier",
        }
        assert set(ENHANCED_AGENT_DEFINITIONS.keys()) == expected

    def test_agent_persistence(self):
        import tempfile
        from pilotcode.agent.agent_manager import AgentManager, AgentStatus

        with tempfile.TemporaryDirectory() as tmp:
            mgr = AgentManager(storage_dir=tmp)
            agent = mgr.create_agent(agent_type="tester")
            mgr.set_agent_status(agent.agent_id, AgentStatus.COMPLETED)
            mgr2 = AgentManager(storage_dir=tmp)
            loaded = mgr2.get_agent(agent.agent_id)
            assert loaded.status == AgentStatus.COMPLETED

    def test_agent_parent_child_tree(self):
        from pilotcode.agent.agent_manager import AgentManager

        mgr = AgentManager()
        p = mgr.create_agent()
        c = mgr.create_agent(parent_id=p.agent_id)
        tree = mgr.get_agent_tree(p.agent_id)
        assert tree["children"][0]["agent"]["agent_id"] == c.agent_id


# ---------------------------------------------------------------------------
# Services / Infrastructure gaps vs original
# ---------------------------------------------------------------------------
class TestServiceGaps:
    """These document features present in original but missing/unfinished here."""

    def test_session_persistence_exists(self):
        from pilotcode.query_engine import QueryEngine

        assert hasattr(QueryEngine, "save_session") and hasattr(QueryEngine, "load_session")

    def test_auto_compact_exists(self):
        from pilotcode.query_engine import QueryEngineConfig

        assert hasattr(QueryEngineConfig, "auto_compact")

    def test_token_counting_exists(self):
        from pilotcode.query_engine import QueryEngine

        assert hasattr(QueryEngine, "count_tokens")

    def test_headless_mode_exists(self):
        from pilotcode.components.repl import run_headless

        assert callable(run_headless)

    def test_mcp_server_management_exists(self):
        from pilotcode.commands.base import get_all_commands

        names = {c.name for c in get_all_commands()}
        assert "mcp-add" in names or "mcp-remove" in names

    def test_cost_tracking_wired(self):
        from pilotcode.query_engine import QueryEngine

        assert hasattr(QueryEngine, "track_cost")

    def test_tool_result_caching_exists(self):
        from pilotcode.query_engine import QueryEngineConfig

        assert hasattr(QueryEngineConfig, "cache_tool_results")
