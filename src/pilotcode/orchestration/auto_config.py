"""Configuration for automatic task decomposition.

Controls when and how tasks are automatically decomposed.
No global mutable state — consumers instantiate their own AutoDecompositionConfig.
"""

from dataclasses import dataclass


@dataclass
class AutoDecompositionConfig:
    """Configuration for automatic task decomposition."""

    # Enable/disable automatic decomposition globally
    enabled: bool = True

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


def should_auto_decompose(
    task: str,
    complexity_score: int,
    config: AutoDecompositionConfig | None = None,
) -> bool:
    """Determine if a task should be automatically decomposed.

    Args:
        task: The task description
        complexity_score: Calculated complexity score
        config: AutoDecompositionConfig instance (uses default if not provided)

    Returns:
        True if the task should be auto-decomposed
    """
    if config is None:
        config = AutoDecompositionConfig()

    if not config.enabled:
        return False

    if len(task) < config.max_simple_task_length:
        if complexity_score < config.simple_task_threshold:
            return False

    return True
