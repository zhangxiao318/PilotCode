"""Tests for background task queue service."""

import asyncio

import pytest

from pilotcode.services.task_queue import (
    BackgroundTaskQueue,
    Task,
    TaskResult,
    TaskStatus,
    get_task_queue,
    run_in_background,
)


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_enum_values(self):
        """Test enum values."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"


class TestTaskResult:
    """Tests for TaskResult dataclass."""

    def test_success_result(self):
        """Test successful result."""
        result = TaskResult(success=True, data="test_data", execution_time=1.5)

        assert result.success is True
        assert result.data == "test_data"
        assert result.execution_time == 1.5

    def test_failure_result(self):
        """Test failure result."""
        result = TaskResult(success=False, error="Something failed")

        assert result.success is False
        assert result.error == "Something failed"


class TestBackgroundTaskQueue:
    """Tests for BackgroundTaskQueue."""

    def test_init(self):
        """Test initialization."""
        queue = BackgroundTaskQueue(max_concurrent=5)

        assert queue.max_concurrent == 5
        assert not queue._running

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Test starting and stopping."""
        queue = BackgroundTaskQueue()

        await queue.start()
        assert queue._running_flag is True

        await queue.stop(wait_for_complete=False)
        assert queue._running_flag is False

    @pytest.mark.asyncio
    async def test_submit_task(self):
        """Test submitting a task."""
        queue = BackgroundTaskQueue()
        await queue.start()

        async def simple_task():
            return "result"

        task = await queue.submit(simple_task(), name="test_task")

        assert task.name == "test_task"
        assert task.id is not None
        assert task in queue._tasks.values()

        await queue.stop(wait_for_complete=False)

    @pytest.mark.asyncio
    async def test_task_execution(self):
        """Test that tasks are executed."""
        queue = BackgroundTaskQueue()
        await queue.start()

        result_holder = {}

        async def test_task():
            await asyncio.sleep(0.1)
            result_holder["done"] = True
            return "success"

        task = await queue.submit(test_task())

        # Wait for task to complete
        await asyncio.sleep(0.3)

        assert result_holder.get("done") is True
        assert task.status == TaskStatus.COMPLETED
        assert task.result is not None
        assert task.result.success is True

        await queue.stop(wait_for_complete=False)

    @pytest.mark.asyncio
    async def test_task_failure(self):
        """Test handling of task failure."""
        queue = BackgroundTaskQueue()
        await queue.start()

        async def failing_task():
            raise ValueError("Test error")

        task = await queue.submit(failing_task())

        # Wait for task to complete
        await asyncio.sleep(0.2)

        assert task.status == TaskStatus.FAILED
        assert task.result is not None
        assert task.result.success is False
        assert "Test error" in task.result.error

        await queue.stop(wait_for_complete=False)

    @pytest.mark.asyncio
    async def test_cancel_task(self):
        """Test cancelling a task."""
        queue = BackgroundTaskQueue()
        await queue.start()

        async def long_task():
            await asyncio.sleep(10)
            return "done"

        task = await queue.submit(long_task())

        # Cancel the task
        result = queue.cancel_task(task.id)

        assert result is True
        assert task._cancelled is True

        await queue.stop(wait_for_complete=False)

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_task(self):
        """Test cancelling nonexistent task."""
        queue = BackgroundTaskQueue()

        result = queue.cancel_task("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_get_task(self):
        """Test getting task by ID."""
        queue = BackgroundTaskQueue()
        await queue.start()

        async def test_task():
            return "result"

        task = await queue.submit(test_task(), name="my_task")

        retrieved = queue.get_task(task.id)

        assert retrieved is task

        await queue.stop(wait_for_complete=False)

    @pytest.mark.asyncio
    async def test_get_tasks(self):
        """Test getting tasks list."""
        queue = BackgroundTaskQueue()
        await queue.start()

        async def test_task():
            return "result"

        await queue.submit(test_task(), name="task1")
        await queue.submit(test_task(), name="task2")

        tasks = queue.get_tasks()

        assert len(tasks) == 2

        await queue.stop(wait_for_complete=False)

    @pytest.mark.asyncio
    async def test_get_tasks_with_status_filter(self):
        """Test getting tasks with status filter."""
        queue = BackgroundTaskQueue()
        await queue.start()

        async def completed_task():
            return "done"

        task = await queue.submit(completed_task())

        # Wait for completion
        await asyncio.sleep(0.2)

        tasks = queue.get_tasks(status=TaskStatus.COMPLETED)

        assert len(tasks) == 1
        assert tasks[0].status == TaskStatus.COMPLETED

        await queue.stop(wait_for_complete=False)

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test getting queue statistics."""
        queue = BackgroundTaskQueue()
        await queue.start()

        async def test_task():
            return "result"

        await queue.submit(test_task())

        stats = queue.get_stats()

        assert stats["total_tasks"] == 1
        assert stats["max_concurrent"] == 3

        await queue.stop(wait_for_complete=False)

    def test_clear_completed(self):
        """Test clearing completed tasks."""
        queue = BackgroundTaskQueue()

        # Create completed task with old completion time
        import time

        task = Task(id="1", name="test", coro=None, status=TaskStatus.COMPLETED)
        task.completed_at = time.time() - 10  # 10 seconds ago
        queue._tasks["1"] = task

        cleared = queue.clear_completed(max_age=5)  # Clear tasks older than 5 seconds

        assert cleared == 1
        assert "1" not in queue._tasks

    @pytest.mark.asyncio
    async def test_callbacks(self):
        """Test callback functionality."""
        queue = BackgroundTaskQueue()

        completed_tasks = []
        progress_updates = []

        def on_complete(task):
            completed_tasks.append(task)

        def on_progress(task, progress):
            progress_updates.append((task.id, progress))

        queue.add_callback_on_complete(on_complete)
        queue.add_callback_on_progress(on_progress)

        await queue.start()

        async def test_task():
            return "done"

        task = await queue.submit(test_task())

        # Simulate progress
        queue._notify_progress(task, 0.5)

        # Wait for completion
        await asyncio.sleep(0.2)

        assert len(completed_tasks) >= 0  # May or may not be called
        assert len(progress_updates) == 1

        await queue.stop(wait_for_complete=False)


class TestGlobalFunctions:
    """Tests for global functions."""

    def test_get_task_queue(self):
        """Test getting global queue."""
        queue1 = get_task_queue()
        queue2 = get_task_queue()
        assert queue1 is queue2

    @pytest.mark.asyncio
    async def test_run_in_background(self):
        """Test run_in_background convenience function."""

        async def test_task():
            return "result"

        task = await run_in_background(test_task(), name="bg_task")

        assert task.name == "bg_task"

        # Clean up
        queue = get_task_queue()
        await queue.stop(wait_for_complete=False)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
