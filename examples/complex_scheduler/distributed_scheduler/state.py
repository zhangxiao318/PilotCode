"""State Manager - ISSUES: No persistence, memory only, race conditions."""

import asyncio
from typing import Optional
from collections import defaultdict
from datetime import datetime, timedelta

from .task import Task, TaskStatus


class StateManager:
    """Task state management - ISSUES: Not persistent, memory leaks."""
    
    def __init__(self, retention_hours: float = 24.0):
        self.retention_hours = retention_hours
        
        # ISSUE: All in memory, no persistence
        self._tasks: dict[str, Task] = {}
        self._history: dict[str, list[dict]] = defaultdict(list)
        
        # ISSUE: Simple counters, no time-series
        self._counters = defaultdict(int)
        
        # ISSUE: No cleanup task
        self._last_cleanup = datetime.now()
    
    async def track_task(self, task: Task) -> None:
        """Track task - ISSUE: No validation."""
        self._tasks[task.id] = task
        self._counters['total_tracked'] += 1
        
        # ISSUE: Stores full history in memory
        self._history[task.id].append({
            'status': task.status.value,
            'timestamp': datetime.now().isoformat(),
        })
    
    async def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        metadata: Optional[dict] = None
    ) -> None:
        """Update task status - ISSUE: Race condition possible."""
        if task_id not in self._tasks:
            return
        
        # ISSUE: Not atomic
        task = self._tasks[task_id]
        task.status = status
        
        self._history[task_id].append({
            'status': status.value,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {},
        })
        
        self._counters[f'status_{status.value}'] += 1
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        return self._tasks.get(task_id)
    
    def get_history(self, task_id: str) -> list[dict]:
        """ISSUE: No pagination."""
        return list(self._history.get(task_id, []))
    
    def get_stats(self) -> dict:
        """ISSUE: Expensive calculation."""
        stats = dict(self._counters)
        
        # ISSUE: Linear scan
        status_counts = defaultdict(int)
        for task in self._tasks.values():
            status_counts[task.status.value] += 1
        
        stats['by_status'] = dict(status_counts)
        stats['total_tasks'] = len(self._tasks)
        
        return stats
    
    def get_tasks_by_status(self, status: TaskStatus) -> list[Task]:
        """ISSUE: Linear scan every time."""
        return [t for t in self._tasks.values() if t.status == status]
    
    async def cleanup(self) -> int:
        """Cleanup old tasks - ISSUE: Blocks event loop."""
        cutoff = datetime.now() - timedelta(hours=self.retention_hours)
        removed = 0
        
        # ISSUE: Modifying dict while iterating
        for task_id in list(self._tasks.keys()):
            task = self._tasks[task_id]
            if task.completed_at and task.completed_at < cutoff:
                del self._tasks[task_id]
                del self._history[task_id]
                removed += 1
        
        self._last_cleanup = datetime.now()
        return removed
