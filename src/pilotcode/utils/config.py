"""Configuration management with environment variable and model support."""

import json
import os
import asyncio
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any

from platformdirs import user_config_dir

from .models_config import (
    get_model_info,
    get_default_model,
    get_model_from_env,
)


@dataclass
class GlobalConfig:
    """Global configuration."""

    theme: str = "default"
    verbose: bool = False
    auto_compact: bool = True
    api_key: str | None = None
    base_url: str = ""
    default_model: str = ""
    model_provider: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    mcp_servers: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self):
        """Validate and set defaults after initialization."""
        # Set default model if not specified
        if not self.default_model:
            self.default_model = get_default_model()

        # Set base_url from model config if not specified
        if not self.base_url and self.default_model:
            model_info = get_model_info(self.default_model)
            if model_info:
                self.base_url = model_info.base_url


@dataclass
class ProjectConfig:
    """Project-specific configuration."""

    allowed_tools: list[str] = field(default_factory=list)
    mcp_servers: dict[str, dict[str, Any]] | None = None
    custom_instructions: str | None = None


class ConfigManager:
    """Manages configuration files with environment variable support."""

    CONFIG_DIR = Path(user_config_dir("pilotcode", "pilotcode"))
    SETTINGS_FILE = CONFIG_DIR / "settings.json"

    # Environment variable mappings
    ENV_MAPPINGS = {
        "PILOTCODE_THEME": "theme",
        "PILOTCODE_VERBOSE": "verbose",
        "PILOTCODE_AUTO_COMPACT": "auto_compact",
        "PILOTCODE_API_KEY": "api_key",
        "PILOTCODE_BASE_URL": "base_url",
        "PILOTCODE_MODEL": "default_model",
        # Legacy env vars for backward compatibility
        "LOCAL_API_KEY": "api_key",
        "OPENAI_BASE_URL": "base_url",
        "OPENAI_API_KEY": "api_key",
    }

    def __init__(self):
        self._global_config: GlobalConfig | None = None
        self._project_config: ProjectConfig | None = None
        self._ensure_config_dir()

    def _ensure_config_dir(self) -> None:
        """Ensure configuration directory exists."""
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def _apply_env_overrides(self, config: GlobalConfig) -> GlobalConfig:
        """Apply environment variable overrides to config."""
        for env_var, config_key in self.ENV_MAPPINGS.items():
            value = os.environ.get(env_var)
            if value is not None:
                # Handle boolean values
                if config_key in ("verbose", "auto_compact"):
                    value = value.lower() in ("true", "1", "yes", "on")
                setattr(config, config_key, value)

        # Check for model-specific env configuration
        model_from_env = get_model_from_env()
        if model_from_env:
            model_name, api_key = model_from_env
            if not config.default_model or config.default_model == get_default_model():
                config.default_model = model_name
            if not config.api_key:
                config.api_key = api_key

            # Update base_url from model config
            model_info = get_model_info(model_name)
            if model_info and not config.base_url:
                config.base_url = model_info.base_url

        return config

    def load_raw_global_config(self) -> GlobalConfig:
        """Load global configuration from file only (no env overrides).

        This is useful for checking the original config before environment
        variables are applied.
        """
        if self.SETTINGS_FILE.exists():
            try:
                with open(self.SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                return GlobalConfig(**data)
            except Exception:
                return GlobalConfig()
        return GlobalConfig()

    def load_global_config(self) -> GlobalConfig:
        """Load global configuration from file and environment."""
        if self._global_config is not None:
            return self._global_config

        # Load from file
        if self.SETTINGS_FILE.exists():
            try:
                with open(self.SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                self._global_config = GlobalConfig(**data)
            except Exception:
                self._global_config = GlobalConfig()
        else:
            self._global_config = GlobalConfig()

        # Apply environment overrides
        self._global_config = self._apply_env_overrides(self._global_config)

        # Set model provider
        if self._global_config.default_model:
            model_info = get_model_info(self._global_config.default_model)
            if model_info:
                self._global_config.model_provider = model_info.provider.value

        return self._global_config

    def save_global_config(self, config: GlobalConfig) -> None:
        """Save global configuration."""
        self._ensure_config_dir()
        with open(self.SETTINGS_FILE, "w") as f:
            json.dump(asdict(config), f, indent=2)
        self._global_config = config

    def load_project_config(self, cwd: str | None = None) -> ProjectConfig | None:
        """Load project configuration from .pilotcode.json."""
        if cwd is None:
            cwd = os.getcwd()

        config_file = Path(cwd) / ".pilotcode.json"
        if not config_file.exists():
            # Try to find in git root
            git_root = self._find_git_root(cwd)
            if git_root:
                config_file = Path(git_root) / ".pilotcode.json"

        if config_file.exists():
            try:
                with open(config_file, "r") as f:
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

    def is_configured(self) -> bool:
        """Check if the application has valid configuration."""
        config = self.load_global_config()

        # Check if API key is set
        if config.api_key:
            return True

        # Check if model-specific env vars are set
        model_from_env = get_model_from_env()
        if model_from_env:
            return True

        # Check for local models (Ollama, llama.cpp, etc. - no key needed)
        if config.default_model:
            # Ollama default model name
            if config.default_model == "ollama":
                return True
            # Local models with file extensions (.gguf, .bin, etc.)
            if ".gguf" in config.default_model or ".bin" in config.default_model:
                return True
            # Local models with specific patterns (e.g., localhost, 127.0.0.1, local network)
            if config.base_url and (
                "localhost" in config.base_url
                or "127.0.0.1" in config.base_url
                or ":11434" in config.base_url
                or config.base_url.startswith("http://192.168.")
                or config.base_url.startswith("http://10.")
                or config.base_url.startswith("http://172.")
            ):
                return True
            # Custom base URL without API key (local/custom endpoint)
            if config.base_url and not config.base_url.startswith("https://api."):
                return True

        return False

    async def verify_configuration(self, timeout: float = 10.0) -> dict[str, Any]:
        """Verify configuration by sending a test message to the LLM.

        Args:
            timeout: Timeout in seconds for the test request

        Returns:
            Dict with 'success' (bool), 'message' (str), and optional 'response' (str)
        """
        from .model_client import ModelClient, Message

        result = {
            "success": False,
            "message": "",
            "response": None,
            "error": None,
        }

        # First check if configuration exists
        if not self.is_configured():
            result["message"] = "No configuration found"
            return result

        config = self.load_global_config()

        try:
            # Create client with current configuration
            client = ModelClient(
                api_key=config.api_key or None,
                base_url=config.base_url or None,
                model=config.default_model or None,
            )

            # Send test message
            test_messages = [Message(role="user", content="Who are you? Reply in one sentence.")]

            response_chunks = []
            async for chunk in client.chat_completion(
                test_messages,
                max_tokens=50,
                stream=True,
                temperature=0.7,
            ):
                if "choices" in chunk and chunk["choices"]:
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        response_chunks.append(content)

                # Early exit if we have enough response
                if len(response_chunks) >= 5:
                    break

            await client.close()

            full_response = "".join(response_chunks).strip()

            if full_response:
                result["success"] = True
                result["message"] = "LLM responded successfully"
                result["response"] = full_response[:200]  # Truncate if too long
            else:
                result["message"] = "LLM returned empty response"
                result["error"] = "Empty response from model"

        except asyncio.TimeoutError:
            result["message"] = f"Connection timeout after {timeout}s"
            result["error"] = "Timeout"
        except Exception as e:
            error_str = str(e)
            result["message"] = f"Connection failed: {error_str[:100]}"
            result["error"] = error_str

        return result

    def get_config_status(self) -> dict[str, Any]:
        """Get detailed configuration status."""
        config = self.load_global_config()

        status = {
            "configured": self.is_configured(),
            "config_file_exists": self.SETTINGS_FILE.exists(),
            "config_file_path": str(self.SETTINGS_FILE),
            "model": config.default_model,
            "base_url": config.base_url,
            "has_api_key": bool(config.api_key),
            "env_overrides": {},
        }

        # Check which env vars are set
        for env_var in self.ENV_MAPPINGS.keys():
            if os.environ.get(env_var):
                status["env_overrides"][env_var] = "***set***"

        return status


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


def is_configured() -> bool:
    """Check if application is configured."""
    return get_config_manager().is_configured()


def get_config_status() -> dict[str, Any]:
    """Get configuration status."""
    return get_config_manager().get_config_status()


def ensure_configured() -> bool:
    """Ensure application is configured, return True if configured.

    This function checks configuration and can be used at startup
    to verify the application is ready to run.
    """
    return get_config_manager().is_configured()
