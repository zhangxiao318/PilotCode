"""Agent Tool for spawning sub-agents."""

import asyncio
import uuid
from typing import Any
from dataclasses import dataclass, field
from pydantic import BaseModel, Field

from .base import Tool, ToolResult, ToolUseContext, build_tool
from .registry import register_tool, get_all_tools


class AgentInput(BaseModel):
    """Input for Agent tool."""
    prompt: str = Field(description="The prompt/task for the sub-agent")
    agent_name: str | None = Field(default=None, description="Specific agent to use")
    context_files: list[str] = Field(default_factory=list, description="Files to include in context")
    max_turns: int = Field(default=10, description="Maximum turns for the sub-agent")


class AgentOutput(BaseModel):
    """Output from Agent tool."""
    result: str
    agent_id: str
    turns_used: int
    tools_used: list[str]


# Agent definitions
AGENT_DEFINITIONS = {
    "coder": {
        "name": "coder",
        "description": "Specialized in writing and editing code",
        "system_prompt": "You are a coding assistant. Focus on writing clean, efficient code.",
        "allowed_tools": ["Bash", "FileRead", "FileWrite", "FileEdit", "Glob", "Grep"]
    },
    "debugger": {
        "name": "debugger",
        "description": "Specialized in debugging and finding issues",
        "system_prompt": "You are a debugging assistant. Focus on finding and fixing bugs.",
        "allowed_tools": ["Bash", "FileRead", "Grep", "LSP"]
    },
    "explainer": {
        "name": "explainer",
        "description": "Specialized in explaining code and concepts",
        "system_prompt": "You are an explainer. Focus on making complex concepts clear.",
        "allowed_tools": ["FileRead", "Grep", "WebSearch"]
    },
    "tester": {
        "name": "tester",
        "description": "Specialized in writing tests",
        "system_prompt": "You are a testing assistant. Focus on writing comprehensive tests.",
        "allowed_tools": ["Bash", "FileRead", "FileWrite", "FileEdit"]
    }
}


@dataclass
class SubAgent:
    """Sub-agent instance."""
    agent_id: str
    definition: dict
    messages: list = field(default_factory=list)
    tools_used: list = field(default_factory=list)
    turns: int = 0


class AgentManager:
    """Manager for sub-agents."""
    
    def __init__(self):
        self.agents: dict[str, SubAgent] = {}
    
    def create_agent(self, agent_name: str | None = None) -> SubAgent:
        """Create a new sub-agent."""
        agent_id = str(uuid.uuid4())[:8]
        
        if agent_name and agent_name in AGENT_DEFINITIONS:
            definition = AGENT_DEFINITIONS[agent_name]
        else:
            # Default to coder
            definition = AGENT_DEFINITIONS["coder"]
        
        agent = SubAgent(
            agent_id=agent_id,
            definition=definition
        )
        
        self.agents[agent_id] = agent
        return agent
    
    async def run_agent(
        self,
        agent: SubAgent,
        prompt: str,
        max_turns: int = 10
    ) -> str:
        """Run sub-agent with prompt."""
        from ..utils.model_client import get_model_client, Message
        
        client = get_model_client()
        
        # Build messages
        messages = [
            Message(role="system", content=agent.definition["system_prompt"]),
            Message(role="user", content=prompt)
        ]
        
        result_parts = []
        
        for turn in range(max_turns):
            agent.turns += 1
            
            # Get response from model
            response_chunks = []
            async for chunk in client.chat_completion(messages=messages, stream=False):
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                if delta.get("content"):
                    response_chunks.append(delta["content"])
            
            response = "".join(response_chunks)
            result_parts.append(f"Turn {turn + 1}:\n{response}")
            
            # Check if agent is done
            if "<complete>" in response or "<done>" in response:
                break
            
            # Add assistant message
            messages.append(Message(role="assistant", content=response))
            
            # In real implementation, would parse tool calls and execute them
            # For now, simulate completion
            break
        
        return "\n\n".join(result_parts)
    
    def get_agent(self, agent_id: str) -> SubAgent | None:
        """Get agent by ID."""
        return self.agents.get(agent_id)


# Global agent manager
_agent_manager: AgentManager | None = None


def get_agent_manager() -> AgentManager:
    """Get global agent manager."""
    global _agent_manager
    if _agent_manager is None:
        _agent_manager = AgentManager()
    return _agent_manager


async def agent_call(
    input_data: AgentInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any
) -> ToolResult[AgentOutput]:
    """Execute agent tool."""
    manager = get_agent_manager()
    
    # Create agent
    agent = manager.create_agent(input_data.agent_name)
    
    # Build context
    context_parts = [input_data.prompt]
    
    if input_data.context_files:
        context_parts.append("\nContext files:")
        for file_path in input_data.context_files:
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                context_parts.append(f"\n--- {file_path} ---\n{content[:2000]}")
            except Exception as e:
                context_parts.append(f"\n--- {file_path} ---\nError reading: {e}")
    
    full_prompt = "\n".join(context_parts)
    
    try:
        # Run agent
        result = await manager.run_agent(
            agent,
            full_prompt,
            max_turns=input_data.max_turns
        )
        
        return ToolResult(data=AgentOutput(
            result=result,
            agent_id=agent.agent_id,
            turns_used=agent.turns,
            tools_used=agent.tools_used
        ))
    except Exception as e:
        return ToolResult(
            data=AgentOutput(
                result="",
                agent_id=agent.agent_id,
                turns_used=0,
                tools_used=[]
            ),
            error=str(e)
        )


async def agent_description(input_data: AgentInput, options: dict[str, Any]) -> str:
    """Get description for agent tool."""
    agent = input_data.agent_name or "default"
    return f"Spawning {agent} agent: {input_data.prompt[:50]}..."


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
