"""Model configuration for supported LLM providers.

Supports both domestic (China) and international models.
Model metadata is loaded from config/models.json so it can be updated
without touching source code.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any
import json


class ModelProvider(Enum):
    """Model provider types."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE = "azure"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    ZHIPU = "zhipu"
    MOONSHOT = "moonshot"
    BAICHUAN = "baichuan"
    DOUBAO = "doubao"
    CUSTOM = "custom"


@dataclass
class ModelInfo:
    """Information about a supported model."""

    name: str
    display_name: str
    provider: ModelProvider
    base_url: str
    default_model: str
    description: str
    supports_tools: bool = True
    supports_vision: bool = False
    max_tokens: int = 4096
    context_window: int = 8192
    env_key: str = ""

    def get_env_key(self) -> str:
        """Get environment variable key for API key."""
        if self.env_key:
            return self.env_key
        return f"{self.provider.value.upper()}_API_KEY"


def _load_models_json() -> dict[str, ModelInfo]:
    """Load model definitions from JSON configuration file.

    Searches for config/models.json relative to the project root,
    falling back to the shipped default if the file is missing or malformed.
    """
    # Determine candidate paths for the JSON file
    src_dir = Path(__file__).resolve().parent.parent  # src/pilotcode
    project_root = src_dir.parent  # project root
    candidates = [
        project_root / "config" / "models.json",
        Path("config/models.json"),
    ]

    data: dict = {}
    for candidate in candidates:
        if candidate.exists():
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                break
            except (json.JSONDecodeError, OSError):
                continue

    models: dict[str, ModelInfo] = {}
    for key, raw in data.get("models", {}).items():
        try:
            provider = ModelProvider(raw.get("provider", "custom"))
        except ValueError:
            provider = ModelProvider.CUSTOM

        models[key] = ModelInfo(
            name=raw.get("name", key),
            display_name=raw.get("display_name", key),
            provider=provider,
            base_url=raw.get("base_url", ""),
            default_model=raw.get("default_model", "default"),
            description=raw.get("description", ""),
            supports_tools=raw.get("supports_tools", True),
            supports_vision=raw.get("supports_vision", False),
            max_tokens=raw.get("max_tokens", 4096),
            context_window=raw.get("context_window", 8192),
            env_key=raw.get("env_key", ""),
        )

    return models


# Runtime-loaded model configurations
SUPPORTED_MODELS: dict[str, ModelInfo] = _load_models_json()


def _get_models_json_path() -> Path | None:
    """Return the path to the active models.json file, or None."""
    src_dir = Path(__file__).resolve().parent.parent  # src/pilotcode
    project_root = src_dir.parent  # project root
    candidates = [
        project_root / "config" / "models.json",
        Path("config/models.json"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def update_model_in_json(model_name: str, updates: dict[str, Any]) -> bool:
    """Update fields for a given model in models.json.

    Args:
        model_name: Key in the models.json "models" object.
        updates: Dict of field names to new values (e.g. {"context_window": 8192}).

    Returns:
        True if the file was updated, False otherwise.
    """
    path = _get_models_json_path()
    if path is None:
        return False

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False

    models = data.get("models", {})
    if model_name not in models:
        return False

    models[model_name].update(updates)

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except OSError:
        return False

    # Refresh in-memory cache
    global SUPPORTED_MODELS
    SUPPORTED_MODELS = _load_models_json()
    return True


def get_model_info(model_name: str) -> ModelInfo | None:
    """Get model information by name."""
    return SUPPORTED_MODELS.get(model_name)


def get_all_models() -> dict[str, ModelInfo]:
    """Get all supported models."""
    return SUPPORTED_MODELS.copy()


def get_models_by_provider(provider: ModelProvider) -> dict[str, ModelInfo]:
    """Get models for a specific provider."""
    return {k: v for k, v in SUPPORTED_MODELS.items() if v.provider == provider}


def get_international_models() -> dict[str, ModelInfo]:
    """Get international (non-China) models."""
    domestic = {
        ModelProvider.DEEPSEEK,
        ModelProvider.QWEN,
        ModelProvider.ZHIPU,
        ModelProvider.MOONSHOT,
        ModelProvider.BAICHUAN,
        ModelProvider.DOUBAO,
    }
    return {k: v for k, v in SUPPORTED_MODELS.items() if v.provider not in domestic}


def get_domestic_models() -> dict[str, ModelInfo]:
    """Get domestic (China) models."""
    domestic = {
        ModelProvider.DEEPSEEK,
        ModelProvider.QWEN,
        ModelProvider.ZHIPU,
        ModelProvider.MOONSHOT,
        ModelProvider.BAICHUAN,
        ModelProvider.DOUBAO,
    }
    return {k: v for k, v in SUPPORTED_MODELS.items() if v.provider in domestic}


def get_default_model() -> str:
    """Get default model name."""
    return "deepseek"


def get_model_context_window(model_name: str | None = None) -> int:
    """Get the context window for a model (static config).

    Args:
        model_name: Model key. If None, uses the currently configured model.

    Returns:
        Context window size in tokens.
    """
    if model_name is None:
        from .config import get_global_config

        model_name = get_global_config().default_model

    info = get_model_info(model_name)
    if info and info.context_window > 0:
        return info.context_window
    return 128_000  # Safe fallback


def get_model_max_tokens(model_name: str | None = None) -> int:
    """Get the max output tokens for a model (static config).

    Args:
        model_name: Model key. If None, uses the currently configured model.

    Returns:
        Max output tokens.
    """
    if model_name is None:
        from .config import get_global_config

        model_name = get_global_config().default_model

    info = get_model_info(model_name)
    if info and info.max_tokens > 0:
        return info.max_tokens
    return 4096  # Safe fallback


def check_api_key_configured(model_name: str) -> bool:
    """Check if API key is configured for a model."""
    import os

    model_info = get_model_info(model_name)

    # For custom/unknown models, consider configured if model name is provided
    # (local models like Ollama don't need API keys)
    if not model_info:
        # Check if it looks like a local model (has file extension or specific patterns)
        if ".gguf" in model_name or ":" in model_name:
            return True
        return False

    # For Ollama/local models, no API key needed
    if model_info.provider == ModelProvider.CUSTOM and not model_info.env_key:
        return True

    # Check environment variable
    env_key = model_info.get_env_key()
    if env_key and os.environ.get(env_key):
        return True

    # Check generic env vars
    if os.environ.get("PILOTCODE_API_KEY"):
        return True
    if os.environ.get("OPENAI_API_KEY"):
        return True

    return False


def get_model_from_env() -> tuple[str, str] | None:
    """Get model configuration from environment variables.

    Returns:
        Tuple of (model_name, api_key) or None
    """
    import os

    # Check for specific provider env vars first
    env_mappings = {
        "OPENAI_API_KEY": "openai",
        "ANTHROPIC_API_KEY": "anthropic",
        "AZURE_OPENAI_API_KEY": "azure",
        "DEEPSEEK_API_KEY": "deepseek",
        "DASHSCOPE_API_KEY": "qwen",
        "ZHIPU_API_KEY": "zhipu",
        "MOONSHOT_API_KEY": "moonshot",
        "BAICHUAN_API_KEY": "baichuan",
        "ARK_API_KEY": "doubao",
    }

    for env_var, model_name in env_mappings.items():
        api_key = os.environ.get(env_var)
        if api_key:
            return (model_name, api_key)

    # Check for generic PILOTCODE env vars
    pilotcode_model = os.environ.get("PILOTCODE_MODEL")
    pilotcode_key = os.environ.get("PILOTCODE_API_KEY")

    if pilotcode_key:
        return (pilotcode_model or "custom", pilotcode_key)

    return None


def format_model_list() -> str:
    """Format model list for display."""
    lines = []

    lines.append("\n[bold cyan]International Models:[/bold cyan]")
    for key, info in get_international_models().items():
        if not info.base_url:  # Skip custom with no URL
            continue
        lines.append(f"  [green]{key:<15}[/green] - {info.display_name}")
        lines.append(f"    {info.description}")

    lines.append("\n[bold cyan]Domestic (China) Models:[/bold cyan]")
    for key, info in get_domestic_models().items():
        lines.append(f"  [green]{key:<15}[/green] - {info.display_name}")
        lines.append(f"    {info.description}")

    lines.append("\n[bold cyan]Local/Custom:[/bold cyan]")
    lines.append(f"  [green]{'ollama':<15}[/green] - Ollama (Local)")
    lines.append("    Local Ollama instance")
    lines.append(f"  [green]{'custom':<15}[/green] - Custom endpoint")
    lines.append("    Custom OpenAI-compatible API")

    return "\n".join(lines)
