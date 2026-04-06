"""Initial tests - ISSUES: Incomplete, poor coverage."""

import pytest
import asyncio
from distributed_scheduler import Task, TaskPriority, TaskQueue, TaskScheduler


class TestTask:
    """Basic task tests."""

    def test_task_creation(self):
        """ISSUE: Only tests happy path."""
        task = Task(name="test")
        assert task.name == "test"
        assert task.priority == TaskPriority.NORMAL


class TestTaskQueue:
    """Queue tests - ISSUES: No concurrency tests."""

    @pytest.mark.asyncio
    async def test_submit_and_get(self):
        """ISSUE: Single-threaded test only."""
        queue = TaskQueue()
        task = Task(name="test")

        await queue.submit(task)
        retrieved = await queue.get()

        assert retrieved.id == task.id

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        """ISSUE: Incomplete test."""
        queue = TaskQueue()

        low = Task(name="low", priority=TaskPriority.LOW)
        high = Task(name="high", priority=TaskPriority.HIGH)

        await queue.submit(low)
        await queue.submit(high)

        # Should get high priority first
        first = await queue.get()
        assert first.name == "high"


class TestScheduler:
    """Scheduler tests - ISSUES: No integration tests."""

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """ISSUE: Doesn't verify clean shutdown."""
        scheduler = TaskScheduler()
        await scheduler.start()
        await scheduler.stop()
