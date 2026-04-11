"""Integration between orchestration system and PilotCode.

Connects the orchestration layer with existing PilotCode components.
"""

from __future__ import annotations

from typing import Any, Optional

from ..utils.model_client import get_model_client
from .coordinator import AgentCoordinator, get_coordinator


class OrchestrationAdapter:
    """Adapter to integrate orchestration with PilotCode's existing systems."""

    def __init__(self):
        self.coordinator: Optional[AgentCoordinator] = None
        self.model_client = get_model_client()

    def initialize(self):
        """Initialize the orchestration system."""

        def agent_factory(role: str, prompt: str) -> Any:
            """Factory for creating agent instances."""
            return AgentInstance(role, prompt, self.model_client)

        self.coordinator = get_coordinator(agent_factory, self.model_client)

    async def execute_task(
        self, task: str, context: dict = None, auto_decompose: bool = True
    ) -> dict:
        """Execute a task with orchestration."""
        if not self.coordinator:
            self.initialize()

        result = await self.coordinator.execute(
            task=task, context=context, auto_decompose=auto_decompose
        )

        return result.to_dict()


class AgentInstance:
    """Lightweight agent instance for orchestration."""

    def __init__(self, role: str, prompt: str, model_client: Any):
        self.role = role
        self.prompt = prompt
        self.model_client = model_client
        self.tools_used: list[str] = []
        self._system_prompt = self._get_system_prompt(role)

    def _get_system_prompt(self, role: str) -> str:
        """Get system prompt for the role."""
        prompts = {
            "coder": "You are an expert software developer. Write clean, efficient code.",
            "debugger": "You are an expert debugger. Find and fix issues.",
            "tester": "You are an expert in testing. Write comprehensive tests.",
            "reviewer": "You are a code reviewer. Identify issues and suggest improvements.",
            "planner": "You are an expert planner. Create clear, actionable plans.",
            "explainer": "You are an expert teacher. Explain concepts clearly.",
            "explorer": "You are an explorer. Understand and map codebases.",
        }
        return prompts.get(role, prompts.get("coder"))

    async def execute(self) -> str:
        """Execute the agent's task."""
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": self.prompt},
        ]

        # Use model client to get response
        response = ""
        async for chunk in self.model_client.chat_completion(messages, stream=False):
            response = chunk.get("content", "")

        return response


def initialize_orchestration():
    """Initialize the orchestration system for use."""
    adapter = OrchestrationAdapter()
    adapter.initialize()
    return adapter
