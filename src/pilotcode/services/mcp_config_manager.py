"""MCP server configuration manager with hierarchical scopes.

Following Claude Code's approach with three-level configuration:
- global: User-level configuration
- project: Project-level configuration
- mcprc: Repository-level (.mcprc file)

Lower-level configurations override higher-level ones.
"""

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ..utils.paths import get_config_dir

from .mcp_client import MCPConfig


class ConfigScope(Enum):
    """Configuration scope levels."""

    GLOBAL = "global"
    PROJECT = "project"
    MCPRC = "mcprc"


@dataclass
class MCPServerEntry:
    """MCP server configuration entry with scope info."""

    name: str
    config: MCPConfig
    scope: ConfigScope
    source_path: str | None = None  # Path to config file for mcprc scope


class MCPConfigManager:
    """Manages MCP server configurations across scopes.

    Implements Claude Code's three-level hierarchical configuration:
    1. Global: ~/.config/pilotcode/settings.json
    2. Project: .pilotcode.json in project root
    3. MCPrc: .mcprc file in current directory

    Lower scopes override higher scopes.
    """

    MCPRC_FILENAME = ".mcprc"
    PROJECT_CONFIG_FILENAME = ".pilotcode.json"

    def __init__(self):
        self._config_dir = get_config_dir()
        self._global_config_file = self._config_dir / "settings.json"

    def _get_cwd(self) -> Path:
        """Get current working directory."""
        return Path.cwd()

    def _find_project_root(self, path: Path | None = None) -> Path | None:
        """Find project root (git root or directory with config file)."""
        if path is None:
            path = self._get_cwd()

        current = path.resolve()
        while current != current.parent:
            # Check for git root
            if (current / ".git").exists():
                return current
            # Check for project config
            if (current / self.PROJECT_CONFIG_FILENAME).exists():
                return current
            current = current.parent

        return None

    def _load_json_file(self, path: Path) -> dict[str, Any] | None:
        """Load and parse JSON file."""
        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def _save_json_file(self, path: Path, data: dict[str, Any]) -> None:
        """Save data to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_global_servers(self) -> dict[str, MCPConfig]:
        """Get global MCP servers."""
        data = self._load_json_file(self._global_config_file)

        if data is None:
            return {}

        servers = data.get("mcp_servers", {})
        return {
            name: MCPConfig(**config)
            for name, config in servers.items()
            if isinstance(config, dict) and config.get("enabled", True)
        }

    def add_global_server(self, name: str, config: MCPConfig) -> None:
        """Add or update a global MCP server."""
        data = self._load_json_file(self._global_config_file) or {}

        if "mcp_servers" not in data:
            data["mcp_servers"] = {}

        data["mcp_servers"][name] = {
            "command": config.command,
            "args": config.args,
            "env": config.env,
            "enabled": config.enabled,
        }

        self._save_json_file(self._global_config_file, data)

    def remove_global_server(self, name: str) -> bool:
        """Remove a global MCP server."""
        data = self._load_json_file(self._global_config_file)

        if data is None or "mcp_servers" not in data:
            return False

        if name in data["mcp_servers"]:
            del data["mcp_servers"][name]
            self._save_json_file(self._global_config_file, data)
            return True

        return False

    def get_project_servers(self, project_path: Path | None = None) -> dict[str, MCPConfig]:
        """Get project-level MCP servers."""
        root = self._find_project_root(project_path)

        if root is None:
            return {}

        config_file = root / self.PROJECT_CONFIG_FILENAME
        data = self._load_json_file(config_file)

        if data is None:
            return {}

        servers = data.get("mcp_servers", {})
        if not isinstance(servers, dict):
            return {}

        return {
            name: MCPConfig(**config)
            for name, config in servers.items()
            if isinstance(config, dict) and config.get("enabled", True)
        }

    def add_project_server(
        self, name: str, config: MCPConfig, project_path: Path | None = None
    ) -> None:
        """Add or update a project-level MCP server."""
        root = self._find_project_root(project_path)

        if root is None:
            # Create in current directory
            root = self._get_cwd()

        config_file = root / self.PROJECT_CONFIG_FILENAME
        data = self._load_json_file(config_file) or {}

        if "mcp_servers" not in data:
            data["mcp_servers"] = {}

        data["mcp_servers"][name] = {
            "command": config.command,
            "args": config.args,
            "env": config.env,
            "enabled": config.enabled,
        }

        self._save_json_file(config_file, data)

    def remove_project_server(self, name: str, project_path: Path | None = None) -> bool:
        """Remove a project-level MCP server."""
        root = self._find_project_root(project_path)

        if root is None:
            return False

        config_file = root / self.PROJECT_CONFIG_FILENAME
        data = self._load_json_file(config_file)

        if data is None or "mcp_servers" not in data:
            return False

        if name in data["mcp_servers"]:
            del data["mcp_servers"][name]
            self._save_json_file(config_file, data)
            return True

        return False

    def get_mcprc_servers(self, path: Path | None = None) -> dict[str, MCPConfig]:
        """Get MCP servers from .mcprc file.

        .mcprc is a dedicated file for MCP configuration at the repository level.
        """
        if path is None:
            # Look for .mcprc in current directory and project root
            cwd = self._get_cwd()
            mcprc_file = cwd / self.MCPRC_FILENAME

            if not mcprc_file.exists():
                # Try project root
                root = self._find_project_root()
                if root:
                    mcprc_file = root / self.MCPRC_FILENAME
        else:
            mcprc_file = path / self.MCPRC_FILENAME
            if path.name == self.MCPRC_FILENAME:
                mcprc_file = path

        if not mcprc_file.exists():
            return {}

        data = self._load_json_file(mcprc_file)

        if data is None or not isinstance(data, dict):
            return {}

        # .mcprc format: {server_name: config}
        return {
            name: MCPConfig(**config)
            for name, config in data.items()
            if isinstance(config, dict) and config.get("enabled", True)
        }

    def add_mcprc_server(
        self, name: str, config: MCPConfig, mcprc_path: Path | None = None
    ) -> None:
        """Add or update an MCP server in .mcprc file."""
        if mcprc_path is None:
            # Use project root if available, otherwise cwd
            root = self._find_project_root()
            if root:
                mcprc_file = root / self.MCPRC_FILENAME
            else:
                mcprc_file = self._get_cwd() / self.MCPRC_FILENAME
        else:
            if mcprc_path.is_dir():
                mcprc_file = mcprc_path / self.MCPRC_FILENAME
            else:
                mcprc_file = mcprc_path

        data = self._load_json_file(mcprc_file) or {}

        data[name] = {
            "command": config.command,
            "args": config.args,
            "env": config.env,
            "enabled": config.enabled,
        }

        self._save_json_file(mcprc_file, data)

    def remove_mcprc_server(self, name: str, mcprc_path: Path | None = None) -> bool:
        """Remove an MCP server from .mcprc file."""
        if mcprc_path is None:
            root = self._find_project_root()
            if root:
                mcprc_file = root / self.MCPRC_FILENAME
            else:
                mcprc_file = self._get_cwd() / self.MCPRC_FILENAME
        else:
            if mcprc_path.is_dir():
                mcprc_file = mcprc_path / self.MCPRC_FILENAME
            else:
                mcprc_file = mcprc_path

        if not mcprc_file.exists():
            return False

        data = self._load_json_file(mcprc_file)

        if data is None or not isinstance(data, dict):
            return False

        if name in data:
            del data[name]
            self._save_json_file(mcprc_file, data)
            return True

        return False

    def get_all_servers(self, cwd: Path | None = None) -> dict[str, MCPServerEntry]:
        """Get all MCP servers with merged configuration.

        Returns servers from all scopes with lower scopes overriding higher scopes.
        Priority: mcprc > project > global
        """
        servers: dict[str, MCPServerEntry] = {}

        # 1. Load global servers (lowest priority)
        for name, config in self.get_global_servers().items():
            if config.enabled:
                servers[name] = MCPServerEntry(name=name, config=config, scope=ConfigScope.GLOBAL)

        # 2. Load project servers (override global)
        project_root = self._find_project_root(cwd)
        for name, config in self.get_project_servers(cwd).items():
            if config.enabled:
                servers[name] = MCPServerEntry(
                    name=name,
                    config=config,
                    scope=ConfigScope.PROJECT,
                    source_path=str(project_root) if project_root else None,
                )

        # 3. Load .mcprc servers (highest priority)
        mcprc_path = None
        if cwd:
            mcprc_path = cwd / self.MCPRC_FILENAME
        if not mcprc_path or not mcprc_path.exists():
            if project_root:
                mcprc_path = project_root / self.MCPRC_FILENAME

        for name, config in self.get_mcprc_servers(cwd).items():
            if config.enabled:
                servers[name] = MCPServerEntry(
                    name=name,
                    config=config,
                    scope=ConfigScope.MCPRC,
                    source_path=str(mcprc_path) if mcprc_path else None,
                )

        return servers

    def add_server(
        self, name: str, config: MCPConfig, scope: ConfigScope = ConfigScope.PROJECT
    ) -> None:
        """Add an MCP server to the specified scope."""
        if scope == ConfigScope.GLOBAL:
            self.add_global_server(name, config)
        elif scope == ConfigScope.PROJECT:
            self.add_project_server(name, config)
        elif scope == ConfigScope.MCPRC:
            self.add_mcprc_server(name, config)
        else:
            raise ValueError(f"Unknown scope: {scope}")

    def remove_server(self, name: str, scope: ConfigScope | None = None) -> bool:
        """Remove an MCP server.

        If scope is None, tries to remove from all scopes in order: mcprc, project, global
        """
        if scope is not None:
            if scope == ConfigScope.GLOBAL:
                return self.remove_global_server(name)
            elif scope == ConfigScope.PROJECT:
                return self.remove_project_server(name)
            elif scope == ConfigScope.MCPRC:
                return self.remove_mcprc_server(name)
            return False

        # Try all scopes
        if self.remove_mcprc_server(name):
            return True
        if self.remove_project_server(name):
            return True
        if self.remove_global_server(name):
            return True
        return False

    def list_servers(self, cwd: Path | None = None) -> list[MCPServerEntry]:
        """List all configured MCP servers with their scopes."""
        return list(self.get_all_servers(cwd).values())

    def get_server(self, name: str, cwd: Path | None = None) -> MCPServerEntry | None:
        """Get a specific MCP server by name (respecting scope priority)."""
        servers = self.get_all_servers(cwd)
        return servers.get(name)


# Global instance
_mcp_config_manager: MCPConfigManager | None = None


def get_mcp_config_manager() -> MCPConfigManager:
    """Get global MCP config manager."""
    global _mcp_config_manager
    if _mcp_config_manager is None:
        _mcp_config_manager = MCPConfigManager()
    return _mcp_config_manager
