"""Skill command implementation."""

import os
import json
from pathlib import Path
from .base import CommandHandler, register_command, CommandContext


SKILLS_DIR = os.path.expanduser("~/.local/share/pilotcode/skills")


def ensure_skills_dir():
    """Ensure skills directory exists."""
    os.makedirs(SKILLS_DIR, exist_ok=True)


async def skills_command(args: list[str], context: CommandContext) -> str:
    """Handle /skills command."""
    ensure_skills_dir()
    
    if not args:
        # List skills
        skills = []
        for item in os.listdir(SKILLS_DIR):
            skill_path = Path(SKILLS_DIR) / item
            if skill_path.is_dir():
                skills.append(item)
        
        if not skills:
            return "No skills installed. Use '/skills create <name>' to create one."
        
        lines = ["Installed skills:", ""]
        for skill in sorted(skills):
            lines.append(f"  • {skill}")
        
        return "\n".join(lines)
    
    action = args[0]
    
    if action == "create":
        if len(args) < 2:
            return "Usage: /skills create <name>"
        
        name = args[1]
        skill_path = Path(SKILLS_DIR) / name
        skill_path.mkdir(parents=True, exist_ok=True)
        
        # Create skill.json
        skill_config = {
            "name": name,
            "version": "1.0.0",
            "description": f"Custom skill: {name}",
            "commands": []
        }
        
        with open(skill_path / "skill.json", 'w') as f:
            json.dump(skill_config, f, indent=2)
        
        return f"Created skill: {name}\nLocation: {skill_path}"
    
    elif action == "info":
        if len(args) < 2:
            return "Usage: /skills info <name>"
        
        name = args[1]
        skill_path = Path(SKILLS_DIR) / name / "skill.json"
        
        if not skill_path.exists():
            return f"Skill not found: {name}"
        
        with open(skill_path, 'r') as f:
            config = json.load(f)
        
        lines = [
            f"Skill: {config.get('name', name)}",
            f"Version: {config.get('version', 'unknown')}",
            f"Description: {config.get('description', 'No description')}",
        ]
        
        return "\n".join(lines)
    
    elif action == "delete":
        if len(args) < 2:
            return "Usage: /skills delete <name>"
        
        name = args[1]
        skill_path = Path(SKILLS_DIR) / name
        
        if not skill_path.exists():
            return f"Skill not found: {name}"
        
        import shutil
        shutil.rmtree(skill_path)
        return f"Deleted skill: {name}"
    
    else:
        return f"Unknown action: {action}. Use: create, info, delete"


register_command(CommandHandler(
    name="skills",
    description="Manage skills",
    handler=skills_command
))
