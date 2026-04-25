"""Advanced Agent tool with unified P-EVR orchestration.

This tool provides structured task execution through the unified MissionAdapter.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from ..orchestration.integration import initialize_orchestration
from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class AdvancedAgentInput(BaseModel):
    """Input for the advanced Agent tool."""

    description: str = Field(description="Brief description of what to do")
    task: str = Field(description="The full task with all context")
    strategy: Optional[str] = Field(
        default=None, description="Execution strategy hint (deprecated, kept for compatibility)"
    )
    context: dict = Field(default_factory=dict, description="Additional context")
    decompose: bool = Field(default=True, description="Whether to use structured planning")


class AdvancedAgentOutput(BaseModel):
    """Output from the advanced Agent tool."""

    mission_id: str = ""
    status: str = ""
    result: str = ""
    success: bool = False


class AdvancedAgentTool:
    """Advanced agent tool with unified orchestration support."""

    def __init__(self):
        self.adapter = None

    def initialize(self):
        """Initialize the tool."""
        if self.adapter is None:
            self.adapter = initialize_orchestration()

    async def execute(
        self,
        input_data: AdvancedAgentInput,
        context: ToolUseContext,
    ) -> ToolResult[AdvancedAgentOutput]:
        """Execute the advanced agent tool."""
        self.initialize()

        try:
            result = await self.adapter.execute_task(
                task=input_data.task,
                context=input_data.context,
                explore_first=input_data.decompose,
            )

            success = result.get("success", False)
            output = AdvancedAgentOutput(
                mission_id=result.get("mission_id", ""),
                status="completed" if success else "failed",
                result=(
                    result.get("error", "") if not success else str(result.get("task_outputs", {}))
                ),
                success=success,
            )
            return ToolResult(data=output)
        except Exception as e:
            output = AdvancedAgentOutput(
                status="error",
                result=str(e),
                success=False,
            )
            return ToolResult(data=output, error=str(e))


# Build and register the tool
_tool_instance = AdvancedAgentTool()


async def advanced_agent_call(
    input_data: AdvancedAgentInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[AdvancedAgentOutput]:
    """Call the advanced agent tool."""
    return await _tool_instance.execute(input_data, context)


AdvancedAgentToolDef = build_tool(
    name="AdvancedAgent",
    description="Execute complex tasks using unified P-EVR orchestration with automatic planning.",
    input_schema=AdvancedAgentInput,
    call=advanced_agent_call,
    output_schema=AdvancedAgentOutput,
)
register_tool(AdvancedAgentToolDef)
