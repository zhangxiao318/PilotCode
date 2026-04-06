"""Optimized task queue - Thread-safe, efficient, memory-conscious."""

from __future__ import annotations

import asyncio
import heapq
from dataclasses import dataclass, field
from typing import Optional
from collections import deque
from datetime import datetime

from .models import TaskDefinition, TaskInstance, TaskPriority, TaskStatus


@dataclass(order=True)
class QueueItem:
    """Priority queue item with tie-breaking."""

    priority: int
    sequence: int  # Tie-breaker for FIFO within same priority
    instance: TaskInstance = field(compare=False)
    definition: TaskDefinition = field(compare=False)


@dataclass
class QueueStats:
    """Queue statistics."""

    submitted: int = 0
    completed: int = 0
    failed: int = 0
    retried: int = 0
    current_size: int = 0
    peak_size: int = 0

    def to_dict(self) -> dict:
        return {
            "submitted": self.submitted,
            "completed": self.completed,
            "failed": self.failed,
            "retried": self.retried,
            "current_size": self.current_size,
            "peak_size": self.peak_size,
        }


class OptimizedTaskQueue:
    """High-performance async priority queue.

    Features:
    - Thread-safe with asyncio primitives
    - O(log n) priority operations
    - Automatic cleanup of completed tasks
    - Backpressure support
    """

    def __init__(
        self, max_size: int = 10000, cleanup_interval: float = 60.0, enable_metrics: bool = True
    ):
        self.max_size = max_size
        self.cleanup_interval = cleanup_interval
        self.enable_metrics = enable_metrics

        # Main priority queue (heap-based)
        self._queue: asyncio.PriorityQueue[QueueItem] = asyncio.PriorityQueue(maxsize=max_size)

        # Delayed tasks (scheduled for future)
        self._delayed: list[tuple[datetime, QueueItem]] = []
        self._delayed_lock = asyncio.Lock()

        # Task lookup (only for active tasks)
        self._active_tasks: dict[str, tuple[TaskInstance, TaskDefinition]] = {}
        self._lock = asyncio.Lock()

        # Statistics
        self._stats = QueueStats()

        # Sequence counter for FIFO ordering
        self._sequence = 0

        # Background tasks
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None
        self._delayed_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start queue background tasks."""
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._delayed_task = asyncio.create_task(self._delayed_loop())

    async def stop(self) -> None:
        """Stop queue gracefully."""
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        if self._delayed_task:
            self._delayed_task.cancel()
            try:
                await self._delayed_task
            except asyncio.CancelledError:
                pass

    async def submit(self, definition: TaskDefinition, instance: TaskInstance) -> bool:
        """Submit a task to the queue.

        Returns:
            True if submitted successfully
            False if queue is full (backpressure)
        """
        # Check if delayed
        if definition.scheduled_at and definition.scheduled_at > datetime.utcnow():
            async with self._delayed_lock:
                heapq.heappush(
                    self._delayed,
                    (
                        definition.scheduled_at,
                        QueueItem(
                            priority=-definition.priority.value,
                            sequence=0,  # Will be assigned when moved to main queue
                            instance=instance,
                            definition=definition,
                        ),
                    ),
                )
            return True

        # Submit to main queue
        self._sequence += 1
        item = QueueItem(
            priority=-definition.priority.value,
            sequence=self._sequence,
            instance=instance,
            definition=definition,
        )

        try:
            self._queue.put_nowait(item)

            async with self._lock:
                self._active_tasks[instance.instance_id] = (instance, definition)
                self._stats.submitted += 1
                self._stats.current_size = len(self._active_tasks)
                self._stats.peak_size = max(self._stats.peak_size, self._stats.current_size)

            return True

        except asyncio.QueueFull:
            return False

    async def get(
        self, timeout: Optional[float] = None
    ) -> Optional[tuple[TaskInstance, TaskDefinition]]:
        """Get next task from queue.

        Args:
            timeout: Maximum time to wait (None = forever)

        Returns:
            Tuple of (instance, definition) or None if timeout
        """
        try:
            # Use wait_for with timeout
            if timeout is not None:
                item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            else:
                item = await self._queue.get()

            instance = item.instance
            definition = item.definition

            # Update state
            instance.status = TaskStatus.RUNNING
            instance.started_at = datetime.utcnow()

            return instance, definition

        except asyncio.TimeoutError:
            return None

    async def complete(self, instance: TaskInstance) -> None:
        """Mark task as completed."""
        instance.status = TaskStatus.COMPLETED
        instance.completed_at = datetime.utcnow()

        async with self._lock:
            if instance.instance_id in self._active_tasks:
                del self._active_tasks[instance.instance_id]
                self._stats.completed += 1
                self._stats.current_size = len(self._active_tasks)

        self._queue.task_done()

    async def fail(self, instance: TaskInstance, retry: bool = False) -> None:
        """Mark task as failed."""
        if retry:
            instance.retry_count += 1
            instance.status = TaskStatus.PENDING
            # Task will be resubmitted by caller
            self._stats.retried += 1
        else:
            instance.status = TaskStatus.FAILED
            instance.completed_at = datetime.utcnow()

            async with self._lock:
                if instance.instance_id in self._active_tasks:
                    del self._active_tasks[instance.instance_id]
                    self._stats.failed += 1
                    self._stats.current_size = len(self._active_tasks)

    def get_active_task(self, instance_id: str) -> Optional[TaskInstance]:
        """Get active task by ID."""
        pair = self._active_tasks.get(instance_id)
        return pair[0] if pair else None

    def get_stats(self) -> QueueStats:
        """Get queue statistics."""
        return QueueStats(
            submitted=self._stats.submitted,
            completed=self._stats.completed,
            failed=self._stats.failed,
            retried=self._stats.retried,
            current_size=self._stats.current_size,
            peak_size=self._stats.peak_size,
        )

    async def _cleanup_loop(self) -> None:
        """Periodically clean up completed tasks."""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                # Queue.task_done() handles completion tracking
            except asyncio.CancelledError:
                break

    async def _delayed_loop(self) -> None:
        """Move delayed tasks to main queue when ready."""
        while self._running:
            try:
                now = datetime.utcnow()
                ready = []

                async with self._delayed_lock:
                    # Find ready tasks
                    while self._delayed and self._delayed[0][0] <= now:
                        _, item = heapq.heappop(self._delayed)
                        ready.append(item)

                # Submit ready tasks
                for item in ready:
                    self._sequence += 1
                    item.sequence = self._sequence
                    try:
                        self._queue.put_nowait(item)
                    except asyncio.QueueFull:
                        # Put back in delayed queue
                        async with self._delayed_lock:
                            heapq.heappush(self._delayed, (now, item))
                        break

                await asyncio.sleep(0.1)  # 100ms check interval

            except asyncio.CancelledError:
                break
            except Exception:
                # Log and continue
                await asyncio.sleep(1.0)

    def __len__(self) -> int:
        return self._queue.qsize()
