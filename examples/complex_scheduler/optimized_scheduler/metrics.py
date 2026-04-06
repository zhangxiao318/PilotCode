"""Metrics collection and performance monitoring."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional, Callable
from collections import deque
from datetime import datetime


@dataclass
class PerformanceMetrics:
    """Performance metrics snapshot."""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Throughput
    tasks_per_second: float = 0.0
    
    # Latency (ms)
    avg_wait_time_ms: float = 0.0
    p50_wait_time_ms: float = 0.0
    p99_wait_time_ms: float = 0.0
    
    # Execution time (ms)
    avg_execution_time_ms: float = 0.0
    p50_execution_time_ms: float = 0.0
    p99_execution_time_ms: float = 0.0
    
    # Queue
    queue_size: int = 0
    queue_capacity: int = 0
    
    # Workers
    active_workers: int = 0
    healthy_workers: int = 0
    
    # Success rate
    success_rate: float = 1.0


class MetricsCollector:
    """Collect and aggregate performance metrics."""
    
    def __init__(
        self,
        window_size: int = 1000,
        collection_interval: float = 10.0
    ):
        self.window_size = window_size
        self.collection_interval = collection_interval
        
        # Circular buffers for metrics
        self._wait_times: deque[float] = deque(maxlen=window_size)
        self._execution_times: deque[float] = deque(maxlen=window_size)
        self._results: deque[bool] = deque(maxlen=window_size)
        
        # Rate tracking
        self._task_times: deque[float] = deque(maxlen=window_size)
        
        # Callbacks
        self._on_metric: list[Callable[[PerformanceMetrics], None]] = []
        
        # Control
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    def add_callback(self, callback: Callable[[PerformanceMetrics], None]) -> None:
        """Add callback for metric updates."""
        self._on_metric.append(callback)
    
    def record_task_complete(
        self,
        wait_time_ms: float,
        execution_time_ms: float,
        success: bool
    ) -> None:
        """Record task completion metrics."""
        self._wait_times.append(wait_time_ms)
        self._execution_times.append(execution_time_ms)
        self._results.append(success)
        self._task_times.append(time.monotonic())
    
    def calculate_metrics(
        self,
        queue_size: int = 0,
        queue_capacity: int = 0,
        active_workers: int = 0,
        healthy_workers: int = 0
    ) -> PerformanceMetrics:
        """Calculate current metrics."""
        # Wait times
        wait_times = list(self._wait_times) or [0.0]
        wait_times_sorted = sorted(wait_times)
        
        # Execution times
        exec_times = list(self._execution_times) or [0.0]
        exec_times_sorted = sorted(exec_times)
        
        # Success rate
        results = list(self._results)
        success_rate = sum(results) / len(results) if results else 1.0
        
        # Throughput (tasks per second over last minute)
        now = time.monotonic()
        recent_tasks = sum(1 for t in self._task_times if now - t < 60.0)
        tps = recent_tasks / 60.0
        
        def percentile(sorted_data: list[float], p: float) -> float:
            if not sorted_data:
                return 0.0
            k = (len(sorted_data) - 1) * p / 100
            f = int(k)
            c = f + 1 if f + 1 < len(sorted_data) else f
            return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])
        
        return PerformanceMetrics(
            timestamp=datetime.utcnow(),
            tasks_per_second=tps,
            avg_wait_time_ms=sum(wait_times) / len(wait_times),
            p50_wait_time_ms=percentile(wait_times_sorted, 50),
            p99_wait_time_ms=percentile(wait_times_sorted, 99),
            avg_execution_time_ms=sum(exec_times) / len(exec_times),
            p50_execution_time_ms=percentile(exec_times_sorted, 50),
            p99_execution_time_ms=percentile(exec_times_sorted, 99),
            queue_size=queue_size,
            queue_capacity=queue_capacity,
            active_workers=active_workers,
            healthy_workers=healthy_workers,
            success_rate=success_rate,
        )
    
    async def start(self) -> None:
        """Start metrics collection."""
        self._running = True
        self._task = asyncio.create_task(self._collect_loop())
    
    async def stop(self) -> None:
        """Stop metrics collection."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def _collect_loop(self) -> None:
        """Periodic metrics collection."""
        while self._running:
            try:
                await asyncio.sleep(self.collection_interval)
                
                # Metrics will be calculated and callbacks called by external code
                # that has access to queue and worker stats
                
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1.0)
