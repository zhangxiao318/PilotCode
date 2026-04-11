"""Advanced Agent tool with ClaudeCode-style decomposition.

This tool provides the full ClaudeCode agent experience with:
- Automatic task decomposition
- Multi-strategy execution
- Progress tracking
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from ..orchestration.coordinator import AgentCoordinator
from ..orchestration.integration import initialize_orchestration
from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class AdvancedAgentInput(BaseModel):
    """Input for the advanced Agent tool."""

    description: str = Field(description="Brief description of what to do")
    task: str = Field(description="The full task with all context")
    strategy: Optional[str] = Field(
        default=None, description="Execution strategy: auto, sequential, parallel, hierarchical"
    )
    context: dict = Field(default_factory=dict, description="Additional context")
    decompose: bool = Field(default=True, description="Whether to automatically decompose the task")


class AdvancedAgentOutput(BaseModel):
    """Output from the advanced Agent tool."""

    workflow_id: str
    status: str
    result: str
    strategy_used: str
    subtask_count: int
    execution_time_seconds: float


class AdvancedAgentTool:
    """Advanced agent tool with full orchestration support."""

    def __init__(self):
        self.adapter = None
        self.coordinator: Optional[AgentCoordinator] = None

    def initialize(self):
        """Initialize the tool."""
        if self.adapter is None:
            self.adapter = initialize_orchestration()
            self.coordinator = self.adapter.coordinator

    async def execute(
        self,
        input_data: AdvancedAgentInput,
        context: ToolUseContext,
        can_use_tool: Any,
        parent_message: Any,
        on_progress: Any,
    ) -> ToolResult[AdvancedAgentOutput]:
        """Execute the advanced agent tool."""
        self.initialize()

        # Progress tracking
        def progress_callback(event: str, data: dict):
            if on_progress:
                on_progress({"event": event, **data})

        if self.coordinator:
            self.coordinator.on_progress(progress_callback)

        # Determine strategy
        strategy = input_data.strategy
        if strategy == "auto":
            strategy = None

        # Execute with orchestration
        result = await self.adapter.execute_task(
            task=input_data.task, context=input_data.context, auto_decompose=input_data.decompose
        )

        return ToolResult(
            data=AdvancedAgentOutput(
                workflow_id=result["workflow_id"],
                status=result["status"],
                result=result["summary"],
                strategy_used=result["metadata"].get("strategy", "none"),
                subtask_count=result["metadata"].get("subtask_count", 0),
                execution_time_seconds=result["duration_seconds"],
            )
        )


# Global tool instance
_tool_instance = AdvancedAgentTool()


async def advanced_agent_call(
    input_data: AdvancedAgentInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[AdvancedAgentOutput]:
    """Entry point for the advanced agent tool."""
    return await _tool_instance.execute(
        input_data, context, can_use_tool, parent_message, on_progress
    )


# Create and register the tool
AdvancedAgentToolDef = build_tool(
    name="AdvancedAgent",
    description=lambda x, o: f"🤖 Advanced agent: {x.description[:50]}...",
    input_schema=AdvancedAgentInput,
    output_schema=AdvancedAgentOutput,
    call=advanced_agent_call,
    aliases=["adv_agent", "smart_agent"],
    search_hint="Create an intelligent agent that automatically decomposes and executes tasks",
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: False,
)

register_tool(AdvancedAgentToolDef)
