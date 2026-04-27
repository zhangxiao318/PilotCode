"""Integration between orchestration system and PilotCode.

Connects the unified P-EVR orchestration layer with existing PilotCode components.
"""

from __future__ import annotations


from .adapter import MissionAdapter


class OrchestrationAdapter:
    """Adapter to integrate orchestration with PilotCode's existing systems."""

    def __init__(self, cwd: str | None = None):
        self.adapter: MissionAdapter | None = None
        self._cwd = cwd

    def initialize(self):
        """Initialize the orchestration system."""
        self.adapter = MissionAdapter(cwd=self._cwd)

    async def execute_task(
        self, task: str, context: dict = None, explore_first: bool = True, cwd: str | None = None
    ) -> dict:
        """Execute a task with unified P-EVR orchestration."""
        if not self.adapter:
            self.initialize()

        effective_cwd = cwd or self._cwd
        return await self.adapter.run(
            user_request=task,
            progress_callback=None,
            explore_first=explore_first,
            cwd=effective_cwd,
        )


def initialize_orchestration() -> OrchestrationAdapter:
    """Create and initialize a new orchestration adapter."""
    adapter = OrchestrationAdapter()
    adapter.initialize()
    return adapter
