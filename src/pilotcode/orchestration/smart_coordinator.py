"""Smart coordinator with seamless automatic task decomposition.

This module provides a thin wrapper around the unified MissionAdapter
that automatically decides when to use structured P-EVR planning.
"""

from __future__ import annotations

from typing import Any, Optional

from .adapter import MissionAdapter
from .auto_config import get_auto_config, should_auto_decompose


class SmartCoordinator:
    """Smart coordinator with automatic task decomposition.

    Uses the unified MissionAdapter for all complex tasks.
    """

    def __init__(self, config: Optional[Any] = None):
        self.adapter = MissionAdapter()
        self.config = config or get_auto_config()

    async def run(
        self,
        task: str,
        context: dict = None,
        force_decompose: Optional[bool] = None,
    ) -> dict:
        """Run a task with intelligent automatic decomposition.

        Args:
            task: The task to execute
            context: Additional context (unused, kept for API compatibility)
            force_decompose: Force decomposition (True/False) or auto (None)

        Returns:
            Execution result dict
        """
        # Determine if we should decompose
        if force_decompose is not None:
            should_decompose = force_decompose
        else:
            should_decompose = should_auto_decompose(task, complexity_score=3)

        if should_decompose:
            return await self.adapter.run(user_request=task, explore_first=True)
        else:
            # For simple tasks, run with minimal planning
            return await self.adapter.run(user_request=task, explore_first=False)


# Global instance
_smart_coordinator: SmartCoordinator | None = None


def get_smart_coordinator(config: Optional[Any] = None) -> SmartCoordinator:
    """Get global smart coordinator instance."""
    global _smart_coordinator
    if _smart_coordinator is None:
        _smart_coordinator = SmartCoordinator(config=config)
    return _smart_coordinator
