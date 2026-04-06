"""Task handler registry - Decouples task definitions from handlers."""

from __future__ import annotations

import asyncio
import inspect
from typing import Callable, Any, TypeVar
from functools import wraps

from .models import TaskInstance, TaskResult

F = TypeVar("F", bound=Callable[..., Any])


class TaskRegistry:
    """Global task handler registry.

    Decouples task definitions (serializable) from handlers (callables).
    Handlers are registered by path and looked up at execution time.
    """

    _instance: TaskRegistry | None = None

    def __new__(cls) -> TaskRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._handlers: dict[str, Callable] = {}
        return cls._instance

    def register(
        self, path: str, handler: Callable, metadata: dict[str, Any] | None = None
    ) -> Callable:
        """Register a task handler.

        Args:
            path: Unique identifier for this handler (e.g., "tasks.email.send")
            handler: Callable to execute
            metadata: Optional metadata about the handler
        """
        if path in self._handlers:
            raise ValueError(f"Handler already registered: {path}")

        self._handlers[path] = {
            "handler": handler,
            "metadata": metadata or {},
            "is_async": asyncio.iscoroutinefunction(handler),
        }
        return handler

    def get(self, path: str) -> dict[str, Any] | None:
        """Get handler info by path."""
        return self._handlers.get(path)

    async def execute(self, path: str, instance: TaskInstance, **kwargs: Any) -> TaskResult:
        """Execute a handler by path.

        Args:
            path: Handler path
            instance: Task instance being executed
            **kwargs: Additional arguments from task definition

        Returns:
            TaskResult with execution outcome
        """
        info = self._handlers.get(path)
        if info is None:
            return TaskResult(
                success=False,
                error_message=f"Handler not found: {path}",
                error_type="HandlerNotFound",
            )

        handler = info["handler"]
        is_async = info["is_async"]

        try:
            if is_async:
                result = await handler(instance, **kwargs)
            else:
                # Run sync handler in thread pool
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, lambda: handler(instance, **kwargs)  # Default executor
                )

            return TaskResult(
                success=True,
                data=result,
            )

        except Exception as e:
            error_type = type(e).__name__
            return TaskResult(
                success=False,
                error_message=str(e),
                error_type=error_type,
            )

    def list_handlers(self) -> list[str]:
        """List all registered handler paths."""
        return list(self._handlers.keys())

    def unregister(self, path: str) -> bool:
        """Unregister a handler."""
        if path in self._handlers:
            del self._handlers[path]
            return True
        return False


# Decorator for registering handlers
def task_handler(path: str | None = None, **metadata: Any) -> Callable[[F], F]:
    """Decorator to register a function as a task handler.

    Usage:
        @task_handler("tasks.email.send")
        async def send_email(instance: TaskInstance, to: str, subject: str):
            ...
    """

    def decorator(func: F) -> F:
        handler_path = path or f"{func.__module__}.{func.__name__}"
        registry = TaskRegistry()
        registry.register(handler_path, func, metadata)
        return func

    return decorator


# Global registry accessor
def get_registry() -> TaskRegistry:
    """Get the global task registry."""
    return TaskRegistry()
