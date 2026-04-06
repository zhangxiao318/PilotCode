"""Team management tools - Multi-agent system support."""

from pydantic import Field
from pilotcode.tools.base import Tool, ToolResult
from pilotcode.services.team_manager import get_team_manager, AgentStatus


class TeamCreate(Tool):
    """Create a new team of agents to work on a complex task.

    Teams allow you to spawn multiple agents that can work in parallel on
    different aspects of a problem. Each agent in the team can have a specific
    role and task.
    """

    name: str = Field(..., description="Name of the team (e.g., 'CodeReviewTeam', 'BugHunters')")
    description: str = Field(
        default="", description="Description of what this team will accomplish"
    )

    async def execute(self) -> ToolResult:
        try:
            manager = get_team_manager()
            team = manager.create_team(self.name, self.description)

            return ToolResult(
                success=True,
                message=f"Team '{self.name}' created successfully",
                data={
                    "team_id": team.id,
                    "name": team.name,
                    "description": team.description,
                    "created_at": team.created_at.isoformat(),
                },
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to create team: {str(e)}")


class TeamDelete(Tool):
    """Delete a team and all its agents.

    This permanently removes the team and cancels any running agents.
    """

    team_id: str = Field(..., description="ID of the team to delete")

    async def execute(self) -> ToolResult:
        try:
            manager = get_team_manager()
            if manager.delete_team(self.team_id):
                return ToolResult(
                    success=True, message=f"Team '{self.team_id}' deleted successfully"
                )
            else:
                return ToolResult(success=False, message=f"Team '{self.team_id}' not found")
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to delete team: {str(e)}")


class AgentSpawn(Tool):
    """Spawn a new agent in a team.

    Use this to create specialized agents for specific tasks. Agents can work
    in parallel on different aspects of a problem.

    Example roles:
    - "code_analyzer": Analyze code quality and structure
    - "test_writer": Write unit tests for code
    - "doc_writer": Write documentation
    - "bug_hunter": Find bugs in code
    - "refactorer": Suggest code improvements
    """

    team_id: str = Field(..., description="ID of the team to add the agent to")
    name: str = Field(..., description="Name of the agent (e.g., 'TestBot', 'DocWriter')")
    role: str = Field(..., description="Role of the agent (e.g., 'code_analyzer', 'test_writer')")
    description: str = Field(..., description="What this agent does and its expertise")
    task: str = Field(..., description="Specific task for this agent to complete")

    async def execute(self) -> ToolResult:
        try:
            manager = get_team_manager()
            agent = manager.spawn_agent(
                self.team_id, self.name, self.role, self.description, self.task
            )

            if agent:
                return ToolResult(
                    success=True,
                    message=f"Agent '{self.name}' spawned successfully",
                    data={
                        "agent_id": agent.id,
                        "team_id": self.team_id,
                        "name": agent.name,
                        "role": agent.role,
                        "status": agent.status.value,
                    },
                )
            else:
                return ToolResult(
                    success=False,
                    message=f"Failed to spawn agent - team '{self.team_id}' not found",
                )
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to spawn agent: {str(e)}")


class TeamList(Tool):
    """List all teams and their status."""

    async def execute(self) -> ToolResult:
        try:
            manager = get_team_manager()
            teams = manager.list_teams()

            if not teams:
                return ToolResult(success=True, message="No teams found", data={"teams": []})

            team_data = [t.to_dict() for t in teams]

            return ToolResult(
                success=True, message=f"Found {len(teams)} team(s)", data={"teams": team_data}
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to list teams: {str(e)}")


class TeamStatus(Tool):
    """Get detailed status of a team and its agents."""

    team_id: str = Field(..., description="ID of the team to check status for")

    async def execute(self) -> ToolResult:
        try:
            manager = get_team_manager()
            summary = manager.get_team_summary(self.team_id)

            if summary:
                return ToolResult(
                    success=True, message=f"Team '{self.team_id}' status retrieved", data=summary
                )
            else:
                return ToolResult(success=False, message=f"Team '{self.team_id}' not found")
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to get team status: {str(e)}")


class AgentCancel(Tool):
    """Cancel a running agent."""

    agent_id: str = Field(..., description="ID of the agent to cancel")

    async def execute(self) -> ToolResult:
        try:
            manager = get_team_manager()
            if manager.cancel_agent(self.agent_id):
                return ToolResult(success=True, message=f"Agent '{self.agent_id}' cancelled")
            else:
                return ToolResult(
                    success=False, message=f"Agent '{self.agent_id}' not found or not running"
                )
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to cancel agent: {str(e)}")


class ShareContext(Tool):
    """Share context or data across all agents in a team.

    This allows agents to share intermediate results, configuration,
    or any other data that multiple agents need access to.
    """

    team_id: str = Field(..., description="ID of the team")
    key: str = Field(..., description="Key for the shared data")
    value: str = Field(..., description="Value to share (use JSON for complex data)")

    async def execute(self) -> ToolResult:
        try:
            manager = get_team_manager()
            if manager.share_context(self.team_id, self.key, self.value):
                return ToolResult(
                    success=True,
                    message=f"Context shared in team '{self.team_id}'",
                    data={"key": self.key, "team_id": self.team_id},
                )
            else:
                return ToolResult(success=False, message=f"Team '{self.team_id}' not found")
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to share context: {str(e)}")


# Tool registry for team tools
TEAM_TOOLS = [
    TeamCreate,
    TeamDelete,
    AgentSpawn,
    TeamList,
    TeamStatus,
    AgentCancel,
    ShareContext,
]
