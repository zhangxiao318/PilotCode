"""Tests for unified prompts module."""

import pytest
from pilotcode.services.prompts import (
    get_system_prompt,
    get_tool_prompt,
    get_agent_prompt,
    get_verifier_prompt,
    get_l1_verifier_prompt,
    get_l2_verifier_prompt,
    get_l3_verifier_prompt,
    get_planner_prompt,
    get_compact_prompt,
    get_analysis_prompt,
    get_implementation_prompt,
    get_review_prompt,
    _TOOL_PROMPTS,
    _AGENT_PROMPTS,
)


class TestBasePrompts:
    def test_get_system_prompt_returns_string(self):
        prompt = get_system_prompt(include_tools=True)
        assert isinstance(prompt, str)
        assert len(prompt) > 100
        assert "PilotCode" in prompt

    def test_get_system_prompt_without_tools(self):
        prompt = get_system_prompt(include_tools=False)
        assert isinstance(prompt, str)
        assert "PilotCode" in prompt
        # Without tools, should not contain tool-specific descriptions
        assert "## Available Tools" not in prompt


class TestToolPrompts:
    def test_get_tool_prompt(self):
        prompt = get_tool_prompt("Bash")
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_tool_prompt_unknown(self):
        prompt = get_tool_prompt("UnknownTool")
        assert prompt == ""

    def test_tool_prompts_defined(self):
        assert "Bash" in _TOOL_PROMPTS
        assert "FileRead" in _TOOL_PROMPTS
        assert "FileWrite" in _TOOL_PROMPTS
        assert "FileEdit" in _TOOL_PROMPTS
        assert "Glob" in _TOOL_PROMPTS
        assert "Grep" in _TOOL_PROMPTS
        assert "CodeSearch" in _TOOL_PROMPTS


class TestAgentPrompts:
    def test_get_agent_prompt_coder(self):
        prompt = get_agent_prompt("coder")
        assert isinstance(prompt, str)
        assert "coding" in prompt.lower()

    def test_get_agent_prompt_debugger(self):
        prompt = get_agent_prompt("debugger")
        assert isinstance(prompt, str)
        assert "debug" in prompt.lower() or "bug" in prompt.lower()

    def test_get_agent_prompt_unknown(self):
        prompt = get_agent_prompt("unknown_type")
        assert "specialized AI assistant" in prompt

    def test_all_agents_defined(self):
        assert "coder" in _AGENT_PROMPTS
        assert "debugger" in _AGENT_PROMPTS
        assert "explainer" in _AGENT_PROMPTS
        assert "tester" in _AGENT_PROMPTS
        assert "reviewer" in _AGENT_PROMPTS
        assert "planner" in _AGENT_PROMPTS
        assert "explorer" in _AGENT_PROMPTS


class TestVerifierPrompts:
    def test_get_l1_verifier_prompt(self):
        prompt = get_l1_verifier_prompt()
        assert isinstance(prompt, str)
        assert "L1" in prompt or "basic" in prompt.lower()

    def test_get_l2_verifier_prompt(self):
        prompt = get_l2_verifier_prompt()
        assert isinstance(prompt, str)
        assert "L2" in prompt or "implementation" in prompt.lower()

    def test_get_l3_verifier_prompt(self):
        prompt = get_l3_verifier_prompt()
        assert isinstance(prompt, str)
        assert "L3" in prompt or "comprehensive" in prompt.lower()

    def test_get_verifier_prompt_by_level(self):
        # Default to L1
        prompt = get_verifier_prompt()
        assert isinstance(prompt, str)

        # Explicit levels
        prompt_l1 = get_verifier_prompt(level=1)
        prompt_l2 = get_verifier_prompt(level=2)
        prompt_l3 = get_verifier_prompt(level=3)

        assert isinstance(prompt_l1, str)
        assert isinstance(prompt_l2, str)
        assert isinstance(prompt_l3, str)


class TestPlannerPrompts:
    def test_get_planner_prompt(self):
        prompt = get_planner_prompt()
        assert isinstance(prompt, str)
        assert "planner" in prompt.lower() or "plan" in prompt.lower()

    def test_get_planner_prompt_with_params(self):
        prompt = get_planner_prompt(complexity=0.3, json_capable=False)
        assert isinstance(prompt, str)


class TestSpecializedPrompts:
    def test_get_compact_prompt(self):
        prompt = get_compact_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) < 200

    def test_get_analysis_prompt(self):
        prompt = get_analysis_prompt()
        assert isinstance(prompt, str)
        assert "analysis" in prompt.lower()

    def test_get_implementation_prompt(self):
        prompt = get_implementation_prompt()
        assert isinstance(prompt, str)
        assert "implement" in prompt.lower()

    def test_get_review_prompt(self):
        prompt = get_review_prompt()
        assert isinstance(prompt, str)
        assert "review" in prompt.lower()
