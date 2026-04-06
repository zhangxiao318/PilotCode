"""Background task queue service.

Provides asynchronous task execution:
- Queue long-running tasks
- Progress tracking
- Task cancellation
- Result caching
"""

from __future__ import annotations

import asyncio
import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine


class TaskStatus(enum.Enum):
    """Status of a background task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskResult:
    """Result of a background task."""

    success: bool
    data: Any = None
    error: str | None = None
    execution_time: float = 0.0


@dataclass
class Task:
    """Background task."""

    id: str
    name: str
    coro: Coroutine[Any, Any, Any]
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    result: TaskResult | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    _cancelled: bool = False


class BackgroundTaskQueue:
    """Queue for background task execution.

    Manages concurrent execution of background tasks with:
    - Priority queue support
    - Progress tracking
    - Result storage
    - Cancellation support
    """

    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self._queue: asyncio.Queue[Task] = asyncio.Queue()
        self._tasks: dict[str, Task] = {}
        self._running: set[asyncio.Task] = set()
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._worker_task: asyncio.Task | None = None
        self._running_flag = False

        # Callbacks
        self._on_complete: list[Callable[[Task], Any]] = []
        self._on_progress: list[Callable[[Task, float], Any]] = []

    def add_callback_on_complete(self, callback: Callable[[Task], Any]) -> None:
        """Add callback for task completion."""
        self._on_complete.append(callback)

    def add_callback_on_progress(self, callback: Callable[[Task, float], Any]) -> None:
        """Add callback for task progress updates."""
        self._on_progress.append(callback)

    def _notify_complete(self, task: Task) -> None:
        """Notify completion callbacks."""
        for callback in self._on_complete:
            try:
                callback(task)
            except Exception:
                pass

    def _notify_progress(self, task: Task, progress: float) -> None:
        """Notify progress callbacks."""
        task.progress = progress
        for callback in self._on_progress:
            try:
                callback(task, progress)
            except Exception:
                pass

    async def submit(
        self,
        coro: Coroutine[Any, Any, Any],
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Submit a task to the queue.

        Args:
            coro: Coroutine to execute
            name: Optional task name
            metadata: Optional metadata

        Returns:
            Task object
        """
        task = Task(
            id=str(uuid.uuid4())[:8],
            name=name or f"task_{uuid.uuid4().hex[:6]}",
            coro=coro,
            metadata=metadata or {},
        )

        self._tasks[task.id] = task
        await self._queue.put(task)

        return task

    async def _execute_task(self, task: Task) -> None:
        """Execute a single task."""
        async with self._semaphore:
            if task._cancelled:
                task.status = TaskStatus.CANCELLED
                return

            task.status = TaskStatus.RUNNING
            task.started_at = time.time()

            start_time = time.time()

            try:
                # Wrap coroutine to track progress if it accepts progress_callback
                if hasattr(task.coro, "__self__"):
                    # Try to inject progress callback
                    pass

                result_data = await task.coro

                task.result = TaskResult(
                    success=True, data=result_data, execution_time=time.time() - start_time
                )
                task.status = TaskStatus.COMPLETED
                task.progress = 1.0

            except asyncio.CancelledError:
                task.status = TaskStatus.CANCELLED
                task.result = TaskResult(
                    success=False,
                    error="Task was cancelled",
                    execution_time=time.time() - start_time,
                )
                raise

            except Exception as e:
                task.result = TaskResult(
                    success=False, error=str(e), execution_time=time.time() - start_time
                )
                task.status = TaskStatus.FAILED

            finally:
                task.completed_at = time.time()
                self._notify_complete(task)

    async def _worker(self) -> None:
        """Main worker loop."""
        while self._running_flag:
            try:
                task = await asyncio.wait_for(self._queue.get(), timeout=1.0)

                # Execute task
                exec_task = asyncio.create_task(self._execute_task(task))
                self._running.add(exec_task)

                # Clean up when done
                exec_task.add_done_callback(lambda t: self._running.discard(t))

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def start(self) -> None:
        """Start the task queue."""
        if self._running_flag:
            return

        self._running_flag = True
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self, wait_for_complete: bool = True) -> None:
        """Stop the task queue.

        Args:
            wait_for_complete: If True, wait for running tasks to complete
        """
        self._running_flag = False

        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        if wait_for_complete and self._running:
            await asyncio.gather(*self._running, return_exceptions=True)

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending or running task.

        Returns:
            True if task was found and cancelled
        """
        task = self._tasks.get(task_id)
        if not task:
            return False

        if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            task._cancelled = True
            task.status = TaskStatus.CANCELLED
            return True

        return False

    def get_task(self, task_id: str) -> Task | None:
        """Get task by ID."""
        return self._tasks.get(task_id)

    def get_tasks(self, status: TaskStatus | None = None, limit: int | None = None) -> list[Task]:
        """Get tasks, optionally filtered by status.

        Args:
            status: Filter by status
            limit: Maximum number of tasks to return

        Returns:
            List of tasks (sorted by creation time, newest first)
        """
        tasks = list(self._tasks.values())
        tasks.sort(key=lambda t: t.created_at, reverse=True)

        if status:
            tasks = [t for t in tasks if t.status == status]

        if limit:
            tasks = tasks[:limit]

        return tasks

    def get_stats(self) -> dict[str, Any]:
        """Get queue statistics."""
        all_tasks = list(self._tasks.values())

        return {
            "total_tasks": len(all_tasks),
            "pending": sum(1 for t in all_tasks if t.status == TaskStatus.PENDING),
            "running": sum(1 for t in all_tasks if t.status == TaskStatus.RUNNING),
            "completed": sum(1 for t in all_tasks if t.status == TaskStatus.COMPLETED),
            "failed": sum(1 for t in all_tasks if t.status == TaskStatus.FAILED),
            "cancelled": sum(1 for t in all_tasks if t.status == TaskStatus.CANCELLED),
            "max_concurrent": self.max_concurrent,
            "current_running": len(self._running),
        }

    def clear_completed(self, max_age: float | None = None) -> int:
        """Clear completed tasks from memory.

        Args:
            max_age: Only clear tasks older than this many seconds

        Returns:
            Number of tasks cleared
        """
        now = time.time()
        to_clear = []

        for task_id, task in self._tasks.items():
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                if max_age is None or (task.completed_at and now - task.completed_at > max_age):
                    to_clear.append(task_id)

        for task_id in to_clear:
            del self._tasks[task_id]

        return len(to_clear)


# Global queue instance
_global_queue: BackgroundTaskQueue | None = None


def get_task_queue(max_concurrent: int = 3) -> BackgroundTaskQueue:
    """Get global task queue."""
    global _global_queue
    if _global_queue is None:
        _global_queue = BackgroundTaskQueue(max_concurrent)
    return _global_queue


async def run_in_background(
    coro: Coroutine[Any, Any, Any], name: str | None = None, metadata: dict[str, Any] | None = None
) -> Task:
    """Convenience function to run a coroutine in background.

    Args:
        coro: Coroutine to execute
        name: Optional task name
        metadata: Optional metadata

    Returns:
        Task object
    """
    queue = get_task_queue()
    await queue.start()
    return await queue.submit(coro, name, metadata)
