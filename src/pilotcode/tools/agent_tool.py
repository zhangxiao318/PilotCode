"""Agent Tool for spawning sub-agents."""

from typing import Any
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool
from ..agent import get_agent_manager, AgentStatus, ENHANCED_AGENT_DEFINITIONS


class AgentInput(BaseModel):
    """Input for Agent tool."""
    description: str = Field(description="Brief description of the task")
    prompt: str = Field(description="The full prompt/task for the sub-agent")
    subagent_type: str | None = Field(default=None, description="Agent type: coder, debugger, explainer, tester, reviewer, planner, explorer")
    name: str | None = Field(default=None, description="Custom name for the agent")
    model: str | None = Field(default=None, description="Model to use")
    context_files: list[str] = Field(default_factory=list, description="Files to include in context")
    max_turns: int = Field(default=10, description="Maximum turns for the sub-agent")


class AgentOutput(BaseModel):
    """Output from Agent tool."""
    result: str
    agent_id: str
    turns_used: int
    tools_used: list[str]


async def agent_call(
    input_data: AgentInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any
) -> ToolResult[AgentOutput]:
    """Execute agent tool using enhanced agent manager."""
    from ..agent.agent_orchestrator import get_orchestrator
    from ..hooks import get_hook_manager
    
    manager = get_agent_manager()
    hook_manager = get_hook_manager()
    
    # Create agent using enhanced manager
    agent = manager.create_agent(
        agent_type=input_data.subagent_type,
        name=input_data.name,
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
    
    # Build context with files
    context_parts = [modified_prompt]
    
    if input_data.context_files:
        context_parts.append("\n\nContext files:")
        for file_path in input_data.context_files:
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                context_parts.append(f"\n--- {file_path} ---\n{content[:2000]}")
            except Exception as e:
                context_parts.append(f"\n--- {file_path} ---\nError reading: {e}")
    
    full_prompt = "\n".join(context_parts)
    
    # Set agent running
    manager.set_agent_status(agent.agent_id, AgentStatus.RUNNING)
    
    try:
        # Use orchestrator to run agent
        orchestrator = get_orchestrator()
        result = await orchestrator._run_agent_task(agent, full_prompt)
        
        # Update agent
        agent.output = result
        agent.turns += 1
        manager.set_agent_status(agent.agent_id, AgentStatus.COMPLETED)
        
        # Call post-agent-run hooks
        await hook_manager.on_post_agent_run(agent.agent_id, result)
        
        return ToolResult(data=AgentOutput(
            result=result,
            agent_id=agent.agent_id,
            turns_used=agent.turns,
            tools_used=agent.tools_used,
        ))
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
    return f"Spawning {agent_type} agent: {input_data.description or input_data.prompt[:50]}..."


# Create the Agent tool
AgentTool = build_tool(
    name="Agent",
    description=agent_description,
    input_schema=AgentInput,
    output_schema=AgentOutput,
    call=agent_call,
    aliases=["agent", "subagent", "spawn"],
    search_hint="Spawn a sub-agent to work on a task",
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: False,
)

register_tool(AgentTool)


# Export available agent types
AGENT_TYPES = list(ENHANCED_AGENT_DEFINITIONS.keys())
