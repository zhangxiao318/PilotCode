"""Tests for the agent management and orchestration system."""

import os
import tempfile

import pytest

from pilotcode.agent.agent_manager import (
    AgentManager,
    AgentStatus,
    ENHANCED_AGENT_DEFINITIONS,
    get_agent_manager,
)
from pilotcode.agent.agent_orchestrator import get_orchestrator
from tests.mock_llm import MockLLMResponse


class TestAgentManager:
    """Tests for AgentManager lifecycle."""

    def test_create_default_agent(self):
        mgr = AgentManager()
        agent = mgr.create_agent()
        assert agent.definition.name == "coder"
        assert agent.status == AgentStatus.PENDING
        assert agent.agent_id is not None

    def test_create_typed_agent(self):
        mgr = AgentManager()
        agent = mgr.create_agent(agent_type="debugger")
        assert agent.definition.name == "debugger"
        assert "🐛" in agent.definition.icon

    def test_create_named_agent(self):
        mgr = AgentManager()
        agent = mgr.create_agent(name="custom_bot")
        assert agent.definition.name == "custom_bot"

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AgentManager(storage_dir=tmpdir)
            agent = mgr.create_agent(agent_type="tester")
            agent_id = agent.agent_id

            # Simulate status change
            mgr.set_agent_status(agent_id, AgentStatus.COMPLETED)

            # New manager loads from disk
            mgr2 = AgentManager(storage_dir=tmpdir)
            loaded = mgr2.get_agent(agent_id)
            assert loaded is not None
            assert loaded.status == AgentStatus.COMPLETED
            assert loaded.definition.name == "tester"

    def test_parent_child_tree(self):
        mgr = AgentManager()
        parent = mgr.create_agent()
        child = mgr.create_agent(parent_id=parent.agent_id)
        grandchild = mgr.create_agent(parent_id=child.agent_id)

        tree = mgr.get_agent_tree(parent.agent_id)
        assert tree["agent"]["agent_id"] == parent.agent_id
        assert len(tree["children"]) == 1
        assert tree["children"][0]["agent"]["agent_id"] == child.agent_id
        assert len(tree["children"][0]["children"]) == 1

    def test_list_agents_with_filter(self):
        mgr = AgentManager()
        a1 = mgr.create_agent(agent_type="coder")
        a2 = mgr.create_agent(agent_type="debugger")
        mgr.set_agent_status(a1.agent_id, AgentStatus.COMPLETED)

        pending = mgr.list_agents(status=AgentStatus.PENDING)
        assert len(pending) >= 1
        assert all(a.status == AgentStatus.PENDING for a in pending)

    def test_delete_agent_removes_from_parent(self):
        mgr = AgentManager()
        parent = mgr.create_agent()
        child = mgr.create_agent(parent_id=parent.agent_id)

        mgr.delete_agent(child.agent_id)
        assert child.agent_id not in mgr.agents
        assert child.agent_id not in mgr.get_agent(parent.agent_id).child_ids


class TestAgentDefinitions:
    """Tests for built-in agent definitions."""

    def test_all_seven_types_exist(self):
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

    def test_coder_has_code_tools(self):
        coder = ENHANCED_AGENT_DEFINITIONS["coder"]
        assert "Bash" in coder.allowed_tools
        assert "FileWrite" in coder.allowed_tools

    def test_explainer_has_read_tools(self):
        explainer = ENHANCED_AGENT_DEFINITIONS["explainer"]
        assert "FileRead" in explainer.allowed_tools
        assert "WebSearch" in explainer.allowed_tools

    def test_reviewer_is_read_only(self):
        reviewer = ENHANCED_AGENT_DEFINITIONS["reviewer"]
        assert "FileWrite" not in reviewer.allowed_tools
        assert "FileEdit" not in reviewer.allowed_tools


class TestAgentWorkflows:
    """Tests for workflow creation."""

    def test_create_workflow(self):
        mgr = AgentManager()
        wf = mgr.create_workflow("test_wf", "A test workflow")
        assert wf.workflow_id is not None
        assert wf.name == "test_wf"

    def test_add_agent_to_workflow(self):
        mgr = AgentManager()
        wf = mgr.create_workflow("wf", "desc")
        agent = mgr.create_agent()

        ok = mgr.add_agent_to_workflow(wf.workflow_id, agent.agent_id)
        assert ok is True
        assert agent.agent_id in mgr.get_workflow(wf.workflow_id).agent_ids


class TestAgentOrchestrator:
    """Tests for AgentOrchestrator."""

    @pytest.mark.asyncio
    async def test_run_agent_task_mocked(self, mock_model_client, monkeypatch):
        """Orchestrator can run a simple agent task against mock LLM."""
        monkeypatch.setattr(
            "pilotcode.agent.agent_orchestrator.get_model_client",
            lambda: mock_model_client,
        )
        mock_model_client.set_responses(
            [
                MockLLMResponse.with_text("Task complete."),
            ]
        )

        mgr = AgentManager()
        agent = mgr.create_agent()
        orch = get_orchestrator()

        result = await orch._run_agent_task(agent, "Say hello")
        assert "Task complete." in result
        assert agent.status == AgentStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_orchestrator_runs_tool_and_continues(
        self, mock_model_client, auto_allow_permissions, monkeypatch
    ):
        """Orchestrator handles a tool call inside an agent task."""
        monkeypatch.setattr(
            "pilotcode.agent.agent_orchestrator.get_model_client",
            lambda: mock_model_client,
        )
        mock_model_client.set_responses(
            [
                MockLLMResponse.with_tool_call("Bash", {"command": "echo orch"}),
                MockLLMResponse.with_text("The output was orch."),
            ]
        )

        mgr = AgentManager()
        agent = mgr.create_agent()
        orch = get_orchestrator()

        result = await orch._run_agent_task(agent, "Run a command")
        assert "orch" in result.lower()
        assert agent.turns > 0
