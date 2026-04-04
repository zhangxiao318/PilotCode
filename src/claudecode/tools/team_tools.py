"""Team management tools for agent teams."""

import uuid
from typing import Any
from dataclasses import dataclass, field
from pydantic import BaseModel, Field

from .base import Tool, ToolResult, ToolUseContext, build_tool
from .registry import register_tool


@dataclass
class Team:
    """Agent team."""
    team_id: str
    name: str
    description: str
    members: list[str] = field(default_factory=list)
    created_at: str = ""


# In-memory team storage
_teams: dict[str, Team] = {}


class TeamCreateInput(BaseModel):
    """Input for TeamCreate tool."""
    name: str = Field(description="Team name")
    description: str | None = Field(default=None, description="Team description")
    members: list[str] = Field(default_factory=list, description="Initial member IDs")


class TeamCreateOutput(BaseModel):
    """Output from TeamCreate tool."""
    team_id: str
    name: str
    member_count: int
    message: str


async def team_create_call(
    input_data: TeamCreateInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any
) -> ToolResult[TeamCreateOutput]:
    """Create a new agent team."""
    from datetime import datetime
    
    team_id = f"team_{uuid.uuid4().hex[:8]}"
    
    team = Team(
        team_id=team_id,
        name=input_data.name,
        description=input_data.description or "",
        members=input_data.members,
        created_at=datetime.now().isoformat()
    )
    
    _teams[team_id] = team
    
    return ToolResult(data=TeamCreateOutput(
        team_id=team_id,
        name=input_data.name,
        member_count=len(input_data.members),
        message=f"Created team '{input_data.name}' with {len(input_data.members)} members"
    ))


class TeamDeleteInput(BaseModel):
    """Input for TeamDelete tool."""
    team_id: str = Field(description="Team ID to delete")


class TeamDeleteOutput(BaseModel):
    """Output from TeamDelete tool."""
    team_id: str
    name: str
    message: str


async def team_delete_call(
    input_data: TeamDeleteInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any
) -> ToolResult[TeamDeleteOutput]:
    """Delete an agent team."""
    if input_data.team_id not in _teams:
        return ToolResult(
            data=TeamDeleteOutput(team_id=input_data.team_id, name="", message=""),
            error=f"Team not found: {input_data.team_id}"
        )
    
    team = _teams.pop(input_data.team_id)
    
    return ToolResult(data=TeamDeleteOutput(
        team_id=input_data.team_id,
        name=team.name,
        message=f"Deleted team: {team.name}"
    ))


class TeamAddMemberInput(BaseModel):
    """Input for TeamAddMember tool."""
    team_id: str = Field(description="Team ID")
    member_id: str = Field(description="Member ID to add")


class TeamAddMemberOutput(BaseModel):
    """Output from TeamAddMember tool."""
    team_id: str
    member_id: str
    message: str


async def team_add_member_call(
    input_data: TeamAddMemberInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any
) -> ToolResult[TeamAddMemberOutput]:
    """Add member to team."""
    if input_data.team_id not in _teams:
        return ToolResult(
            data=TeamAddMemberOutput(team_id=input_data.team_id, member_id=input_data.member_id, message=""),
            error=f"Team not found: {input_data.team_id}"
        )
    
    team = _teams[input_data.team_id]
    
    if input_data.member_id in team.members:
        return ToolResult(
            data=TeamAddMemberOutput(team_id=input_data.team_id, member_id=input_data.member_id, message=""),
            error=f"Member already in team: {input_data.member_id}"
        )
    
    team.members.append(input_data.member_id)
    
    return ToolResult(data=TeamAddMemberOutput(
        team_id=input_data.team_id,
        member_id=input_data.member_id,
        message=f"Added {input_data.member_id} to team {team.name}"
    ))


class TeamListInput(BaseModel):
    """Input for TeamList tool."""
    pass


class TeamInfo(BaseModel):
    """Team information."""
    team_id: str
    name: str
    description: str
    member_count: int


class TeamListOutput(BaseModel):
    """Output from TeamList tool."""
    teams: list[TeamInfo]
    total: int


async def team_list_call(
    input_data: TeamListInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any
) -> ToolResult[TeamListOutput]:
    """List all teams."""
    teams = [
        TeamInfo(
            team_id=t.team_id,
            name=t.name,
            description=t.description,
            member_count=len(t.members)
        )
        for t in _teams.values()
    ]
    
    return ToolResult(data=TeamListOutput(
        teams=teams,
        total=len(teams)
    ))


# Register team tools
TeamCreateTool = build_tool(
    name="TeamCreate",
    description=lambda x, o: f"Create team: {x.name}",
    input_schema=TeamCreateInput,
    output_schema=TeamCreateOutput,
    call=team_create_call,
    aliases=["team_create"],
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: True,
)

TeamDeleteTool = build_tool(
    name="TeamDelete",
    description=lambda x, o: f"Delete team: {x.team_id}",
    input_schema=TeamDeleteInput,
    output_schema=TeamDeleteOutput,
    call=team_delete_call,
    aliases=["team_delete"],
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: True,
)

TeamAddMemberTool = build_tool(
    name="TeamAddMember",
    description=lambda x, o: f"Add {x.member_id} to team {x.team_id}",
    input_schema=TeamAddMemberInput,
    output_schema=TeamAddMemberOutput,
    call=team_add_member_call,
    aliases=["team_add", "add_to_team"],
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: False,
)

TeamListTool = build_tool(
    name="TeamList",
    description=lambda x, o: "List all teams",
    input_schema=TeamListInput,
    output_schema=TeamListOutput,
    call=team_list_call,
    aliases=["teams", "list_teams"],
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
)

register_tool(TeamCreateTool)
register_tool(TeamDeleteTool)
register_tool(TeamAddMemberTool)
register_tool(TeamListTool)
