"""Worker implementation - ISSUES: Resource leaks, poor error handling."""

import asyncio
import traceback
from typing import Callable, Optional
from datetime import datetime

from .task import Task, TaskStatus
from .queue import TaskQueue


class Worker:
    """Task worker - ISSUES: No graceful shutdown, resource leaks."""
    
    def __init__(
        self,
        worker_id: str,
        queue: TaskQueue,
        poll_interval: float = 0.1
    ):
        self.worker_id = worker_id
        self.queue = queue
        self.poll_interval = poll_interval
        
        # ISSUE: Task references not cleaned up
        self.current_task: Optional[Task] = None
        self.tasks_processed = 0
        self.tasks_failed = 0
        
        # ISSUE: No proper lifecycle management
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # ISSUE: No health check tracking
        self.last_heartbeat = datetime.now()
    
    async def start(self) -> None:
        """Start worker - ISSUE: No startup validation."""
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
    
    async def stop(self) -> None:
        """Stop worker - ISSUE: Doesn't wait for current task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass  # ISSUE: Task may be left in unknown state
    
    async def _run_loop(self) -> None:
        """Main loop - ISSUE: Busy waiting, no backoff."""
        while self._running:
            try:
                # ISSUE: Blocking get with no timeout
                task = await self.queue.get()
                
                if task is None:
                    # ISSUE: Busy waiting
                    await asyncio.sleep(self.poll_interval)
                    continue
                
                self.current_task = task
                self.last_heartbeat = datetime.now()
                
                # Execute task
                await self._execute_task(task)
                
                self.tasks_processed += 1
                self.current_task = None
                
            except Exception as e:
                # ISSUE: Catches everything, may hide bugs
                print(f"Worker error: {e}")
                await asyncio.sleep(self.poll_interval)
    
    async def _execute_task(self, task: Task) -> None:
        """Execute single task - ISSUE: No timeout enforcement."""
        try:
            task.started_at = datetime.now()
            task.status = TaskStatus.RUNNING
            
            if task.handler is None:
                raise ValueError(f"Task {task.id} has no handler")
            
            # ISSUE: Synchronous handlers block event loop
            if asyncio.iscoroutinefunction(task.handler):
                result = await task.handler(*task.args, **task.kwargs)
            else:
                # ISSUE: Running sync code in thread pool would be better
                result = task.handler(*task.args, **task.kwargs)
            
            await self.queue.complete(task, result)
            
        except Exception as e:
            # ISSUE: Catches everything
            error_msg = str(e)
            task.error_traceback = traceback.format_exc()
            await self.queue.fail(task, error_msg)
            self.tasks_failed += 1
    
    def is_healthy(self) -> bool:
        """ISSUE: Simple time-based check, not accurate."""
        elapsed = (datetime.now() - self.last_heartbeat).total_seconds()
        return elapsed < 30  # 30 second timeout


class WorkerPool:
    """Worker pool - ISSUES: No dynamic scaling, poor load balancing."""
    
    def __init__(
        self,
        queue: TaskQueue,
        min_workers: int = 2,
        max_workers: int = 10
    ):
        self.queue = queue
        self.min_workers = min_workers
        self.max_workers = max_workers
        
        # ISSUE: Fixed size, no scaling
        self.workers: list[Worker] = []
        self._worker_counter = 0
        
        # ISSUE: No metrics for scaling decisions
        self._stats = {
            'scale_up_events': 0,
            'scale_down_events': 0,
        }
    
    async def start(self) -> None:
        """Start pool - ISSUE: Creates all workers at once."""
        for _ in range(self.min_workers):
            await self._add_worker()
    
    async def stop(self) -> None:
        """Stop pool - ISSUE: Sequential stop, slow."""
        for worker in self.workers:
            await worker.stop()
        self.workers.clear()
    
    async def _add_worker(self) -> Worker:
        """Add worker - ISSUE: No resource limit check."""
        self._worker_counter += 1
        worker = Worker(
            worker_id=f"worker-{self._worker_counter}",
            queue=self.queue
        )
        await worker.start()
        self.workers.append(worker)
        return worker
    
    def get_stats(self) -> dict:
        """ISSUE: Calculates on every call."""
        return {
            'total_workers': len(self.workers),
            'healthy_workers': sum(1 for w in self.workers if w.is_healthy()),
            'total_processed': sum(w.tasks_processed for w in self.workers),
            'total_failed': sum(w.tasks_failed for w in self.workers),
        }
    
    async def scale_to(self, target: int) -> None:
        """ISSUE: Immediate scaling, no gradual adjustment."""
        target = max(self.min_workers, min(target, self.max_workers))
        
        while len(self.workers) < target:
            await self._add_worker()
            self._stats['scale_up_events'] += 1
        
        while len(self.workers) > target:
            worker = self.workers.pop()
            await worker.stop()
            self._stats['scale_down_events'] += 1
