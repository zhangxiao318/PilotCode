"""Configuration management."""

import json
import os
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any

from platformdirs import user_config_dir


@dataclass
class GlobalConfig:
    """Global configuration."""
    theme: str = "default"
    verbose: bool = False
    auto_compact: bool = True
    api_key: str | None = None
    base_url: str = "http://172.19.201.40:3509/v1"
    default_model: str = "default"
    allowed_tools: list[str] = field(default_factory=list)
    mcp_servers: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class ProjectConfig:
    """Project-specific configuration."""
    allowed_tools: list[str] = field(default_factory=list)
    mcp_servers: dict[str, dict[str, Any]] | None = None
    custom_instructions: str | None = None


class ConfigManager:
    """Manages configuration files."""
    
    CONFIG_DIR = Path(user_config_dir("claudecode", "claudecode"))
    SETTINGS_FILE = CONFIG_DIR / "settings.json"
    
    def __init__(self):
        self._global_config: GlobalConfig | None = None
        self._project_config: ProjectConfig | None = None
        self._ensure_config_dir()
    
    def _ensure_config_dir(self) -> None:
        """Ensure configuration directory exists."""
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    def load_global_config(self) -> GlobalConfig:
        """Load global configuration."""
        if self._global_config is not None:
            return self._global_config
        
        if self.SETTINGS_FILE.exists():
            try:
                with open(self.SETTINGS_FILE, 'r') as f:
                    data = json.load(f)
                self._global_config = GlobalConfig(**data)
            except Exception:
                self._global_config = GlobalConfig()
        else:
            self._global_config = GlobalConfig()
        
        # Override with environment variables
        if os.environ.get("LOCAL_API_KEY"):
            self._global_config.api_key = os.environ.get("LOCAL_API_KEY")
        if os.environ.get("OPENAI_BASE_URL"):
            self._global_config.base_url = os.environ.get("OPENAI_BASE_URL")
        
        return self._global_config
    
    def save_global_config(self, config: GlobalConfig) -> None:
        """Save global configuration."""
        self._ensure_config_dir()
        with open(self.SETTINGS_FILE, 'w') as f:
            json.dump(asdict(config), f, indent=2)
        self._global_config = config
    
    def load_project_config(self, cwd: str | None = None) -> ProjectConfig | None:
        """Load project configuration from .claudecode.json."""
        if cwd is None:
            cwd = os.getcwd()
        
        config_file = Path(cwd) / ".claudecode.json"
        if not config_file.exists():
            # Try to find in git root
            git_root = self._find_git_root(cwd)
            if git_root:
                config_file = Path(git_root) / ".claudecode.json"
        
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    data = json.load(f)
                return ProjectConfig(**data)
            except Exception:
                pass
        
        return None
    
    def _find_git_root(self, path: str) -> str | None:
        """Find git repository root."""
        current = Path(path).resolve()
        while current != current.parent:
            if (current / ".git").exists():
                return str(current)
            current = current.parent
        return None
    
    def get_effective_config(self, cwd: str | None = None) -> dict[str, Any]:
        """Get effective configuration (global + project)."""
        global_config = self.load_global_config()
        project_config = self.load_project_config(cwd)
        
        result = asdict(global_config)
        
        if project_config:
            project_dict = {k: v for k, v in asdict(project_config).items() if v is not None}
            result.update(project_dict)
        
        return result


# Global instance
_config_manager: ConfigManager | None = None


def get_config_manager() -> ConfigManager:
    """Get global config manager."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def get_global_config() -> GlobalConfig:
    """Get global configuration."""
    return get_config_manager().load_global_config()


def get_project_config(cwd: str | None = None) -> ProjectConfig | None:
    """Get project configuration."""
    return get_config_manager().load_project_config(cwd)


def save_global_config(config: GlobalConfig) -> None:
    """Save global configuration."""
    get_config_manager().save_global_config(config)
