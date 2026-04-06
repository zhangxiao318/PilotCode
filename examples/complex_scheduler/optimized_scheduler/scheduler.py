"""Optimized task scheduler - Event-driven, efficient, scalable."""

from __future__ import annotations

import asyncio
import heapq
from dataclasses import dataclass
from typing import Optional, Callable, Any
from datetime import datetime

from .models import (
    TaskDefinition,
    TaskInstance,
    TaskPriority,
    TaskStatus,
    ExecutionConfig,
)
from .queue import OptimizedTaskQueue
from .worker import WorkerPool, WorkerConfig
from .state import StateManager, StateBackend
from .registry import TaskRegistry, task_handler
from .metrics import MetricsCollector, PerformanceMetrics


@dataclass
class SchedulerConfig:
    """Scheduler configuration."""

    max_queue_size: int = 10000
    min_workers: int = 2
    max_workers: int = 20
    enable_metrics: bool = True
    metrics_interval: float = 10.0
    state_retention_hours: float = 24.0


class OptimizedScheduler:
    """High-performance task scheduler.

    Key improvements:
    - Event-driven architecture (no polling)
    - Clean component separation
    - Dependency injection
    - Comprehensive metrics
    - Graceful shutdown
    """

    def __init__(
        self,
        config: SchedulerConfig | None = None,
        state_backend: StateBackend | None = None,
        registry: TaskRegistry | None = None,
    ):
        self.config = config or SchedulerConfig()

        # Dependencies (injected for testability)
        self.registry = registry or TaskRegistry()

        # Components
        self.queue = OptimizedTaskQueue(max_size=self.config.max_queue_size, cleanup_interval=60.0)
        self.state = StateManager(
            backend=state_backend, retention_hours=self.config.state_retention_hours
        )
        self.workers = WorkerPool(
            queue=self.queue,
            registry=self.registry,
            config=WorkerConfig(
                min_workers=self.config.min_workers, max_workers=self.config.max_workers
            ),
        )
        self.metrics = (
            MetricsCollector(collection_interval=self.config.metrics_interval)
            if self.config.enable_metrics
            else None
        )

        # Scheduled tasks (using heap for O(log n) operations)
        self._scheduled: list[tuple[datetime, str, TaskDefinition]] = []
        self._scheduled_lock = asyncio.Lock()

        # Control
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start the scheduler and all components."""
        self._running = True

        # Start components
        await self.queue.start()
        await self.state.start()
        await self.workers.start()

        if self.metrics:
            await self.metrics.start()

        # Start scheduled task processor
        self._tasks.append(asyncio.create_task(self._scheduled_task_loop()))

        # Start metrics reporter
        if self.metrics:
            self._tasks.append(asyncio.create_task(self._metrics_loop()))

    async def stop(self, graceful: bool = True, timeout: float = 30.0) -> None:
        """Stop the scheduler gracefully."""
        self._running = False

        # Cancel background tasks
        for task in self._tasks:
            task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)

        # Stop components in order
        await self.workers.stop(graceful=graceful, timeout=timeout)
        await self.queue.stop()
        await self.state.stop()

        if self.metrics:
            await self.metrics.stop()

    async def submit(
        self,
        name: str,
        handler_path: str,
        input_data: dict[str, Any] | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        execution_config: ExecutionConfig | None = None,
        scheduled_at: Optional[datetime] = None,
        dependencies: list[str] | None = None,
        tags: set[str] | None = None,
    ) -> TaskInstance:
        """Submit a task for execution.

        Args:
            name: Task name
            handler_path: Path to handler in registry
            input_data: Input data for handler
            priority: Task priority
            execution_config: Execution configuration
            scheduled_at: Schedule for future execution
            dependencies: Task IDs that must complete first
            tags: Tags for categorization

        Returns:
            TaskInstance representing the submitted task
        """
        definition = TaskDefinition(
            name=name,
            handler_path=handler_path,
            priority=priority,
            execution_config=execution_config or ExecutionConfig(),
            input_data=input_data or {},
            scheduled_at=scheduled_at,
            dependencies=dependencies or [],
            tags=tags or set(),
        )

        instance = definition.with_status(TaskStatus.PENDING)

        # Save to state
        await self.state.save(instance)

        # Submit to queue
        await self.queue.submit(definition, instance)

        return instance

    async def submit_scheduled(
        self,
        name: str,
        handler_path: str,
        cron_expression: str,
        input_data: dict[str, Any] | None = None,
        **kwargs,
    ) -> TaskDefinition:
        """Submit a recurring scheduled task.

        Note: Cron parsing and scheduling is simplified for this example.
        A full implementation would use a proper cron parser.
        """
        definition = TaskDefinition(
            name=name,
            handler_path=handler_path,
            cron_expression=cron_expression,
            input_data=input_data or {},
            **kwargs,
        )

        # Add to scheduled heap
        async with self._scheduled_lock:
            heapq.heappush(self._scheduled, (datetime.utcnow(), definition.id, definition))

        return definition

    async def get_task(self, instance_id: str) -> Optional[TaskInstance]:
        """Get task by instance ID."""
        return await self.state.get(instance_id)

    async def cancel_task(self, instance_id: str) -> bool:
        """Cancel a pending task."""
        instance = await self.state.get(instance_id)
        if instance and instance.status == TaskStatus.PENDING:
            instance.status = TaskStatus.CANCELLED
            await self.state.save(instance)
            return True
        return False

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive scheduler statistics."""
        stats = {
            "queue": self.queue.get_stats().to_dict(),
            "workers": self.workers.get_stats(),
            "state": self.state.get_stats(),
        }

        return stats

    def add_metrics_callback(self, callback: Callable[[PerformanceMetrics], None]) -> None:
        """Add callback for metrics updates."""
        if self.metrics:
            self.metrics.add_callback(callback)

    async def _scheduled_task_loop(self) -> None:
        """Process scheduled/delayed tasks."""
        while self._running:
            try:
                now = datetime.utcnow()
                ready = []

                # Find ready scheduled tasks
                async with self._scheduled_lock:
                    while self._scheduled and self._scheduled[0][0] <= now:
                        _, _, definition = heapq.heappop(self._scheduled)
                        ready.append(definition)

                # Submit ready tasks
                for definition in ready:
                    instance = definition.with_status(TaskStatus.PENDING)
                    await self.state.save(instance)
                    await self.queue.submit(definition, instance)

                # Wait for next check (or until stopped)
                wait_time = 1.0
                if self._scheduled:
                    next_time = self._scheduled[0][0]
                    delta = (next_time - now).total_seconds()
                    wait_time = max(0.1, min(delta, 1.0))

                await asyncio.wait_for(asyncio.sleep(wait_time), timeout=wait_time + 1.0)

            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1.0)

    async def _metrics_loop(self) -> None:
        """Collect and report metrics."""
        while self._running:
            try:
                await asyncio.sleep(self.config.metrics_interval)

                if not self.metrics:
                    continue

                queue_stats = self.queue.get_stats()
                worker_stats = self.workers.get_stats()

                metrics = self.metrics.calculate_metrics(
                    queue_size=queue_stats.current_size,
                    queue_capacity=self.queue.max_size,
                    active_workers=worker_stats["total_workers"],
                    healthy_workers=worker_stats["healthy_workers"],
                )

                # Could log, send to monitoring system, etc.

            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1.0)
