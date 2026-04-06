"""Optimized worker pool - Dynamic scaling, graceful shutdown."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional, Callable
from datetime import datetime

from .models import TaskInstance, TaskDefinition, TaskStatus, TaskResult
from .queue import OptimizedTaskQueue
from .registry import TaskRegistry


@dataclass
class WorkerConfig:
    """Worker pool configuration."""
    min_workers: int = 2
    max_workers: int = 20
    scale_up_threshold: float = 0.8  # Queue fill ratio
    scale_down_threshold: float = 0.3
    scale_cooldown_seconds: float = 10.0
    poll_interval_seconds: float = 0.01  # 10ms
    health_check_interval_seconds: float = 5.0


class Worker:
    """Individual worker that processes tasks."""
    
    def __init__(
        self,
        worker_id: str,
        queue: OptimizedTaskQueue,
        registry: TaskRegistry,
        on_task_complete: Optional[Callable[[TaskInstance], None]] = None
    ):
        self.worker_id = worker_id
        self.queue = queue
        self.registry = registry
        self.on_task_complete = on_task_complete
        
        # Stats
        self.tasks_completed = 0
        self.tasks_failed = 0
        self.total_execution_time_ms = 0.0
        
        # Health
        self.last_heartbeat = datetime.utcnow()
        self.is_running = False
        self.current_task: Optional[str] = None  # instance_id
        
        # Control
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
    
    async def start(self) -> None:
        """Start the worker."""
        self.is_running = True
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())
    
    async def stop(self, graceful: bool = True, timeout: float = 30.0) -> bool:
        """Stop the worker."""
        self.is_running = False
        self._stop_event.set()
        
        if self._task is None:
            return True
        
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        return True
    
    async def _run(self) -> None:
        """Main worker loop."""
        while self.is_running:
            try:
                # Get task with timeout
                result = await self.queue.get(timeout=1.0)
                
                if result is None:
                    continue
                
                if not self.is_running:
                    break
                
                instance, definition = result
                await self._process_task(instance, definition)
                
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.1)
    
    async def _process_task(
        self,
        instance: TaskInstance,
        definition: TaskDefinition
    ) -> None:
        """Process a single task."""
        self.current_task = instance.instance_id
        instance.worker_id = self.worker_id
        
        start_time = time.monotonic()
        
        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                self.registry.execute(
                    definition.handler_path,
                    instance,
                    **definition.input_data
                ),
                timeout=definition.execution_config.timeout_seconds
            )
            
            execution_time = (time.monotonic() - start_time) * 1000
            instance.result = result
            instance.completed_at = datetime.utcnow()
            
            if result.success:
                await self.queue.complete(instance)
                self.tasks_completed += 1
            else:
                # Check retry
                if instance.retry_count < definition.execution_config.max_retries:
                    await self.queue.fail(instance, retry=True)
                    # Resubmit with delay
                    await asyncio.sleep(
                        definition.execution_config.retry_delay_seconds *
                        (definition.execution_config.retry_backoff_multiplier ** instance.retry_count)
                    )
                    await self.queue.submit(definition, instance)
                else:
                    await self.queue.fail(instance, retry=False)
                    self.tasks_failed += 1
            
            self.total_execution_time_ms += execution_time
            
        except asyncio.TimeoutError:
            instance.status = TaskStatus.TIMEOUT
            instance.result = TaskResult(
                success=False,
                error_message=f"Task timed out after {definition.execution_config.timeout_seconds}s",
                error_type="TimeoutError"
            )
            await self.queue.fail(instance, retry=False)
            self.tasks_failed += 1
            
        except Exception as e:
            instance.status = TaskStatus.FAILED
            instance.result = TaskResult(
                success=False,
                error_message=str(e),
                error_type=type(e).__name__
            )
            await self.queue.fail(instance, retry=False)
            self.tasks_failed += 1
        
        finally:
            self.current_task = None
            self.last_heartbeat = datetime.utcnow()
            
            if self.on_task_complete:
                self.on_task_complete(instance)
    
    def get_stats(self) -> dict:
        """Get worker statistics."""
        avg_time = (self.total_execution_time_ms / max(self.tasks_completed, 1))
        return {
            'worker_id': self.worker_id,
            'tasks_completed': self.tasks_completed,
            'tasks_failed': self.tasks_failed,
            'avg_execution_time_ms': avg_time,
            'current_task': self.current_task,
            'is_healthy': self.is_healthy(),
        }
    
    def is_healthy(self) -> bool:
        """Check worker health."""
        elapsed = (datetime.utcnow() - self.last_heartbeat).total_seconds()
        return elapsed < 30  # Healthy if heartbeat within 30s


class WorkerPool:
    """Dynamic worker pool with auto-scaling."""
    
    def __init__(
        self,
        queue: OptimizedTaskQueue,
        registry: TaskRegistry,
        config: WorkerConfig | None = None
    ):
        self.queue = queue
        self.registry = registry
        self.config = config or WorkerConfig()
        
        self.workers: dict[str, Worker] = {}
        self._worker_counter = 0
        self._lock = asyncio.Lock()
        
        # Scaling
        self._last_scale_action = datetime.utcnow()
        self._scale_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self) -> None:
        """Start the worker pool."""
        self._running = True
        
        # Start minimum workers
        for _ in range(self.config.min_workers):
            await self._add_worker()
    
    async def stop(self, graceful: bool = True, timeout: float = 30.0) -> None:
        """Stop all workers."""
        self._running = False
        
        if self._scale_task:
            self._scale_task.cancel()
            try:
                await self._scale_task
            except asyncio.CancelledError:
                pass
        
        # Stop all workers concurrently
        results = await asyncio.gather(*[
            worker.stop(graceful=graceful, timeout=timeout)
            for worker in self.workers.values()
        ], return_exceptions=True)
        
        self.workers.clear()
    
    async def _add_worker(self) -> Worker:
        """Add a new worker."""
        async with self._lock:
            self._worker_counter += 1
            worker_id = f"worker-{self._worker_counter}"
            
            worker = Worker(
                worker_id=worker_id,
                queue=self.queue,
                registry=self.registry
            )
            await worker.start()
            self.workers[worker_id] = worker
            return worker
    
    async def _remove_worker(self) -> bool:
        """Remove a worker (prefer idle ones)."""
        async with self._lock:
            # Find idle worker
            for worker_id, worker in list(self.workers.items()):
                if worker.current_task is None:
                    await worker.stop(graceful=True, timeout=5.0)
                    del self.workers[worker_id]
                    return True
            return False
    
    async def _auto_scale(self) -> None:
        """Auto-scaling loop."""
        while self._running:
            try:
                await asyncio.sleep(self.config.scale_cooldown_seconds)
                
                if not self._running:
                    break
                
                queue_size = len(self.queue)
                queue_capacity = self.queue.max_size
                fill_ratio = queue_size / queue_capacity if queue_capacity > 0 else 0
                
                current_workers = len(self.workers)
                
                # Scale up
                if (fill_ratio > self.config.scale_up_threshold and 
                    current_workers < self.config.max_workers):
                    await self._add_worker()
                    self._last_scale_action = datetime.utcnow()
                
                # Scale down
                elif (fill_ratio < self.config.scale_down_threshold and
                      current_workers > self.config.min_workers):
                    await self._remove_worker()
                    self._last_scale_action = datetime.utcnow()
                    
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1.0)
    
    def get_stats(self) -> dict:
        """Get pool statistics."""
        healthy = sum(1 for w in self.workers.values() if w.is_healthy())
        return {
            'total_workers': len(self.workers),
            'healthy_workers': healthy,
            'worker_stats': [w.get_stats() for w in self.workers.values()],
        }
