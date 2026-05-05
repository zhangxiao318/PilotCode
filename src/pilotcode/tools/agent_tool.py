"""Agent Tool for spawning sub-agents.

Reference: Claude Code src/tools/AgentTool/AgentTool.tsx

Supports:
- Foreground and background (async) execution
- Worktree isolation
- Team/group execution
- Agent memory
- Fork semantics
"""

from typing import Any
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool
from ..agent import (
    get_agent_manager,
    AgentStatus,
    ENHANCED_AGENT_DEFINITIONS,
    load_agent_memory_prompt,
    create_agent_worktree,
    build_worktree_notice,
)


class AgentInput(BaseModel):
    """Input for Agent tool."""

    description: str = Field(description="Brief description of the task (3-5 words)")
    prompt: str = Field(description="The full prompt/task for the sub-agent")
    subagent_type: str | None = Field(
        default=None,
        description="Agent type: coder, debugger, explainer, tester, reviewer, planner, explorer, verifier",
    )
    name: str | None = Field(default=None, description="Custom name for the agent")
    model: str | None = Field(default=None, description="Model to use")
    context_files: list[str] = Field(
        default_factory=list, description="Files to include in context"
    )
    max_turns: int = Field(default=10, description="Maximum turns for the sub-agent")
    run_in_background: bool = Field(
        default=False,
        description="Run as background task. Use when you don't need the result immediately.",
    )
    isolation: str | None = Field(
        default=None,
        description="'worktree' to run in isolated git worktree",
    )
    team_name: str | None = Field(default=None, description="Team name for group execution")


class AgentOutput(BaseModel):
    """Output from Agent tool."""

    result: str
    agent_id: str
    turns_used: int
    tools_used: list[str]
    is_background: bool = False
    worktree_path: str | None = None


async def agent_call(
    input_data: AgentInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[AgentOutput]:
    """Execute agent tool.

    Supports foreground execution (waits for completion) and
    background execution (returns immediately with agent_id).
    """
    from ..agent.agent_orchestrator import get_orchestrator
    from ..hooks import get_hook_manager

    manager = get_agent_manager()
    hook_manager = get_hook_manager()

    # Create agent with team and background support
    agent = manager.create_agent(
        agent_type=input_data.subagent_type,
        name=input_data.name,
        is_background=input_data.run_in_background,
        team_name=input_data.team_name,
    )

    # Set model if specified
    if input_data.model:
        agent.definition.model = input_data.model

    # Update max turns
    agent.max_turns = input_data.max_turns

    # Call pre-agent-run hooks
    should_run, modified_prompt = await hook_manager.on_pre_agent_run(
        agent.agent_id,
        input_data.prompt,
    )

    if not should_run:
        return ToolResult(
            data=AgentOutput(
                result="",
                agent_id=agent.agent_id,
                turns_used=0,
                tools_used=[],
            ),
            error="Agent execution denied by hook",
        )

    # Build prompt with context files
    context_parts = [modified_prompt]

    if input_data.context_files:
        context_parts.append("\n\nContext files:")
        for file_path in input_data.context_files:
            try:
                with open(file_path, "r") as f:
                    content = f.read()
                context_parts.append(f"\n--- {file_path} ---\n{content[:2000]}")
            except Exception as e:
                context_parts.append(f"\n--- {file_path} ---\nError reading: {e}")

    # Inject agent memory if available
    if agent.definition.memory_scope:
        memory = load_agent_memory_prompt(
            agent.definition.name,
            agent.definition.memory_scope,
        )
        if memory:
            context_parts.append(f"\n{memory}")

    # Worktree isolation
    worktree_info = None
    if input_data.isolation == "worktree":
        slug = f"agent-{agent.agent_id}"
        worktree_info = create_agent_worktree(slug)
        if worktree_info:
            agent.worktree_path = worktree_info["worktree_path"]
            agent.worktree_branch = worktree_info["branch"]
            notice = build_worktree_notice(
                worktree_info["worktree_path"],
                worktree_info["branch"],
            )
            context_parts.append(f"\n{notice}")

    full_prompt = "\n".join(context_parts)

    # Background execution
    if input_data.run_in_background:
        manager.set_agent_status(agent.agent_id, AgentStatus.RUNNING)

        async def _run_background():
            orchestrator = get_orchestrator()
            result = await orchestrator._run_agent_task(agent, full_prompt)
            agent.output = result
            agent.turns += 1
            manager.set_agent_status(agent.agent_id, AgentStatus.COMPLETED)
            await hook_manager.on_post_agent_run(agent.agent_id, result)
            return result

        manager.run_agent_background(agent.agent_id, _run_background)
        manager.set_agent_status(agent.agent_id, AgentStatus.RUNNING)

        return ToolResult(
            data=AgentOutput(
                result=f"Agent {agent.agent_id} ({agent.definition.name}) started in background",
                agent_id=agent.agent_id,
                turns_used=0,
                tools_used=[],
                is_background=True,
                worktree_path=agent.worktree_path,
            )
        )

    # Foreground execution
    manager.set_agent_status(agent.agent_id, AgentStatus.RUNNING)

    try:
        orchestrator = get_orchestrator()
        result = await orchestrator._run_agent_task(agent, full_prompt)

        agent.output = result
        agent.turns += 1
        manager.set_agent_status(agent.agent_id, AgentStatus.COMPLETED)
        await hook_manager.on_post_agent_run(agent.agent_id, result)

        return ToolResult(
            data=AgentOutput(
                result=result,
                agent_id=agent.agent_id,
                turns_used=agent.turns,
                tools_used=agent.tools_used,
                worktree_path=agent.worktree_path,
            )
        )
    except Exception as e:
        manager.set_agent_status(agent.agent_id, AgentStatus.FAILED)
        await hook_manager.on_error(e, agent_id=agent.agent_id)

        return ToolResult(
            data=AgentOutput(
                result="",
                agent_id=agent.agent_id,
                turns_used=agent.turns,
                tools_used=agent.tools_used,
            ),
            error=str(e),
        )


async def agent_description(input_data: AgentInput, options: dict[str, Any]) -> str:
    """Get description for agent tool."""
    agent_type = input_data.subagent_type or input_data.name or "default"
    mode = " (background)" if input_data.run_in_background else ""
    return (
        f"Spawning {agent_type} agent{mode}: {input_data.description or input_data.prompt[:50]}..."
    )


# Create the Agent tool
AgentTool = build_tool(
    name="Agent",
    description=agent_description,
    input_schema=AgentInput,
    output_schema=AgentOutput,
    call=agent_call,
    aliases=["agent", "subagent", "spawn", "fork"],
    search_hint="Spawn a sub-agent to work on a task, optionally in background or worktree isolation",
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: False,
)

register_tool(AgentTool)


# Export available agent types
AGENT_TYPES = list(ENHANCED_AGENT_DEFINITIONS.keys())
