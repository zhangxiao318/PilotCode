"""Task Queue - ISSUES: Thread-safety, performance, memory leaks."""

import heapq
import asyncio
from collections import deque
from typing import Optional
from dataclasses import dataclass

from .task import Task, TaskPriority, TaskStatus


@dataclass(order=True)
class PrioritizedItem:
    """ISSUE: Doesn't handle same priority well."""

    priority: int
    task: Task = None  # type: ignore

    def __post_init__(self):
        if self.task is None:
            raise ValueError("Task required")


class TaskQueue:
    """Priority task queue - ISSUES: Not thread-safe, blocking operations."""

    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        # ISSUE: Using list for queue - O(n) operations
        self._queue: list[PrioritizedItem] = []

        # ISSUE: Separate queues not integrated
        self._delay_queue: deque[Task] = deque()
        self._dead_letter_queue: list[Task] = []

        # ISSUE: No proper synchronization
        self._lock = asyncio.Lock()
        self._not_empty = asyncio.Condition(self._lock)
        self._not_full = asyncio.Condition(self._lock)

        # ISSUE: Loading all into memory
        self._task_map: dict[str, Task] = {}

        self._stats = {
            "submitted": 0,
            "completed": 0,
            "failed": 0,
        }

    async def submit(self, task: Task) -> bool:
        """Submit task - ISSUE: Blocking, no backpressure handling."""
        async with self._not_full:
            if len(self._queue) >= self.max_size:
                # ISSUE: Just waits, no timeout
                await self._not_full.wait()

            # ISSUE: heapq not thread-safe
            heapq.heappush(
                self._queue,
                PrioritizedItem(
                    priority=-task.priority.value, task=task  # Higher priority = lower number
                ),
            )

            self._task_map[task.id] = task
            self._stats["submitted"] += 1

            # ISSUE: Signal while holding lock
            self._not_empty.notify()
            return True

    async def get(self, timeout: Optional[float] = None) -> Optional[Task]:
        """Get next task - ISSUE: Priority inversion possible."""
        async with self._not_empty:
            if not self._queue:
                # ISSUE: No timeout handling
                await self._not_empty.wait()

            if not self._queue:
                return None

            # ISSUE: heapq.heappop not thread-safe
            item = heapq.heappop(self._queue)
            task = item.task
            task.status = TaskStatus.RUNNING

            # ISSUE: Signal while holding lock
            self._not_full.notify()
            return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """ISSUE: Not async, blocks event loop."""
        return self._task_map.get(task_id)

    async def complete(self, task: Task, result: any = None) -> None:
        """Mark task complete - ISSUE: No cleanup of _task_map."""
        task.status = TaskStatus.COMPLETED
        task.result = result
        task.completed_at = __import__("datetime").datetime.now()
        self._stats["completed"] += 1
        # ISSUE: Memory leak - task still in _task_map

    async def fail(self, task: Task, error: str) -> None:
        """Mark task failed - ISSUE: Complex retry logic inline."""
        task.retry_count += 1

        if task.retry_count < task.max_retries:
            task.status = TaskStatus.RETRYING
            # ISSUE: Blocking sleep
            await asyncio.sleep(task.retry_delay * (2**task.retry_count))
            await self.submit(task)
        else:
            task.status = TaskStatus.FAILED
            task.error = error
            self._stats["failed"] += 1
            # ISSUE: Add to DLQ without limit
            self._dead_letter_queue.append(task)

    def get_stats(self) -> dict:
        """ISSUE: Returns internal dict."""
        return self._stats

    def get_dead_letter_tasks(self) -> list[Task]:
        """ISSUE: No pagination."""
        return self._dead_letter_queue.copy()

    def __len__(self) -> int:
        return len(self._queue)
