"""Configuration for automatic task decomposition.

Controls when and how tasks are automatically decomposed.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class AutoDecompositionConfig:
    """Configuration for automatic task decomposition."""

    # Enable/disable automatic decomposition globally
    enabled: bool = True

    # Confidence threshold for auto-decomposition
    # Tasks with confidence below this will use LLM analysis
    min_confidence: float = 0.6

    # Maximum complexity score for simple tasks
    # Tasks with complexity below this won't be decomposed
    simple_task_threshold: int = 2

    # Minimum number of subtasks to consider decomposition beneficial
    min_subtasks: int = 2

    # Maximum task length for simple tasks (in characters)
    max_simple_task_length: int = 100

    # Auto-decompose based on task patterns
    auto_detect_patterns: bool = True

    # Require user confirmation before decomposing
    require_confirmation: bool = False

    # Default strategy when auto-decomposing
    default_strategy: str = "sequential"


# Global configuration instance
_auto_config = AutoDecompositionConfig()


def get_auto_config() -> AutoDecompositionConfig:
    """Get the global auto-decomposition configuration."""
    return _auto_config


def configure_auto_decomposition(
    enabled: Optional[bool] = None,
    min_confidence: Optional[float] = None,
    simple_task_threshold: Optional[int] = None,
    require_confirmation: Optional[bool] = None,
    default_strategy: Optional[str] = None,
):
    """Configure automatic task decomposition.

    Example:
        # Enable auto-decomposition with custom settings
        configure_auto_decomposition(
            enabled=True,
            min_confidence=0.7,
            require_confirmation=False
        )

        # Disable auto-decomposition globally
        configure_auto_decomposition(enabled=False)
    """
    global _auto_config

    if enabled is not None:
        _auto_config.enabled = enabled
    if min_confidence is not None:
        _auto_config.min_confidence = min_confidence
    if simple_task_threshold is not None:
        _auto_config.simple_task_threshold = simple_task_threshold
    if require_confirmation is not None:
        _auto_config.require_confirmation = require_confirmation
    if default_strategy is not None:
        _auto_config.default_strategy = default_strategy


def enable_auto_decomposition():
    """Enable automatic task decomposition globally."""
    global _auto_config
    _auto_config.enabled = True


def disable_auto_decomposition():
    """Disable automatic task decomposition globally."""
    global _auto_config
    _auto_config.enabled = False
    if default_strategy is not None:
        _auto_config.default_strategy = default_strategy


def should_auto_decompose(task: str, complexity_score: int) -> bool:
    """Determine if a task should be automatically decomposed.

    Args:
        task: The task description
        complexity_score: Calculated complexity score

    Returns:
        True if the task should be auto-decomposed
    """
    config = get_auto_config()

    # Check if globally enabled
    if not config.enabled:
        return False

    # Simple length check
    if len(task) < config.max_simple_task_length:
        # Very short tasks likely don't need decomposition
        if complexity_score < config.simple_task_threshold:
            return False

    # Check complexity threshold
    return complexity_score >= config.simple_task_threshold
