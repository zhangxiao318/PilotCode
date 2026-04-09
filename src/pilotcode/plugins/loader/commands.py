"""Command loader for plugin commands.

Commands are similar to skills but typically define slash commands.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .skills import load_skill_from_file, SkillLoadError
from ..core.types import SkillDefinition


class CommandLoader:
    """Loader for plugin commands."""
    
    def __init__(self, commands_path: Path):
        self.commands_path = Path(commands_path)
        self._commands: dict[str, SkillDefinition] = {}
    
    def load_all(self) -> list[SkillDefinition]:
        """Load all commands from the directory.
        
        Returns:
            List of loaded commands
        """
        if not self.commands_path.exists():
            return []
        
        commands = []
        
        # Load individual .md files
        for md_file in self.commands_path.glob("*.md"):
            try:
                cmd = load_skill_from_file(md_file)
                # Commands use their filename as the command name if not specified
                if not cmd.name:
                    cmd.name = md_file.stem
                self._commands[cmd.name] = cmd
                commands.append(cmd)
            except SkillLoadError as e:
                print(f"Warning: Failed to load command {md_file}: {e}")
        
        return commands
    
    def get_command(self, name: str) -> Optional[SkillDefinition]:
        """Get a loaded command by name."""
        return self._commands.get(name)
    
    def list_commands(self) -> list[str]:
        """List names of all loaded commands."""
        return list(self._commands.keys())
