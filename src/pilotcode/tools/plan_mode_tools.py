"""Plan mode tools for structured task planning."""

from typing import Any
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class PlanModeState:
    """Session-scoped plan mode state."""

    is_active: bool = False
    current_plan: list[dict] = []
    completed_steps: list[int] = []


_plan_states: dict[str, PlanModeState] = {}


def get_plan_state(session_id: str = "") -> PlanModeState:
    """Get plan state for a session, creating one if needed."""
    if not session_id:
        session_id = "_default"
    if session_id not in _plan_states:
        _plan_states[session_id] = PlanModeState()
    return _plan_states[session_id]


class EnterPlanModeInput(BaseModel):
    """Input for EnterPlanMode tool."""

    description: str = Field(description="Plan description")
    steps: list[str] = Field(description="List of plan steps")


class EnterPlanModeOutput(BaseModel):
    """Output from EnterPlanMode tool."""

    plan_id: str
    description: str
    total_steps: int
    message: str


async def enter_plan_mode_call(
    input_data: EnterPlanModeInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[EnterPlanModeOutput]:
    """Enter plan mode."""
    state = get_plan_state()

    state.is_active = True
    state.current_plan = [
        {"step": i + 1, "description": step, "status": "pending"}
        for i, step in enumerate(input_data.steps)
    ]
    state.completed_steps = []

    plan_id = "plan_" + str(id(input_data))[:8]

    return ToolResult(
        data=EnterPlanModeOutput(
            plan_id=plan_id,
            description=input_data.description,
            total_steps=len(input_data.steps),
            message=f"Entered plan mode with {len(input_data.steps)} steps",
        )
    )


class ExitPlanModeInput(BaseModel):
    """Input for ExitPlanMode tool."""

    plan_id: str = Field(description="Plan ID")
    completed: bool = Field(default=True, description="Whether plan was completed")


class ExitPlanModeOutput(BaseModel):
    """Output from ExitPlanMode tool."""

    plan_id: str
    completed: bool
    steps_completed: int
    message: str


async def exit_plan_mode_call(
    input_data: ExitPlanModeInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[ExitPlanModeOutput]:
    """Exit plan mode."""
    state = get_plan_state()

    steps_completed = len(state.completed_steps)
    total_steps = len(state.current_plan)

    state.is_active = False
    state.current_plan = []
    state.completed_steps = []

    return ToolResult(
        data=ExitPlanModeOutput(
            plan_id=input_data.plan_id,
            completed=input_data.completed,
            steps_completed=steps_completed,
            message=f"Exited plan mode. Completed {steps_completed}/{total_steps} steps.",
        )
    )


class UpdatePlanStepInput(BaseModel):
    """Input for updating plan step."""

    plan_id: str = Field(description="Plan ID")
    step_number: int = Field(description="Step number")
    status: str = Field(description="Status: pending, in_progress, completed, failed")
    notes: str | None = Field(default=None, description="Step notes")


class UpdatePlanStepOutput(BaseModel):
    """Output from updating plan step."""

    plan_id: str
    step_number: int
    status: str
    message: str


async def update_plan_step_call(
    input_data: UpdatePlanStepInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[UpdatePlanStepOutput]:
    """Update plan step status."""
    state = get_plan_state()

    if not state.is_active:
        return ToolResult(
            data=UpdatePlanStepOutput(
                plan_id=input_data.plan_id,
                step_number=input_data.step_number,
                status=input_data.status,
                message="",
            ),
            error="Not in plan mode",
        )

    step_idx = input_data.step_number - 1
    if step_idx < 0 or step_idx >= len(state.current_plan):
        return ToolResult(
            data=UpdatePlanStepOutput(
                plan_id=input_data.plan_id,
                step_number=input_data.step_number,
                status=input_data.status,
                message="",
            ),
            error=f"Invalid step number: {input_data.step_number}",
        )

    state.current_plan[step_idx]["status"] = input_data.status
    if input_data.notes:
        state.current_plan[step_idx]["notes"] = input_data.notes

    if input_data.status == "completed" and step_idx not in state.completed_steps:
        state.completed_steps.append(step_idx)

    return ToolResult(
        data=UpdatePlanStepOutput(
            plan_id=input_data.plan_id,
            step_number=input_data.step_number,
            status=input_data.status,
            message=f"Step {input_data.step_number} marked as {input_data.status}",
        )
    )


# ------------------------------------------------------------------
# Unified PlanMode tool (replaces EnterPlanMode/ExitPlanMode/UpdatePlanStep)
# ------------------------------------------------------------------


class PlanModeInput(BaseModel):
    """Input for unified PlanMode tool."""

    action: str = Field(description="Action: enter, exit, update_step")
    description: str | None = Field(default=None, description="For enter: plan description")
    steps: list[str] | None = Field(default=None, description="For enter: list of steps")
    plan_id: str | None = Field(default=None, description="For exit/update: plan ID")
    completed: bool = Field(default=True, description="For exit: whether completed")
    step_number: int | None = Field(default=None, description="For update_step: step number")
    status: str | None = Field(
        default=None, description="For update_step: pending, in_progress, completed, failed"
    )
    notes: str | None = Field(default=None, description="For update_step: step notes")


class PlanModeOutputUnified(BaseModel):
    """Unified output for PlanMode tool."""

    result: dict[str, Any] = Field(default_factory=dict)
    message: str = Field(default="")


async def plan_mode_call(
    input_data: PlanModeInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[PlanModeOutputUnified]:
    """Unified plan mode handler."""
    action = input_data.action

    if action == "enter":
        result = await enter_plan_mode_call(
            EnterPlanModeInput(
                description=input_data.description or "", steps=input_data.steps or []
            ),
            context,
            can_use_tool,
            parent_message,
            on_progress,
        )
        return ToolResult(
            data=PlanModeOutputUnified(
                result=result.data.model_dump() if result.data else {}, message="Plan mode entered"
            ),
            error=result.error,
        )

    elif action == "exit":
        result = await exit_plan_mode_call(
            ExitPlanModeInput(plan_id=input_data.plan_id or "", completed=input_data.completed),
            context,
            can_use_tool,
            parent_message,
            on_progress,
        )
        return ToolResult(
            data=PlanModeOutputUnified(
                result=result.data.model_dump() if result.data else {}, message="Plan mode exited"
            ),
            error=result.error,
        )

    elif action == "update_step":
        if input_data.step_number is None:
            return ToolResult(
                data=PlanModeOutputUnified(), error="step_number required for update_step"
            )
        result = await update_plan_step_call(
            UpdatePlanStepInput(
                plan_id=input_data.plan_id or "",
                step_number=input_data.step_number,
                status=input_data.status or "",
                notes=input_data.notes,
            ),
            context,
            can_use_tool,
            parent_message,
            on_progress,
        )
        return ToolResult(
            data=PlanModeOutputUnified(
                result=result.data.model_dump() if result.data else {}, message="Plan step updated"
            ),
            error=result.error,
        )

    else:
        return ToolResult(data=PlanModeOutputUnified(), error=f"Unknown action: {action}")


PlanModeToolUnified = build_tool(
    name="PlanMode",
    description=lambda x, o: f"PlanMode {x.action}",
    input_schema=PlanModeInput,
    output_schema=PlanModeOutputUnified,
    call=plan_mode_call,
    aliases=["plan_mode", "plan"],
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: True,
)

register_tool(PlanModeToolUnified)

# Old fine-grained tools kept for direct import compatibility only.
EnterPlanModeTool = build_tool(
    name="EnterPlanMode",
    description=lambda x, o: f"Enter plan mode: {x.description[:50]}",
    input_schema=EnterPlanModeInput,
    output_schema=EnterPlanModeOutput,
    call=enter_plan_mode_call,
    aliases=["plan_mode", "start_plan"],
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: True,
)

ExitPlanModeTool = build_tool(
    name="ExitPlanMode",
    description=lambda x, o: f"Exit plan mode {x.plan_id}",
    input_schema=ExitPlanModeInput,
    output_schema=ExitPlanModeOutput,
    call=exit_plan_mode_call,
    aliases=["exit_plan", "end_plan"],
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: True,
)

UpdatePlanStepTool = build_tool(
    name="UpdatePlanStep",
    description=lambda x, o: f"Update step {x.step_number} to {x.status}",
    input_schema=UpdatePlanStepInput,
    output_schema=UpdatePlanStepOutput,
    call=update_plan_step_call,
    aliases=["plan_step", "update_step"],
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: True,
)

# register_tool(EnterPlanModeTool)  # Merged into PlanMode
# register_tool(ExitPlanModeTool)
# register_tool(UpdatePlanStepTool)
