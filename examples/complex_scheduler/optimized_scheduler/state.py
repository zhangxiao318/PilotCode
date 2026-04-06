"""State management - Pluggable backends, async persistence."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime, timedelta
from collections import defaultdict

from .models import TaskInstance, TaskStatus


class StateBackend(ABC):
    """Abstract state backend."""

    @abstractmethod
    async def save(self, instance: TaskInstance) -> bool:
        """Save task instance."""
        pass

    @abstractmethod
    async def get(self, instance_id: str) -> Optional[TaskInstance]:
        """Get task by ID."""
        pass

    @abstractmethod
    async def get_by_status(self, status: TaskStatus) -> list[TaskInstance]:
        """Get all tasks with given status."""
        pass

    @abstractmethod
    async def delete(self, instance_id: str) -> bool:
        """Delete task."""
        pass

    @abstractmethod
    async def cleanup(self, before: datetime) -> int:
        """Clean up old completed tasks. Returns count deleted."""
        pass


class MemoryBackend(StateBackend):
    """In-memory state backend (fast, not persistent)."""

    def __init__(self):
        self._tasks: dict[str, TaskInstance] = {}
        self._by_status: dict[TaskStatus, set[str]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def save(self, instance: TaskInstance) -> bool:
        async with self._lock:
            # Update status index
            if instance.instance_id in self._tasks:
                old = self._tasks[instance.instance_id]
                self._by_status[old.status].discard(instance.instance_id)

            self._tasks[instance.instance_id] = instance
            self._by_status[instance.status].add(instance.instance_id)
            return True

    async def get(self, instance_id: str) -> Optional[TaskInstance]:
        async with self._lock:
            return self._tasks.get(instance_id)

    async def get_by_status(self, status: TaskStatus) -> list[TaskInstance]:
        async with self._lock:
            ids = list(self._by_status.get(status, []))
            return [self._tasks[i] for i in ids if i in self._tasks]

    async def delete(self, instance_id: str) -> bool:
        async with self._lock:
            if instance_id in self._tasks:
                status = self._tasks[instance_id].status
                del self._tasks[instance_id]
                self._by_status[status].discard(instance_id)
                return True
            return False

    async def cleanup(self, before: datetime) -> int:
        async with self._lock:
            to_delete = [
                iid
                for iid, task in self._tasks.items()
                if task.is_terminal and task.completed_at and task.completed_at < before
            ]
            for iid in to_delete:
                status = self._tasks[iid].status
                del self._tasks[iid]
                self._by_status[status].discard(iid)
            return len(to_delete)


class StateManager:
    """High-level state management with caching and persistence."""

    def __init__(
        self,
        backend: StateBackend | None = None,
        cleanup_interval: float = 300.0,  # 5 minutes
        retention_hours: float = 24.0,
    ):
        self.backend = backend or MemoryBackend()
        self.cleanup_interval = cleanup_interval
        self.retention_hours = retention_hours

        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None

        # Stats
        self._stats = {
            "saved": 0,
            "retrieved": 0,
            "cleaned": 0,
        }

    async def start(self) -> None:
        """Start background tasks."""
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        """Stop background tasks."""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def save(self, instance: TaskInstance) -> bool:
        """Save task instance."""
        result = await self.backend.save(instance)
        if result:
            self._stats["saved"] += 1
        return result

    async def get(self, instance_id: str) -> Optional[TaskInstance]:
        """Get task by ID."""
        result = await self.backend.get(instance_id)
        if result:
            self._stats["retrieved"] += 1
        return result

    async def get_by_status(self, status: TaskStatus) -> list[TaskInstance]:
        """Get all tasks with given status."""
        return await self.backend.get_by_status(status)

    async def delete(self, instance_id: str) -> bool:
        """Delete task."""
        return await self.backend.delete(instance_id)

    def get_stats(self) -> dict:
        """Get state manager statistics."""
        return dict(self._stats)

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup of old tasks."""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)

                cutoff = datetime.utcnow() - timedelta(hours=self.retention_hours)
                cleaned = await self.backend.cleanup(cutoff)
                self._stats["cleaned"] += cleaned

            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(60.0)
