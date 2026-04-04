"""Agents command implementation."""

from .base import CommandHandler, register_command, CommandContext
from ..tools.agent_tool import AGENT_DEFINITIONS, get_agent_manager


async def agents_command(args: list[str], context: CommandContext) -> str:
    """Handle /agents command."""
    if not args:
        # List available agents
        lines = ["Available agents:", ""]
        
        for name, definition in AGENT_DEFINITIONS.items():
            lines.append(f"  {name}: {definition['description']}")
            lines.append(f"    Tools: {', '.join(definition['allowed_tools'][:5])}...")
        
        # List active agents
        manager = get_agent_manager()
        if manager.agents:
            lines.extend(["", "Active agents:", ""])
            for agent_id, agent in manager.agents.items():
                lines.append(f"  {agent_id}: {agent.definition['name']} ({agent.turns} turns)")
        
        return "\n".join(lines)
    
    action = args[0]
    
    if action == "spawn":
        if len(args) < 2:
            return "Usage: /agents spawn <agent_type> [prompt]"
        
        agent_type = args[1]
        prompt = " ".join(args[2:]) if len(args) > 2 else "Hello"
        
        if agent_type not in AGENT_DEFINITIONS:
            return f"Unknown agent type: {agent_type}"
        
        # Spawn agent
        from ..tools.agent_tool import AgentInput
        
        return f"Spawning {agent_type} agent... (use Task tools to manage)"
    
    else:
        return f"Unknown action: {action}"


register_command(CommandHandler(
    name="agents",
    description="Manage agents",
    handler=agents_command
))
