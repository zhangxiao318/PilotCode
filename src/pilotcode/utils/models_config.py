"""Model configuration for supported LLM providers.

Supports both domestic (China) and international models.
"""

from dataclasses import dataclass, field
from typing import Any
from enum import Enum


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
    env_key: str = ""

    def get_env_key(self) -> str:
        """Get environment variable key for API key."""
        if self.env_key:
            return self.env_key
        return f"{self.provider.value.upper()}_API_KEY"


# Predefined model configurations
SUPPORTED_MODELS: dict[str, ModelInfo] = {
    # International Models
    "openai": ModelInfo(
        name="openai",
        display_name="OpenAI GPT",
        provider=ModelProvider.OPENAI,
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o",
        description="OpenAI GPT-4o - Most capable multimodal model",
        supports_tools=True,
        supports_vision=True,
        max_tokens=4096,
        env_key="OPENAI_API_KEY",
    ),
    "openai-gpt4": ModelInfo(
        name="openai-gpt4",
        display_name="OpenAI GPT-4",
        provider=ModelProvider.OPENAI,
        base_url="https://api.openai.com/v1",
        default_model="gpt-4-turbo",
        description="OpenAI GPT-4 Turbo - High capability model",
        supports_tools=True,
        supports_vision=True,
        max_tokens=4096,
        env_key="OPENAI_API_KEY",
    ),
    "anthropic": ModelInfo(
        name="anthropic",
        display_name="Anthropic Claude",
        provider=ModelProvider.ANTHROPIC,
        base_url="https://api.anthropic.com/v1",
        default_model="claude-3-5-sonnet-20241022",
        description="Anthropic Claude 3.5 Sonnet - Excellent coding assistant",
        supports_tools=True,
        supports_vision=True,
        max_tokens=4096,
        env_key="ANTHROPIC_API_KEY",
    ),
    "azure": ModelInfo(
        name="azure",
        display_name="Azure OpenAI",
        provider=ModelProvider.AZURE,
        base_url="",
        default_model="gpt-4",
        description="Azure OpenAI Service - Enterprise grade",
        supports_tools=True,
        supports_vision=True,
        max_tokens=4096,
        env_key="AZURE_OPENAI_API_KEY",
    ),
    # Domestic (China) Models
    "deepseek": ModelInfo(
        name="deepseek",
        display_name="DeepSeek (深度求索)",
        provider=ModelProvider.DEEPSEEK,
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        description="DeepSeek V3 - Strong coding capabilities, cost-effective",
        supports_tools=True,
        supports_vision=False,
        max_tokens=4096,
        env_key="DEEPSEEK_API_KEY",
    ),
    "qwen": ModelInfo(
        name="qwen",
        display_name="Qwen (通义千问)",
        provider=ModelProvider.QWEN,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-max",
        description="Alibaba Qwen Max - Powerful Chinese/English model",
        supports_tools=True,
        supports_vision=True,
        max_tokens=4096,
        env_key="DASHSCOPE_API_KEY",
    ),
    "qwen-plus": ModelInfo(
        name="qwen-plus",
        display_name="Qwen Plus (通义千问 Plus)",
        provider=ModelProvider.QWEN,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-plus",
        description="Alibaba Qwen Plus - Balanced performance and cost",
        supports_tools=True,
        supports_vision=True,
        max_tokens=4096,
        env_key="DASHSCOPE_API_KEY",
    ),
    "zhipu": ModelInfo(
        name="zhipu",
        display_name="GLM (智谱清言)",
        provider=ModelProvider.ZHIPU,
        base_url="https://open.bigmodel.cn/api/paas/v4",
        default_model="glm-4",
        description="Zhipu GLM-4 - Strong Chinese model with tool use",
        supports_tools=True,
        supports_vision=True,
        max_tokens=4096,
        env_key="ZHIPU_API_KEY",
    ),
    "moonshot": ModelInfo(
        name="moonshot",
        display_name="Moonshot (月之暗面)",
        provider=ModelProvider.MOONSHOT,
        base_url="https://api.moonshot.cn/v1",
        default_model="moonshot-v1-8k",
        description="Moonshot Kimi - Long context window model",
        supports_tools=True,
        supports_vision=False,
        max_tokens=4096,
        env_key="MOONSHOT_API_KEY",
    ),
    "baichuan": ModelInfo(
        name="baichuan",
        display_name="Baichuan (百川智能)",
        provider=ModelProvider.BAICHUAN,
        base_url="https://api.baichuan-ai.com/v1",
        default_model="Baichuan4",
        description="Baichuan 4 - Advanced Chinese model",
        supports_tools=True,
        supports_vision=False,
        max_tokens=4096,
        env_key="BAICHUAN_API_KEY",
    ),
    "doubao": ModelInfo(
        name="doubao",
        display_name="Doubao (豆包)",
        provider=ModelProvider.DOUBAO,
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        default_model="doubao-pro-4k",
        description="ByteDance Doubao - Versatile model",
        supports_tools=True,
        supports_vision=False,
        max_tokens=4096,
        env_key="ARK_API_KEY",
    ),
    # Custom/Local
    "custom": ModelInfo(
        name="custom",
        display_name="Custom/OpenAI-compatible",
        provider=ModelProvider.CUSTOM,
        base_url="",
        default_model="default",
        description="Custom OpenAI-compatible endpoint",
        supports_tools=True,
        supports_vision=False,
        max_tokens=4096,
        env_key="OPENAI_API_KEY",
    ),
    "ollama": ModelInfo(
        name="ollama",
        display_name="Ollama (Local)",
        provider=ModelProvider.CUSTOM,
        base_url="http://localhost:11434/v1",
        default_model="llama3.1",
        description="Local Ollama instance",
        supports_tools=True,
        supports_vision=False,
        max_tokens=4096,
        env_key="",
    ),
}


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
