"""Skill tool for executing skills.

Supports both legacy skill.json format and new plugin-based Markdown skills.
"""

import json
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool

SKILLS_DIR = Path.home() / ".local" / "share" / "pilotcode" / "skills"

# Dynamic skills registry for plugin-provided skills
_dynamic_skills: dict[str, dict] = {}


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


def register_dynamic_skill(
    name: str,
    description: str,
    content: str,
    allowed_tools: list[str] = None,
    source: str = "plugin",
) -> None:
    """Register a dynamic skill from a plugin.

    Args:
        name: Skill name
        description: Skill description
        content: The skill prompt content
        allowed_tools: List of allowed tools
        source: Plugin source identifier
    """
    _dynamic_skills[name] = {
        "name": name,
        "description": description,
        "content": content,
        "allowedTools": allowed_tools or [],
        "source": source,
        "version": "plugin",
        "author": source,
    }


def load_skill_config(skill_name: str) -> dict | None:
    """Load skill configuration."""
    # Check dynamic skills first
    if skill_name in _dynamic_skills:
        return _dynamic_skills[skill_name]

    # Fall back to legacy skill.json
    skill_path = SKILLS_DIR / skill_name / "skill.json"

    if not skill_path.exists():
        return None

    try:
        with open(skill_path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def _list_all_skills() -> list[str]:
    """List all available skills (legacy + dynamic)."""
    skills = []

    # Add dynamic skills
    for name in _dynamic_skills:
        skills.append(name)

    # Add legacy skills
    if SKILLS_DIR.exists():
        for item in SKILLS_DIR.iterdir():
            if item.is_dir():
                config = load_skill_config(item.name)
                if config and item.name not in skills:
                    skills.append(item.name)

    return sorted(skills)


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
        skills = _list_all_skills()

        skill_list = []
        for skill_name in skills:
            config = load_skill_config(skill_name)
            if config:
                desc = config.get("description", "No description")
                source = config.get("source", "legacy")
                skill_list.append(f"{skill_name}: {desc} [{source}]")

        return ToolResult(
            data=SkillOutput(
                skill_name="",
                action="list",
                result="\n".join(skill_list) if skill_list else "No skills installed",
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

        # For dynamic skills, show the content preview
        content_preview = ""
        if config.get("version") == "plugin" and "content" in config:
            content = config["content"]
            content_preview = (
                f"\nContent Preview:\n{content[:500]}..."
                if len(content) > 500
                else f"\nContent:\n{content}"
            )

        info = f"""Skill: {config.get("name", input_data.skill_name)}
Version: {config.get("version", "unknown")}
Description: {config.get("description", "No description")}
Author: {config.get("author", "unknown")}
Source: {config.get("source", "legacy")}
Allowed Tools: {", ".join(config.get("allowedTools", [])) if config.get("allowedTools") else "None specified"}{content_preview}
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

        # For plugin-based skills with content
        if "content" in config:
            skill_content = config["content"]

            # Simple argument substitution
            for key, value in input_data.args.items():
                skill_content = skill_content.replace(f"{{{key}}}", str(value))

            return ToolResult(
                data=SkillOutput(
                    skill_name=input_data.skill_name,
                    action="run",
                    result=skill_content,
                    success=True,
                )
            )

        # Legacy skill with run command
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
