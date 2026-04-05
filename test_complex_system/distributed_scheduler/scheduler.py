"""Task Scheduler - ISSUES: Complex, tightly coupled, hard to test."""

import asyncio
from typing import Optional, Callable
from datetime import datetime

from .task import Task, ScheduledTask, ChainedTask, ParallelTask, TaskStatus
from .queue import TaskQueue
from .worker import WorkerPool
from .state import StateManager


class TaskScheduler:
    """Main scheduler - ISSUES: God class, too many responsibilities."""
    
    def __init__(
        self,
        max_queue_size: int = 10000,
        min_workers: int = 2,
        max_workers: int = 10
    ):
        # ISSUE: Creates dependencies internally, hard to mock
        self.queue = TaskQueue(max_size=max_queue_size)
        self.workers = WorkerPool(
            queue=self.queue,
            min_workers=min_workers,
            max_workers=max_workers
        )
        self.state = StateManager()
        
        # ISSUE: Multiple responsibilities
        self._scheduled_tasks: list[ScheduledTask] = []
        self._chained_tasks: dict[str, ChainedTask] = {}
        self._parallel_tasks: dict[str, ParallelTask] = {}
        
        # ISSUE: No proper lifecycle
        self._running = False
        self._tasks: list[asyncio.Task] = []
        
        # ISSUE: No configuration for intervals
        self._scheduler_interval = 1.0
        self._monitor_interval = 5.0
    
    async def start(self) -> None:
        """Start scheduler - ISSUE: No partial failure handling."""
        self._running = True
        
        # Start components
        await self.workers.start()
        
        # ISSUE: Background tasks not tracked properly
        self._tasks.append(
            asyncio.create_task(self._scheduler_loop())
        )
        self._tasks.append(
            asyncio.create_task(self._monitor_loop())
        )
    
    async def stop(self) -> None:
        """Stop scheduler - ISSUE: Cleanup order may lose tasks."""
        self._running = False
        
        # Cancel background tasks
        for task in self._tasks:
            task.cancel()
        
        # ISSUE: Gathering may fail if one fails
        await asyncio.gather(*self._tasks, return_exceptions=True)
        
        # Stop workers
        await self.workers.stop()
    
    async def submit(
        self,
        handler: Callable,
        *args,
        priority: int = 2,
        **kwargs
    ) -> Task:
        """Submit simple task - ISSUE: Mixed sync/async API."""
        task = Task(
            handler=handler,
            args=args,
            kwargs=kwargs,
            priority=priority,
        )
        
        await self.queue.submit(task)
        await self.state.track_task(task)
        
        return task
    
    async def submit_scheduled(
        self,
        handler: Callable,
        cron: str,
        *args,
        **kwargs
    ) -> ScheduledTask:
        """Submit scheduled task - ISSUE: No validation of cron."""
        task = ScheduledTask(
            handler=handler,
            args=args,
            kwargs=kwargs,
            cron_expression=cron,
        )
        
        self._scheduled_tasks.append(task)
        await self.state.track_task(task)
        
        return task
    
    async def submit_chain(
        self,
        handlers: list[Callable],
        *args,
        **kwargs
    ) -> ChainedTask:
        """Submit chained tasks - ISSUE: Complex, error-prone."""
        # ISSUE: Creates tasks internally, no visibility
        tasks = []
        for handler in handlers:
            task = Task(handler=handler, args=args, kwargs=kwargs)
            tasks.append(task)
        
        # Set up dependencies
        for i in range(1, len(tasks)):
            tasks[i].dependencies.append(tasks[i-1].id)
        
        chain = ChainedTask(dependencies=[t.id for t in tasks[:-1]])
        self._chained_tasks[chain.id] = chain
        
        # Submit all tasks
        for task in tasks:
            await self.queue.submit(task)
            await self.state.track_task(task)
        
        return chain
    
    async def submit_parallel(
        self,
        handlers: list[Callable],
        *args,
        require_all: bool = True,
        **kwargs
    ) -> ParallelTask:
        """Submit parallel tasks - ISSUE: Resource exhaustion risk."""
        parent = ParallelTask(require_all=require_all)
        
        # ISSUE: No limit on number of subtasks
        for handler in handlers:
            subtask = Task(
                handler=handler,
                args=args,
                kwargs=kwargs
            )
            parent.add_subtask(subtask)
            await self.queue.submit(subtask)
            await self.state.track_task(subtask)
        
        self._parallel_tasks[parent.id] = parent
        await self.state.track_task(parent)
        
        return parent
    
    async def _scheduler_loop(self) -> None:
        """Check scheduled tasks - ISSUE: Inefficient polling."""
        while self._running:
            try:
                now = datetime.now()
                
                # ISSUE: Linear scan of all scheduled tasks
                for task in self._scheduled_tasks:
                    if task.scheduled_at and task.scheduled_at <= now:
                        if task.status == TaskStatus.PENDING:
                            await self.queue.submit(task)
                
                # ISSUE: Fixed sleep, no dynamic adjustment
                await asyncio.sleep(self._scheduler_interval)
                
            except Exception as e:
                # ISSUE: Silent failure
                print(f"Scheduler error: {e}")
    
    async def _monitor_loop(self) -> None:
        """Monitor system - ISSUE: No actionable metrics."""
        while self._running:
            try:
                # ISSUE: Just prints, no real monitoring
                stats = self.workers.get_stats()
                print(f"Workers: {stats}")
                
                await asyncio.sleep(self._monitor_interval)
                
            except Exception as e:
                print(f"Monitor error: {e}")
    
    def get_stats(self) -> dict:
        """ISSUE: Expensive aggregation."""
        return {
            'queue_size': len(self.queue),
            'scheduled_tasks': len(self._scheduled_tasks),
            'chained_tasks': len(self._chained_tasks),
            'parallel_tasks': len(self._parallel_tasks),
            'worker_stats': self.workers.get_stats(),
        }
