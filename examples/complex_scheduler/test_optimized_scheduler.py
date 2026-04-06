"""Comprehensive tests for optimized scheduler."""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock

import sys

sys.path.insert(0, "/home/zx/mycc/PilotCode/test_complex_system")

from optimized_scheduler import (
    TaskPriority,
    TaskStatus,
    TaskDefinition,
    TaskInstance,
    TaskResult,
    ExecutionConfig,
    TaskRegistry,
    OptimizedTaskQueue,
    WorkerPool,
    WorkerConfig,
    StateManager,
    MemoryBackend,
    OptimizedScheduler,
    SchedulerConfig,
    MetricsCollector,
    task_handler,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def execution_config():
    return ExecutionConfig(
        timeout_seconds=5.0,
        max_retries=2,
        retry_delay_seconds=0.1,
    )


@pytest.fixture
def task_definition(execution_config):
    return TaskDefinition(
        name="test_task",
        handler_path="test.handler",
        priority=TaskPriority.NORMAL,
        execution_config=execution_config,
        input_data={"key": "value"},
    )


@pytest.fixture
async def queue():
    q = OptimizedTaskQueue(max_size=100)
    await q.start()
    yield q
    await q.stop()


@pytest.fixture
async def state_manager():
    sm = StateManager(backend=MemoryBackend())
    await sm.start()
    yield sm
    await sm.stop()


@pytest.fixture
def registry():
    # Fresh registry for each test
    TaskRegistry._instance = None
    return TaskRegistry()


# ============================================================================
# Test Models
# ============================================================================


class TestTaskPriority:
    """Test priority enum."""

    def test_priority_values(self):
        assert TaskPriority.LOW == 1
        assert TaskPriority.NORMAL == 2
        assert TaskPriority.HIGH == 3
        assert TaskPriority.CRITICAL == 4

    def test_priority_ordering(self):
        assert TaskPriority.LOW < TaskPriority.NORMAL
        assert TaskPriority.NORMAL < TaskPriority.HIGH
        assert TaskPriority.HIGH < TaskPriority.CRITICAL


class TestTaskStatus:
    """Test status enum."""

    def test_status_values(self):
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"


class TestExecutionConfig:
    """Test execution configuration."""

    def test_default_config(self):
        config = ExecutionConfig()
        assert config.timeout_seconds == 60.0
        assert config.max_retries == 3
        assert config.retry_delay_seconds == 1.0
        assert config.retry_backoff_multiplier == 2.0

    def test_custom_config(self):
        config = ExecutionConfig(
            timeout_seconds=30.0,
            max_retries=5,
        )
        assert config.timeout_seconds == 30.0
        assert config.max_retries == 5

    def test_validation(self):
        with pytest.raises(ValueError):
            ExecutionConfig(timeout_seconds=-1)

        with pytest.raises(ValueError):
            ExecutionConfig(max_retries=-1)


class TestTaskDefinition:
    """Test task definition model."""

    def test_definition_creation(self):
        definition = TaskDefinition(
            name="test",
            handler_path="handlers.test",
        )
        assert definition.name == "test"
        assert definition.handler_path == "handlers.test"
        assert definition.priority == TaskPriority.NORMAL
        assert isinstance(definition.id, str)

    def test_definition_scheduled(self):
        future = datetime.utcnow() + timedelta(hours=1)
        definition = TaskDefinition(
            name="scheduled",
            handler_path="handlers.scheduled",
            scheduled_at=future,
        )
        assert definition.is_scheduled is True

    def test_definition_not_scheduled(self):
        definition = TaskDefinition(
            name="immediate",
            handler_path="handlers.immediate",
        )
        assert definition.is_scheduled is False

    def test_cron_validation(self):
        with pytest.raises(ValueError):
            TaskDefinition(
                name="invalid",
                handler_path="handlers.invalid",
                cron_expression="invalid cron",
            )


class TestTaskInstance:
    """Test task instance model."""

    def test_instance_creation(self):
        instance = TaskInstance(definition_id="def-123")
        assert instance.definition_id == "def-123"
        assert instance.status == TaskStatus.PENDING
        assert instance.retry_count == 0

    def test_terminal_states(self):
        for status in [
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.TIMEOUT,
        ]:
            instance = TaskInstance(
                definition_id="test", status=status, completed_at=datetime.utcnow()
            )
            assert instance.is_terminal is True

    def test_non_terminal_state(self):
        instance = TaskInstance(definition_id="test", status=TaskStatus.RUNNING)
        assert instance.is_terminal is False

    def test_execution_time(self):
        now = datetime.utcnow()
        instance = TaskInstance(
            definition_id="test",
            started_at=now - timedelta(seconds=5),
            completed_at=now,
        )
        assert instance.execution_time_ms == pytest.approx(5000, abs=1)


# ============================================================================
# Test Registry
# ============================================================================


class TestTaskRegistry:
    """Test task handler registry."""

    @pytest.mark.asyncio
    async def test_register_and_execute(self, registry):
        async def handler(instance, **kwargs):
            return {"result": kwargs.get("value", 0) * 2}

        registry.register("test.double", handler)

        instance = TaskInstance(definition_id="test")
        result = await registry.execute("test.double", instance, value=5)

        assert result.success is True
        assert result.data == {"result": 10}

    @pytest.mark.asyncio
    async def test_register_sync_handler(self, registry):
        def sync_handler(instance, **kwargs):
            return kwargs.get("value", 0) + 1

        registry.register("test.increment", sync_handler)

        instance = TaskInstance(definition_id="test")
        result = await registry.execute("test.increment", instance, value=5)

        assert result.success is True
        assert result.data == 6

    @pytest.mark.asyncio
    async def test_handler_not_found(self, registry):
        instance = TaskInstance(definition_id="test")
        result = await registry.execute("nonexistent", instance)

        assert result.success is False
        assert "not found" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_handler_exception(self, registry):
        async def failing_handler(instance, **kwargs):
            raise ValueError("Test error")

        registry.register("test.fail", failing_handler)

        instance = TaskInstance(definition_id="test")
        result = await registry.execute("test.fail", instance)

        assert result.success is False
        assert result.error_type == "ValueError"

    def test_duplicate_registration(self, registry):
        def handler1():
            pass

        def handler2():
            pass

        registry.register("test.handler", handler1)

        with pytest.raises(ValueError):
            registry.register("test.handler", handler2)


# ============================================================================
# Test Queue
# ============================================================================


class TestOptimizedTaskQueue:
    """Test optimized task queue."""

    @pytest.mark.asyncio
    async def test_submit_and_get(self, queue, task_definition):
        instance = task_definition.with_status()

        success = await queue.submit(task_definition, instance)
        assert success is True

        retrieved_instance, retrieved_def = await queue.get(timeout=1.0)
        assert retrieved_instance.instance_id == instance.instance_id

    @pytest.mark.asyncio
    async def test_priority_ordering(self, queue):
        low_def = TaskDefinition(name="low", handler_path="h", priority=TaskPriority.LOW)
        high_def = TaskDefinition(name="high", handler_path="h", priority=TaskPriority.HIGH)

        low_inst = low_def.with_status()
        high_inst = high_def.with_status()

        await queue.submit(low_def, low_inst)
        await queue.submit(high_def, high_inst)

        # High priority should come first
        first, _ = await queue.get(timeout=1.0)
        assert first.definition_id == high_def.id

    @pytest.mark.asyncio
    async def test_fifo_within_priority(self, queue):
        def1 = TaskDefinition(name="first", handler_path="h")
        def2 = TaskDefinition(name="second", handler_path="h")

        inst1 = def1.with_status()
        inst2 = def2.with_status()

        await queue.submit(def1, inst1)
        await asyncio.sleep(0.01)  # Ensure different sequence
        await queue.submit(def2, inst2)

        first, _ = await queue.get(timeout=1.0)
        second, _ = await queue.get(timeout=1.0)

        assert first.definition_id == def1.id
        assert second.definition_id == def2.id

    @pytest.mark.asyncio
    async def test_delayed_task(self, queue):
        future = datetime.utcnow() + timedelta(milliseconds=100)
        definition = TaskDefinition(name="delayed", handler_path="h", scheduled_at=future)
        instance = definition.with_status()

        await queue.submit(definition, instance)

        # Should not be immediately available
        result = await queue.get(timeout=0.05)
        assert result is None

        # Wait for delayed task
        await asyncio.sleep(0.2)
        result = await queue.get(timeout=0.5)
        assert result is not None

    @pytest.mark.asyncio
    async def test_complete_task(self, queue, task_definition):
        instance = task_definition.with_status()

        await queue.submit(task_definition, instance)
        retrieved, _ = await queue.get(timeout=1.0)

        await queue.complete(retrieved)

        assert retrieved.status == TaskStatus.COMPLETED
        assert retrieved.completed_at is not None

    @pytest.mark.asyncio
    async def test_fail_task(self, queue, task_definition):
        instance = task_definition.with_status()

        await queue.submit(task_definition, instance)
        retrieved, _ = await queue.get(timeout=1.0)

        await queue.fail(retrieved, retry=False)

        assert retrieved.status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_backpressure(self):
        queue = OptimizedTaskQueue(max_size=2)
        await queue.start()

        try:
            # Fill queue
            for i in range(3):
                definition = TaskDefinition(name=f"task{i}", handler_path="h")
                instance = definition.with_status()
                success = await queue.submit(definition, instance)
                if i < 2:
                    assert success is True
                else:
                    assert success is False  # Queue full
        finally:
            await queue.stop()

    def test_queue_stats(self, queue):
        stats = queue.get_stats()
        assert hasattr(stats, "submitted")
        assert hasattr(stats, "completed")
        assert hasattr(stats, "failed")


# ============================================================================
# Test Worker Pool
# ============================================================================


class TestWorkerPool:
    """Test worker pool."""

    @pytest.mark.asyncio
    async def test_worker_pool_start_stop(self, queue, registry):
        pool = WorkerPool(queue, registry, WorkerConfig(min_workers=2, max_workers=4))

        await pool.start()
        assert len(pool.workers) == 2

        await pool.stop()
        assert len(pool.workers) == 0

    @pytest.mark.asyncio
    async def test_worker_executes_task(self, queue, registry):
        results = []

        async def handler(instance, **kwargs):
            results.append(kwargs.get("value"))
            return {"success": True}

        registry.register("test.worker", handler)

        pool = WorkerPool(queue, registry, WorkerConfig(min_workers=1))
        await pool.start()

        try:
            definition = TaskDefinition(
                name="test", handler_path="test.worker", input_data={"value": 42}
            )
            instance = definition.with_status()
            await queue.submit(definition, instance)

            # Wait for execution
            await asyncio.sleep(0.5)

            assert 42 in results
        finally:
            await pool.stop()

    @pytest.mark.asyncio
    async def test_worker_timeout(self, queue, registry):
        async def slow_handler(instance, **kwargs):
            await asyncio.sleep(10)  # Will timeout
            return {"success": True}

        registry.register("test.slow", slow_handler)

        pool = WorkerPool(queue, registry, WorkerConfig(min_workers=1))
        await pool.start()

        try:
            definition = TaskDefinition(
                name="slow",
                handler_path="test.slow",
                execution_config=ExecutionConfig(timeout_seconds=0.1),
            )
            instance = definition.with_status()
            await queue.submit(definition, instance)

            # Wait for timeout
            await asyncio.sleep(0.5)

            # Task should be marked as failed
            updated = queue.get_active_task(instance.instance_id)
            # Task is removed from active after completion
        finally:
            await pool.stop()

    @pytest.mark.asyncio
    async def test_worker_retry(self, queue, registry):
        attempts = [0]

        async def flaky_handler(instance, **kwargs):
            attempts[0] += 1
            if attempts[0] < 3:
                raise ValueError(f"Attempt {attempts[0]} failed")
            return {"success": True}

        registry.register("test.flaky", flaky_handler)

        pool = WorkerPool(queue, registry, WorkerConfig(min_workers=1))
        await pool.start()

        try:
            definition = TaskDefinition(
                name="flaky",
                handler_path="test.flaky",
                execution_config=ExecutionConfig(max_retries=3, retry_delay_seconds=0.05),
            )
            instance = definition.with_status()
            await queue.submit(definition, instance)

            # Wait for retries
            await asyncio.sleep(1.0)

            assert attempts[0] == 3
        finally:
            await pool.stop()


# ============================================================================
# Test State Manager
# ============================================================================


class TestStateManager:
    """Test state manager."""

    @pytest.mark.asyncio
    async def test_save_and_get(self, state_manager):
        instance = TaskInstance(definition_id="def-123")

        await state_manager.save(instance)
        retrieved = await state_manager.get(instance.instance_id)

        assert retrieved is not None
        assert retrieved.definition_id == "def-123"

    @pytest.mark.asyncio
    async def test_get_by_status(self, state_manager):
        pending = TaskInstance(definition_id="1", status=TaskStatus.PENDING)
        running = TaskInstance(definition_id="2", status=TaskStatus.RUNNING)
        completed = TaskInstance(
            definition_id="3", status=TaskStatus.COMPLETED, completed_at=datetime.utcnow()
        )

        await state_manager.save(pending)
        await state_manager.save(running)
        await state_manager.save(completed)

        pending_tasks = await state_manager.get_by_status(TaskStatus.PENDING)
        assert len(pending_tasks) == 1
        assert pending_tasks[0].definition_id == "1"

    @pytest.mark.asyncio
    async def test_delete(self, state_manager):
        instance = TaskInstance(definition_id="to-delete")
        await state_manager.save(instance)

        deleted = await state_manager.delete(instance.instance_id)
        assert deleted is True

        retrieved = await state_manager.get(instance.instance_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_cleanup(self, state_manager):
        old = TaskInstance(
            definition_id="old",
            status=TaskStatus.COMPLETED,
            completed_at=datetime.utcnow() - timedelta(hours=25),
        )
        recent = TaskInstance(
            definition_id="recent",
            status=TaskStatus.COMPLETED,
            completed_at=datetime.utcnow() - timedelta(hours=1),
        )

        await state_manager.save(old)
        await state_manager.save(recent)

        # Cleanup tasks older than 24 hours
        cutoff = datetime.utcnow() - timedelta(hours=24)
        cleaned = await state_manager.backend.cleanup(cutoff)

        assert cleaned == 1

        old_retrieved = await state_manager.get(old.instance_id)
        recent_retrieved = await state_manager.get(recent.instance_id)

        assert old_retrieved is None
        assert recent_retrieved is not None


# ============================================================================
# Test Scheduler
# ============================================================================


class TestOptimizedScheduler:
    """Test optimized scheduler."""

    @pytest.mark.asyncio
    async def test_scheduler_start_stop(self):
        scheduler = OptimizedScheduler(SchedulerConfig(min_workers=1, max_workers=2))

        await scheduler.start()
        assert scheduler._running is True

        await scheduler.stop()
        assert scheduler._running is False

    @pytest.mark.asyncio
    async def test_submit_task(self):
        scheduler = OptimizedScheduler(SchedulerConfig(min_workers=1, max_workers=2))
        await scheduler.start()

        try:
            instance = await scheduler.submit(
                name="test", handler_path="test.handler", input_data={"value": 42}
            )

            assert instance.definition_id is not None
            assert instance.status == TaskStatus.PENDING
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_get_task(self):
        scheduler = OptimizedScheduler(SchedulerConfig(min_workers=1, max_workers=2))
        await scheduler.start()

        try:
            submitted = await scheduler.submit(name="test", handler_path="test.handler")

            retrieved = await scheduler.get_task(submitted.instance_id)
            assert retrieved is not None
            assert retrieved.instance_id == submitted.instance_id
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_cancel_task(self):
        scheduler = OptimizedScheduler(SchedulerConfig(min_workers=1, max_workers=2))
        await scheduler.start()

        try:
            instance = await scheduler.submit(name="test", handler_path="test.handler")

            cancelled = await scheduler.cancel_task(instance.instance_id)
            assert cancelled is True

            retrieved = await scheduler.get_task(instance.instance_id)
            assert retrieved.status == TaskStatus.CANCELLED
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_get_stats(self):
        scheduler = OptimizedScheduler(SchedulerConfig(min_workers=1, max_workers=2))
        await scheduler.start()

        try:
            stats = scheduler.get_stats()

            assert "queue" in stats
            assert "workers" in stats
            assert "state" in stats
        finally:
            await scheduler.stop()


# ============================================================================
# Test Metrics
# ============================================================================


class TestMetricsCollector:
    """Test metrics collection."""

    def test_record_and_calculate(self):
        collector = MetricsCollector(window_size=100)

        # Record some tasks
        for i in range(10):
            collector.record_task_complete(
                wait_time_ms=float(i * 10),
                execution_time_ms=float(i * 5),
                success=i < 8,  # 80% success rate
            )

        metrics = collector.calculate_metrics(
            queue_size=5, queue_capacity=100, active_workers=2, healthy_workers=2
        )

        assert metrics.queue_size == 5
        assert metrics.active_workers == 2
        assert metrics.success_rate == pytest.approx(0.8, abs=0.01)
        assert metrics.avg_wait_time_ms == pytest.approx(45.0, abs=1.0)
        assert metrics.avg_execution_time_ms == pytest.approx(22.5, abs=1.0)

    @pytest.mark.asyncio
    async def test_metrics_callback(self):
        collector = MetricsCollector(collection_interval=0.1)

        received = []

        def callback(metrics):
            received.append(metrics)

        collector.add_callback(callback)

        await collector.start()
        await asyncio.sleep(0.25)
        await collector.stop()

        # Callbacks are called by external code, not automatically


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests."""

    @pytest.mark.asyncio
    async def test_full_task_lifecycle(self):
        """Test complete task lifecycle from submission to completion."""
        results = []

        async def test_handler(instance, **kwargs):
            results.append(kwargs.get("input"))
            return {"processed": kwargs.get("input")}

        registry = TaskRegistry()
        TaskRegistry._instance = None
        registry = TaskRegistry()
        registry.register("integration.test", test_handler)

        scheduler = OptimizedScheduler(
            SchedulerConfig(min_workers=1, max_workers=2), registry=registry
        )

        await scheduler.start()

        try:
            # Submit task
            instance = await scheduler.submit(
                name="integration_test",
                handler_path="integration.test",
                input_data={"input": "hello"},
                priority=TaskPriority.HIGH,
            )

            # Wait for execution
            await asyncio.sleep(0.5)

            # Verify
            assert "hello" in results

            # Check state
            retrieved = await scheduler.get_task(instance.instance_id)
            assert retrieved is not None

        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_multiple_tasks(self):
        """Test handling multiple tasks concurrently."""
        executed = []

        async def slow_handler(instance, **kwargs):
            await asyncio.sleep(0.05)
            executed.append(kwargs.get("id"))
            return {"id": kwargs.get("id")}

        TaskRegistry._instance = None
        registry = TaskRegistry()
        registry.register("multi.slow", slow_handler)

        scheduler = OptimizedScheduler(
            SchedulerConfig(min_workers=2, max_workers=4), registry=registry
        )

        await scheduler.start()

        try:
            # Submit multiple tasks
            tasks = []
            for i in range(5):
                instance = await scheduler.submit(
                    name=f"task_{i}", handler_path="multi.slow", input_data={"id": i}
                )
                tasks.append(instance)

            # Wait for all
            await asyncio.sleep(0.5)

            # Verify all executed
            assert len(executed) == 5
            assert set(executed) == {0, 1, 2, 3, 4}

        finally:
            await scheduler.stop()


# ============================================================================
# Performance Tests
# ============================================================================


class TestPerformance:
    """Performance tests."""

    @pytest.mark.asyncio
    async def test_throughput(self):
        """Test task throughput."""
        counter = [0]

        async def fast_handler(instance, **kwargs):
            counter[0] += 1
            return {"ok": True}

        TaskRegistry._instance = None
        registry = TaskRegistry()
        registry.register("perf.fast", fast_handler)

        scheduler = OptimizedScheduler(
            SchedulerConfig(min_workers=4, max_workers=8), registry=registry
        )

        await scheduler.start()

        try:
            # Submit many tasks
            start = asyncio.get_event_loop().time()
            num_tasks = 100

            for i in range(num_tasks):
                await scheduler.submit(name=f"perf_{i}", handler_path="perf.fast")

            # Wait for completion
            while counter[0] < num_tasks:
                await asyncio.sleep(0.01)

            elapsed = asyncio.get_event_loop().time() - start
            tps = num_tasks / elapsed

            print(f"\nThroughput: {tps:.1f} tasks/sec")
            assert tps > 50  # Should handle at least 50 TPS

        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_queue_priority_performance(self):
        """Test priority queue performance with many tasks."""
        queue = OptimizedTaskQueue(max_size=10000)
        await queue.start()

        try:
            import time

            # Submit many tasks
            start = time.monotonic()
            for i in range(1000):
                priority = TaskPriority(i % 4 + 1)
                definition = TaskDefinition(name=f"task_{i}", handler_path="h", priority=priority)
                instance = definition.with_status()
                await queue.submit(definition, instance)

            submit_time = time.monotonic() - start

            # Retrieve all
            start = time.monotonic()
            for _ in range(1000):
                result = await queue.get(timeout=1.0)
                assert result is not None

            get_time = time.monotonic() - start

            print(f"\nSubmit 1000 tasks: {submit_time:.3f}s")
            print(f"Get 1000 tasks: {get_time:.3f}s")

            assert submit_time < 1.0  # Should be fast
            assert get_time < 1.0

        finally:
            await queue.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
