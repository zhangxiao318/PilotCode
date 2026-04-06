"""Skill tool for executing skills."""

import os
import json
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from .base import Tool, ToolResult, ToolUseContext, build_tool
from .registry import register_tool

SKILLS_DIR = Path.home() / ".local" / "share" / "pilotcode" / "skills"


class SkillInput(BaseModel):
    """Input for Skill tool."""

    skill_name: str = Field(description="Name of the skill to execute")
    action: str = Field(default="run", description="Action: run, info, list")
    args: dict = Field(default_factory=dict, description="Arguments for the skill")


class SkillOutput(BaseModel):
    """Output from Skill tool."""

    skill_name: str
    action: str
    result: str
    success: bool


def load_skill_config(skill_name: str) -> dict | None:
    """Load skill configuration."""
    skill_path = SKILLS_DIR / skill_name / "skill.json"

    if not skill_path.exists():
        return None

    try:
        with open(skill_path, "r") as f:
            return json.load(f)
    except:
        return None


async def skill_call(
    input_data: SkillInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[SkillOutput]:
    """Execute a skill."""

    if input_data.action == "list":
        # List available skills
        if not SKILLS_DIR.exists():
            return ToolResult(
                data=SkillOutput(
                    skill_name="", action="list", result="No skills directory found", success=True
                )
            )

        skills = []
        for item in SKILLS_DIR.iterdir():
            if item.is_dir():
                config = load_skill_config(item.name)
                if config:
                    skills.append(f"{item.name}: {config.get('description', 'No description')}")

        return ToolResult(
            data=SkillOutput(
                skill_name="",
                action="list",
                result="\n".join(skills) if skills else "No skills installed",
                success=True,
            )
        )

    elif input_data.action == "info":
        # Show skill info
        config = load_skill_config(input_data.skill_name)

        if not config:
            return ToolResult(
                data=SkillOutput(
                    skill_name=input_data.skill_name, action="info", result="", success=False
                ),
                error=f"Skill not found: {input_data.skill_name}",
            )

        info = f"""Skill: {config.get('name', input_data.skill_name)}
Version: {config.get('version', 'unknown')}
Description: {config.get('description', 'No description')}
Author: {config.get('author', 'unknown')}
"""

        return ToolResult(
            data=SkillOutput(
                skill_name=input_data.skill_name, action="info", result=info, success=True
            )
        )

    elif input_data.action == "run":
        # Run the skill
        config = load_skill_config(input_data.skill_name)

        if not config:
            return ToolResult(
                data=SkillOutput(
                    skill_name=input_data.skill_name, action="run", result="", success=False
                ),
                error=f"Skill not found: {input_data.skill_name}",
            )

        # Check for run command
        run_cmd = config.get("run")
        if not run_cmd:
            return ToolResult(
                data=SkillOutput(
                    skill_name=input_data.skill_name, action="run", result="", success=False
                ),
                error=f"Skill has no run command: {input_data.skill_name}",
            )

        # Execute skill (simplified - would actually run the command)
        return ToolResult(
            data=SkillOutput(
                skill_name=input_data.skill_name,
                action="run",
                result=f"Would execute: {run_cmd} with args {input_data.args}",
                success=True,
            )
        )

    else:
        return ToolResult(
            data=SkillOutput(
                skill_name=input_data.skill_name, action=input_data.action, result="", success=False
            ),
            error=f"Unknown action: {input_data.action}",
        )


SkillTool = build_tool(
    name="Skill",
    description=lambda x, o: f"Skill {x.action}: {x.skill_name}",
    input_schema=SkillInput,
    output_schema=SkillOutput,
    call=skill_call,
    aliases=["skill", "run_skill"],
    is_read_only=lambda x: x.action in ["list", "info"] if x else True,
    is_concurrency_safe=lambda x: x.action in ["list", "info"] if x else True,
)

register_tool(SkillTool)
