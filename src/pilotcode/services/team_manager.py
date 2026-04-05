"""Multi-agent team management - ClaudeCode-style implementation.

This module provides:
1. Team creation and management
2. Agent spawning with specific roles
3. Inter-agent communication
4. Task delegation
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable
from datetime import datetime
from enum import Enum


class AgentStatus(Enum):
    """Status of an agent."""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class Agent:
    """A sub-agent in the team."""
    id: str
    name: str
    role: str
    description: str
    status: AgentStatus = field(default=AgentStatus.IDLE)
    task: str = ""
    result: str = ""
    error: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    parent_id: str | None = None  # Parent agent that spawned this one
    messages: list[dict] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "status": self.status.value,
            "task": self.task,
            "result": self.result[:500] if self.result else "",
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "parent_id": self.parent_id,
            "message_count": len(self.messages)
        }


@dataclass
class Team:
    """A team of agents."""
    id: str
    name: str
    description: str
    agents: dict[str, Agent] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    shared_context: dict[str, Any] = field(default_factory=dict)
    
    def get_active_agents(self) -> list[Agent]:
        """Get agents that are currently running."""
        return [a for a in self.agents.values() if a.status == AgentStatus.RUNNING]
    
    def get_completed_agents(self) -> list[Agent]:
        """Get agents that have completed."""
        return [a for a in self.agents.values() if a.status == AgentStatus.COMPLETED]
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "agent_count": len(self.agents),
            "active_agents": len(self.get_active_agents()),
            "completed_agents": len(self.get_completed_agents()),
            "created_at": self.created_at.isoformat(),
            "shared_context_keys": list(self.shared_context.keys())
        }


class TeamManager:
    """Manages teams and agents."""
    
    def __init__(self):
        self.teams: dict[str, Team] = {}
        self.agents: dict[str, Agent] = {}  # Global agent registry
        self._agent_callbacks: dict[str, Callable] = {}
    
    def create_team(
        self,
        name: str,
        description: str = "",
        team_id: str | None = None
    ) -> Team:
        """Create a new team."""
        team = Team(
            id=team_id or str(uuid.uuid4())[:8],
            name=name,
            description=description
        )
        self.teams[team.id] = team
        return team
    
    def delete_team(self, team_id: str) -> bool:
        """Delete a team and all its agents."""
        if team_id not in self.teams:
            return False
        
        team = self.teams[team_id]
        # Cancel all running agents
        for agent in team.agents.values():
            if agent.status == AgentStatus.RUNNING:
                agent.status = AgentStatus.CANCELLED
            if agent.id in self.agents:
                del self.agents[agent.id]
        
        del self.teams[team_id]
        return True
    
    def spawn_agent(
        self,
        team_id: str,
        name: str,
        role: str,
        description: str,
        task: str,
        parent_id: str | None = None
    ) -> Agent | None:
        """Spawn a new agent in a team."""
        if team_id not in self.teams:
            return None
        
        team = self.teams[team_id]
        
        agent = Agent(
            id=str(uuid.uuid4())[:8],
            name=name,
            role=role,
            description=description,
            task=task,
            status=AgentStatus.IDLE,
            parent_id=parent_id
        )
        
        team.agents[agent.id] = agent
        self.agents[agent.id] = agent
        
        return agent
    
    async def run_agent(
        self,
        agent_id: str,
        execution_fn: Callable[[Agent], Any] | None = None
    ) -> bool:
        """Run an agent's task."""
        if agent_id not in self.agents:
            return False
        
        agent = self.agents[agent_id]
        
        if agent.status == AgentStatus.RUNNING:
            return False  # Already running
        
        agent.status = AgentStatus.RUNNING
        
        try:
            if execution_fn:
                result = await execution_fn(agent)
                agent.result = str(result)
            else:
                # Default execution - could integrate with query engine
                agent.result = "Task completed (default execution)"
            
            agent.status = AgentStatus.COMPLETED
            agent.completed_at = datetime.now()
            return True
            
        except Exception as e:
            agent.status = AgentStatus.ERROR
            agent.error = str(e)
            return False
    
    def cancel_agent(self, agent_id: str) -> bool:
        """Cancel a running agent."""
        if agent_id not in self.agents:
            return False
        
        agent = self.agents[agent_id]
        if agent.status == AgentStatus.RUNNING:
            agent.status = AgentStatus.CANCELLED
            return True
        return False
    
    def get_agent(self, agent_id: str) -> Agent | None:
        """Get an agent by ID."""
        return self.agents.get(agent_id)
    
    def get_team(self, team_id: str) -> Team | None:
        """Get a team by ID."""
        return self.teams.get(team_id)
    
    def list_teams(self) -> list[Team]:
        """List all teams."""
        return list(self.teams.values())
    
    def list_agents(self, team_id: str | None = None) -> list[Agent]:
        """List agents, optionally filtered by team."""
        if team_id:
            team = self.teams.get(team_id)
            if team:
                return list(team.agents.values())
            return []
        return list(self.agents.values())
    
    def send_message_to_agent(
        self,
        agent_id: str,
        message: str,
        from_agent_id: str | None = None
    ) -> bool:
        """Send a message to an agent."""
        if agent_id not in self.agents:
            return False
        
        agent = self.agents[agent_id]
        agent.messages.append({
            "from": from_agent_id or "system",
            "content": message,
            "timestamp": datetime.now().isoformat()
        })
        return True
    
    def share_context(
        self,
        team_id: str,
        key: str,
        value: Any
    ) -> bool:
        """Share context across a team."""
        if team_id not in self.teams:
            return False
        
        team = self.teams[team_id]
        team.shared_context[key] = value
        return True
    
    def get_shared_context(
        self,
        team_id: str,
        key: str
    ) -> Any | None:
        """Get shared context from a team."""
        team = self.teams.get(team_id)
        if team:
            return team.shared_context.get(key)
        return None
    
    def get_team_summary(self, team_id: str) -> dict | None:
        """Get a summary of team status."""
        team = self.teams.get(team_id)
        if not team:
            return None
        
        return {
            "team": team.to_dict(),
            "agents": [a.to_dict() for a in team.agents.values()],
            "progress": {
                "total": len(team.agents),
                "running": len(team.get_active_agents()),
                "completed": len(team.get_completed_agents()),
                "pending": len([a for a in team.agents.values() if a.status == AgentStatus.IDLE])
            }
        }


# Global instance
_default_team_manager: TeamManager | None = None


def get_team_manager() -> TeamManager:
    """Get global team manager."""
    global _default_team_manager
    if _default_team_manager is None:
        _default_team_manager = TeamManager()
    return _default_team_manager


def create_team(name: str, description: str = "") -> Team:
    """Convenience function to create a team."""
    return get_team_manager().create_team(name, description)


def spawn_agent(
    team_id: str,
    name: str,
    role: str,
    description: str,
    task: str
) -> Agent | None:
    """Convenience function to spawn an agent."""
    return get_team_manager().spawn_agent(
        team_id, name, role, description, task
    )
