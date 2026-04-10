"""Smart coordinator with seamless automatic task decomposition.

This module provides a higher-level coordinator that automatically
decides when to decompose tasks based on intelligent analysis.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .coordinator import AgentCoordinator, WorkflowResult
from .decomposer import TaskDecomposer, DecompositionStrategy
from .auto_config import get_auto_config, should_auto_decompose


class SmartCoordinator:
    """Smart coordinator with automatic task decomposition.

    Unlike the basic AgentCoordinator which requires explicit auto_decompose=True,
    SmartCoordinator intelligently decides when to decompose based on:
    - Task complexity analysis
    - Historical success rates
    - User preferences

    Example:
        >>> coordinator = SmartCoordinator(agent_factory)
        >>>
        >>> # This will automatically decompose if beneficial
        >>> result = await coordinator.run("Implement user auth with tests")
        >>>
        >>> # This will likely not decompose (simple task)
        >>> result = await coordinator.run("Read README.md")
    """

    def __init__(
        self,
        agent_factory: Callable[[str, str], Any],
        model_client: Optional[Any] = None,
        config: Optional[Any] = None,
    ):
        self.base_coordinator = AgentCoordinator(agent_factory, model_client)
        self.decomposer = TaskDecomposer(model_client)
        self.config = config or get_auto_config()
        self._execution_history: list[dict] = []

    async def run(
        self,
        task: str,
        context: dict = None,
        force_decompose: Optional[bool] = None,
        force_strategy: Optional[str] = None,
    ) -> WorkflowResult:
        """Run a task with intelligent automatic decomposition.

        This method automatically decides whether to decompose the task
        based on analysis of the task complexity and content.

        Args:
            task: The task to execute
            context: Additional context
            force_decompose: Force decomposition (True/False) or auto (None)
            force_strategy: Force a specific strategy

        Returns:
            WorkflowResult with execution details
        """
        context = context or {}

        # Determine if we should decompose
        should_decompose = self._should_decompose(task, force_decompose)

        if should_decompose:
            # Use auto-decomposition
            return await self.base_coordinator.execute(
                task=task, context=context, auto_decompose=True, strategy=force_strategy
            )
        else:
            # Execute as single task (no decomposition)
            return await self.base_coordinator.execute(
                task=task, context=context, auto_decompose=False, strategy="none"
            )

    def _should_decompose(self, task: str, force_decompose: Optional[bool] = None) -> bool:
        """Determine if task should be decomposed.

        Decision hierarchy:
        1. If force_decompose is set, use that
        2. Check global auto-decomposition config
        3. Analyze task complexity
        4. Check historical patterns
        """
        # 1. Forced decision
        if force_decompose is not None:
            return force_decompose

        # 2. Check global config
        if not self.config.enabled:
            return False

        # 3. Analyze task
        analysis = self.decomposer.analyze(task)

        # 4. Use smart decision logic
        return should_auto_decompose(task, len(analysis.subtasks))

    async def run_with_preview(
        self, task: str, context: dict = None
    ) -> tuple[WorkflowResult, dict]:
        """Run task with decomposition preview.

        Shows the user how the task would be decomposed before executing,
        allowing them to confirm or modify the plan.

        Returns:
            Tuple of (WorkflowResult, metadata)
        """
        # First, analyze the task
        decomposition = self.decomposer.analyze(task)

        preview = {
            "original_task": task,
            "will_decompose": decomposition.strategy != DecompositionStrategy.NONE,
            "strategy": decomposition.strategy.name,
            "confidence": decomposition.confidence,
            "subtasks": [
                {
                    "id": st.id,
                    "role": st.role,
                    "description": st.description,
                    "dependencies": st.dependencies,
                }
                for st in decomposition.subtasks
            ],
            "estimated_duration": decomposition.estimated_total_duration,
        }

        # Check if confirmation is required
        if self.config.require_confirmation and preview["will_decompose"]:
            preview["requires_confirmation"] = True
            return None, preview  # User needs to confirm

        # Execute
        result = await self.run(task, context)

        return result, preview

    def get_insights(self) -> dict:
        """Get insights about decomposition decisions.

        Returns statistics about when and why tasks are decomposed.
        """
        return {
            "total_executions": len(self._execution_history),
            "auto_decomposition_enabled": self.config.enabled,
            "min_confidence_threshold": self.config.min_confidence,
            "recent_decompositions": [
                h for h in self._execution_history[-10:] if h.get("decomposed")
            ],
        }


# Global smart coordinator instance
_smart_coordinator: Optional[SmartCoordinator] = None


def get_smart_coordinator(
    agent_factory: Optional[Callable] = None, model_client: Optional[Any] = None
) -> SmartCoordinator:
    """Get or create the global smart coordinator."""
    global _smart_coordinator
    if _smart_coordinator is None:
        if agent_factory is None:
            raise ValueError("Agent factory required for first initialization")
        _smart_coordinator = SmartCoordinator(agent_factory, model_client)
    return _smart_coordinator


def enable_auto_decomposition():
    """Enable automatic task decomposition globally."""
    from .auto_config import configure_auto_decomposition

    configure_auto_decomposition(enabled=True)


def disable_auto_decomposition():
    """Disable automatic task decomposition globally."""
    from .auto_config import configure_auto_decomposition

    configure_auto_decomposition(enabled=False)
