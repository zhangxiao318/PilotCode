"""Utility functions for PilotCode."""

from .config import (
    ConfigManager,
    get_config_manager,
    get_global_config,
    get_project_config,
    save_global_config,
)
from .model_client import (
    ModelClient,
    get_model_client,
    Message as APIMessage,
    ToolCall,
    ToolResult,
)
from .model_router import (
    ModelRouter,
    ModelTier,
    TaskType,
    ModelConfig,
    get_model_router,
    generate_title,
    binary_decision,
    simple_classify,
    quick_summarize,
)
from .token_utils import (
    count_tokens,
    count_messages_tokens,
    estimate_context_window,
    estimate_max_tokens,
    safe_token_count,
    get_context_token_usage,
    get_model_specific_tokenizer,
)

__all__ = [
    # Config
    "ConfigManager",
    "get_config_manager",
    "get_global_config",
    "get_project_config",
    "save_global_config",
    # Model client
    "ModelClient",
    "get_model_client",
    "APIMessage",
    "ToolCall",
    "ToolResult",
    # Model router
    "ModelRouter",
    "ModelTier",
    "TaskType",
    "ModelConfig",
    "get_model_router",
    "generate_title",
    "binary_decision",
    "simple_classify",
    "quick_summarize",
    # Token utilities
    "count_tokens",
    "count_messages_tokens",
    "estimate_context_window",
    "estimate_max_tokens",
    "safe_token_count",
    "get_context_token_usage",
    "get_model_specific_tokenizer",
]
