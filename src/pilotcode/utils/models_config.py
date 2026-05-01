"""Model configuration for supported LLM providers.

Supports both domestic (China) and international models.
Model metadata is loaded from config/models.json so it can be updated
without touching source code.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
import json
import logging

from .model_capabilities import ModelCapabilities

logger = logging.getLogger(__name__)


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
    VLLM = "vllm"
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
    supports_tool_choice: bool = True
    max_tokens: int = 4096
    context_window: int = 8192
    timeout: float = 300.0
    env_key: str = ""
    disabled: bool = False
    disabled_reason: str = ""
    api_protocol: str = "openai"
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)

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
    project_root = src_dir.parent.parent  # project root
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
            supports_tool_choice=raw.get("supports_tool_choice", True),
            max_tokens=raw.get("max_tokens", 4096),
            context_window=raw.get("context_window", 8192),
            timeout=raw.get("timeout", 300.0),
            env_key=raw.get("env_key", ""),
            disabled=raw.get("disabled", False),
            disabled_reason=raw.get("disabled_reason", ""),
            api_protocol=raw.get("api_protocol", ""),
            capabilities=ModelCapabilities.from_dict(raw.get("capabilities", {})),
        )

    return models


# Runtime-loaded model configurations
SUPPORTED_MODELS: dict[str, ModelInfo] = _load_models_json()


def _get_models_json_path() -> Path | None:
    """Return the path to the active models.json file, or None."""
    src_dir = Path(__file__).resolve().parent.parent  # src/pilotcode
    project_root = src_dir.parent.parent  # project root
    candidates = [
        project_root / "config" / "models.json",
        src_dir.parent.parent / "config" / "models.json",
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
    local = {ModelProvider.CUSTOM, ModelProvider.VLLM}
    return {k: v for k, v in SUPPORTED_MODELS.items() if v.provider not in domestic | local}


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


# ------------------------------------------------------------------
# Backend capability probing (llama.cpp /props, etc.)
# ------------------------------------------------------------------

_backend_limits_cache: dict[str, dict[str, int]] = {}


def _probe_backend_limits(base_url: str, api_protocol: str = "openai") -> dict[str, int] | None:
    """Synchronously probe the backend for actual model limits.

    Queries llama-server /props, Ollama /api/show, and OpenAI-compatible
    /v1/models to get the real context_window and max_tokens rather than
    relying on static fallbacks.

    Returns a dict with ``context_window`` and/or ``max_tokens`` keys,
    or None if probing failed.
    """
    if not base_url:
        return None

    # Use cached result if available
    if base_url in _backend_limits_cache:
        return _backend_limits_cache[base_url]

    try:
        import httpx
    except ImportError:
        return None

    root_url = base_url.rstrip("/")
    if root_url.endswith("/v1"):
        root_url = root_url[:-3]

    cap: dict[str, int] = {}

    # Anthropic protocol: skip local backend probes, try /v1/models directly
    if api_protocol == "anthropic":
        try:
            with httpx.Client(timeout=3.0, follow_redirects=True) as client:
                resp = client.get(f"{root_url}/v1/models")
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("data", [])
                    if models:
                        model_data = models[0]
                        ctx = model_data.get("context_window")
                        if ctx is not None:
                            cap["context_window"] = int(ctx)
                        max_out = model_data.get("max_output_tokens")
                        if max_out is not None:
                            cap["max_tokens"] = int(max_out)
        except Exception as exc:
            logger.debug("Anthropic backend probe /v1/models failed: %s", exc)
        if cap:
            _backend_limits_cache[base_url] = cap
            logger.debug("Probed Anthropic backend limits for %s: %s", base_url, cap)
            return cap
        return None

    # 1. llama.cpp / llama-server -> GET /props
    try:
        with httpx.Client(timeout=3.0, follow_redirects=True) as client:
            resp = client.get(f"{root_url}/props")
            if resp.status_code == 200:
                data = resp.json()
                dgs = data.get("default_generation_settings", {})
                n_ctx = dgs.get("n_ctx")
                if n_ctx is not None:
                    cap["context_window"] = int(n_ctx)
                params = dgs.get("params", {})
                max_tok = params.get("max_tokens", params.get("n_predict"))
                if max_tok is not None and max_tok > 0:
                    cap["max_tokens"] = int(max_tok)
    except Exception as exc:
        logger.debug("Backend probe /props failed: %s", exc)

    # 2. Ollama -> POST /api/show
    if "context_window" not in cap:
        try:
            with httpx.Client(timeout=3.0, follow_redirects=True) as client:
                resp = client.post(f"{root_url}/api/show", json={"model": "default"})
                if resp.status_code == 200:
                    data = resp.json()
                    model_info = data.get("model_info", {})
                    for key in ("context_length", "context_window"):
                        val = model_info.get(key)
                        if val is not None:
                            cap["context_window"] = int(val)
                            break
        except Exception as exc:
            logger.debug("Backend probe /api/show failed: %s", exc)

    # 3. OpenAI-compatible -> GET /v1/models
    if "context_window" not in cap:
        try:
            with httpx.Client(timeout=3.0, follow_redirects=True) as client:
                resp = client.get(f"{root_url}/v1/models")
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("data", [])
                    if models:
                        model_data = models[0]
                        for key in ("context_length", "context_window", "max_model_len"):
                            val = model_data.get(key)
                            if val is not None:
                                cap["context_window"] = int(val)
                                break
        except Exception as exc:
            logger.debug("Backend probe /v1/models failed: %s", exc)

    if cap:
        _backend_limits_cache[base_url] = cap
        logger.debug("Probed backend limits for %s: %s", base_url, cap)
        return cap

    return None


def get_model_limits(model_name: str | None = None) -> dict[str, int]:
    """Get both context_window and max_tokens for the current model.

    Follows OpenCode-style priority:
        1. Probe the actual backend (llama.cpp /props, etc.)
        2. User's explicit config (settings.json)
        3. Static model config (models.json) for remote models
        4. Safe fallback

    Returns:
        Dict with ``context_window`` and ``max_tokens`` keys.
    """
    from .config import get_global_config, is_local_url

    config = get_global_config()
    base_url = config.base_url or ""
    is_local = is_local_url(base_url)

    result = {"context_window": 128_000, "max_tokens": 4096}

    # Priority 1: Probe backend for actual limits (especially critical for local)
    probed: dict[str, int] | None = None
    probed_context = False
    if base_url:
        protocol = infer_api_protocol(
            model_name or config.default_model,
            base_url,
            config.get_model_config(model_name or config.default_model),
            get_model_info(model_name or config.default_model),
        )
        probed = _probe_backend_limits(base_url, protocol)
        if probed:
            result.update(probed)
            if "context_window" in probed:
                probed_context = True

    # Priority 2: User's explicit config (but cap at probed value if probed is smaller)
    user_ctx = getattr(config, "context_window", 0)
    if isinstance(user_ctx, int) and user_ctx > 0:
        if "context_window" in result and result["context_window"] > 0:
            # Trust the smaller value: backend reality wins over user config
            result["context_window"] = min(user_ctx, result["context_window"])
        else:
            result["context_window"] = user_ctx

    # Priority 3: Static model config (remote models only)
    if not is_local:
        if model_name is None:
            model_name = config.default_model
        info = get_model_info(model_name)
        if info:
            if info.context_window > 0 and result.get("context_window", 0) <= 0:
                result["context_window"] = info.context_window
            if info.max_tokens > 0 and result.get("max_tokens", 0) <= 0:
                result["max_tokens"] = info.max_tokens

    # Ensure we have sensible fallbacks
    if result.get("context_window", 0) <= 0:
        result["context_window"] = 128_000

    # If backend was probed but didn't report max_tokens, compute a conservative
    # default based on the actual context window so usable space stays reasonable.
    if result.get("max_tokens", 0) <= 0 or (probed_context and "max_tokens" not in (probed or {})):
        ctx = result.get("context_window", 128_000)
        result["max_tokens"] = min(8_192, max(1_024, ctx // 4))

    return result


def get_model_context_window(model_name: str | None = None) -> int:
    """Get the context window for a model.

    Uses :func:`get_model_limits` so that local backends are probed for
    their real ``n_ctx`` instead of falling back to a hard-coded 128K.
    """
    return get_model_limits(model_name)["context_window"]


def get_model_max_tokens(model_name: str | None = None) -> int:
    """Get the max output tokens for a model.

    Uses :func:`get_model_limits` so that local backends are probed for
    their real ``max_tokens`` instead of falling back to a hard-coded 4096.
    """
    return get_model_limits(model_name)["max_tokens"]


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

    # For Ollama/vLLM/local models, no API key needed
    if model_info.provider in (ModelProvider.CUSTOM, ModelProvider.VLLM) and not model_info.env_key:
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
            info = get_model_info(model_name)
            if info and info.disabled:
                continue
            return (model_name, api_key)

    # Check for generic PILOTCODE env vars
    pilotcode_model = os.environ.get("PILOTCODE_MODEL")
    pilotcode_key = os.environ.get("PILOTCODE_API_KEY")

    if pilotcode_key:
        return (pilotcode_model or "custom", pilotcode_key)

    return None


def infer_api_protocol(
    model_name: str,
    base_url: str,
    model_override: dict[str, str] | None = None,
    model_info: ModelInfo | None = None,
) -> str:
    """Infer the API protocol for a model configuration.

    Resolution order:
        1. Explicit override from settings.json (model_overrides.api_protocol)
        2. Explicit config from models.json (model_info.api_protocol)
        3. URL path heuristics (/v1/messages -> anthropic, /chat/completions -> openai)
        4. Model name heuristics (claude-* -> anthropic, gpt-* -> openai)
        5. Provider field fallback (anthropic -> anthropic, others -> openai)
        6. Default to "openai"
    """
    # 1. User override
    if model_override and model_override.get("api_protocol"):
        return model_override["api_protocol"]

    # 2. models.json explicit config
    if model_info and model_info.api_protocol:
        return model_info.api_protocol

    # 3. URL path heuristics
    url = (base_url or "").lower().rstrip("/")
    if "/messages" in url and "/chat/completions" not in url:
        return "anthropic"
    if "/chat/completions" in url:
        return "openai"

    # 4. Model name heuristics
    mn = (model_name or "").lower()
    if mn.startswith("claude-"):
        return "anthropic"
    if mn.startswith("gpt-") or mn.startswith("o1") or mn.startswith("o3"):
        return "openai"

    # 5. Provider fallback
    if model_info and model_info.provider == ModelProvider.ANTHROPIC:
        return "anthropic"

    # 6. Default
    return "openai"


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
    lines.append(f"  [green]{'vllm':<15}[/green] - vLLM (Local)")
    lines.append("    Local vLLM inference server (OpenAI-compatible)")
    lines.append(f"  [green]{'custom':<15}[/green] - Custom endpoint")
    lines.append("    Custom OpenAI-compatible API")

    return "\n".join(lines)
