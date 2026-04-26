"""Declarative cleanup pipeline for session lifecycle management.

Inspired by OpenCode's Effect.ensuring(cleanup) — guarantees that registered
callbacks run regardless of success, failure, or cancellation.
"""

from __future__ import annotations

import inspect
import logging
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

CleanupCallback = Callable[[], Awaitable[None] | None]


class SessionCleanup:
    """Context manager that executes registered cleanup callbacks on exit.

    Callbacks are executed in LIFO order (reverse registration), matching
    the natural nesting of resource acquisition.  Each callback is wrapped
    in its own try/except so that one failing callback does not prevent
    the others from running.

    Supports both sync and async callbacks.

    Example:
        async with SessionCleanup() as cleanup:
            cleanup.on_cleanup(lambda: engine.add_tool_result(...))
            cleanup.on_cleanup(lambda: snapshot.commit())
            await run_worker()
    """

    def __init__(self):
        self._callbacks: list[CleanupCallback] = []

    def on_cleanup(self, fn: CleanupCallback) -> None:
        """Register a callback to be executed on context exit."""
        self._callbacks.append(fn)

    async def cleanup(self) -> None:
        """Execute all registered callbacks in reverse order."""
        for fn in reversed(self._callbacks):
            try:
                result = fn()
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception("Cleanup callback failed")

    async def __aenter__(self) -> SessionCleanup:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.cleanup()
