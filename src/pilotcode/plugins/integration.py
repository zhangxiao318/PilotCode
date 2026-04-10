"""Integration with PilotCode's tool and command systems.

This module integrates plugins with the existing PilotCode infrastructure:
- Registers plugin skills with the Skill tool
- Registers plugin commands with the command system
- Sets up MCP servers from plugins
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .core.manager import PluginManager
    from .core.types import LoadedPlugin, SkillDefinition

from .loader.skills import SkillLoader
from .loader.commands import CommandLoader


class PluginIntegration:
    """Integrates plugins with PilotCode systems."""

    def __init__(self, manager: PluginManager):
        self.manager = manager
        self._skill_loaders: list[SkillLoader] = []
        self._command_loaders: list[CommandLoader] = []
        self._mcp_servers: dict[str, Any] = {}

    async def initialize(self) -> None:
        """Initialize integration by loading all enabled plugins."""
        result = await self.manager.load_plugins()

        for plugin in result.enabled:
            await self.load_plugin(plugin)

        if result.errors:
            for error in result.errors:
                print(f"Plugin error: {error}")

    async def load_plugin(self, plugin: LoadedPlugin) -> None:
        """Load a plugin's components."""
        # Load skills
        if plugin.skills_path and plugin.skills_path.exists():
            loader = SkillLoader(plugin.skills_path)
            skills = loader.load_all()
            self._skill_loaders.append(loader)

            # Register with skill tool
            await self._register_skills(skills, plugin)

        # Load commands
        if plugin.commands_path and plugin.commands_path.exists():
            loader = CommandLoader(plugin.commands_path)
            commands = loader.load_all()
            self._command_loaders.append(loader)

            # Register with command system
            await self._register_commands(commands, plugin)

        # Start MCP servers
        if plugin.mcp_servers:
            await self._start_mcp_servers(plugin.mcp_servers, plugin)

    async def _register_skills(self, skills: list[SkillDefinition], plugin: LoadedPlugin) -> None:
        """Register skills with the Skill tool."""
        try:
            # Import here to avoid circular imports
            from ..tools.skill_tool import register_dynamic_skill

            for skill in skills:
                register_dynamic_skill(
                    name=skill.name,
                    description=skill.description,
                    content=skill.content,
                    allowed_tools=skill.allowed_tools,
                    source=f"{plugin.manifest.name}@{plugin.source}",
                )
        except ImportError:
            # Skill tool not available
            pass

    async def _register_commands(
        self, commands: list[SkillDefinition], plugin: LoadedPlugin
    ) -> None:
        """Register commands with the command system."""
        try:
            from ..commands.base import CommandHandler, register_command

            for cmd in commands:

                async def handler(args, context, content=cmd.content):
                    # Return the command content as the response
                    # In a real implementation, this might process arguments
                    return content

                register_command(
                    CommandHandler(
                        name=f"plugin:{cmd.name}", description=cmd.description, handler=handler
                    )
                )
        except ImportError:
            # Command system not available
            pass

    async def _start_mcp_servers(self, servers: dict[str, Any], plugin: LoadedPlugin) -> None:
        """Start MCP servers from plugin."""
        try:
            from ..services.mcp_client import get_mcp_client, MCPConfig

            mcp_client = get_mcp_client()

            for name, config in servers.items():
                if not config.enabled:
                    continue

                mcp_config = MCPConfig(
                    command=config.command, args=config.args, env=config.env, enabled=True
                )

                try:
                    await mcp_client.connect(name, mcp_config)
                    self._mcp_servers[name] = mcp_config
                except Exception as e:
                    print(f"Failed to start MCP server {name}: {e}")
        except ImportError:
            # MCP client not available
            pass

    def get_all_skills(self) -> list[SkillDefinition]:
        """Get all loaded skills from all plugins."""
        skills = []
        for loader in self._skill_loaders:
            # Access the internal dict - in production, add a proper method
            skills.extend(loader._skills.values())
        return skills

    def get_all_commands(self) -> list[SkillDefinition]:
        """Get all loaded commands from all plugins."""
        commands = []
        for loader in self._command_loaders:
            commands.extend(loader._commands.values())
        return commands


# Global integration instance
_integration: PluginIntegration | None = None


async def get_plugin_integration(manager: PluginManager | None = None) -> PluginIntegration:
    """Get global plugin integration instance."""
    global _integration
    if _integration is None:
        if manager is None:
            from .core.manager import get_plugin_manager

            manager = await get_plugin_manager()
        _integration = PluginIntegration(manager)
        await _integration.initialize()
    return _integration
