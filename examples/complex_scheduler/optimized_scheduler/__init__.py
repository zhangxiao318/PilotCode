"""Optimized Distributed Task Scheduler.

A high-performance, production-ready distributed task scheduling system.

Key improvements:
- Clean separation of concerns
- Async-first design
- Type-safe with Pydantic
- Pluggable backends
- Comprehensive monitoring
"""

__version__ = "2.0.0"

from .models import (
    TaskPriority,
    TaskStatus,
    TaskDefinition,
    TaskInstance,
    TaskResult,
    ExecutionConfig,
)
from .registry import TaskRegistry, task_handler
from .queue import OptimizedTaskQueue, QueueStats
from .worker import WorkerPool, WorkerConfig
from .scheduler import OptimizedScheduler, SchedulerConfig
from .state import StateManager, MemoryBackend, StateBackend
from .metrics import MetricsCollector, PerformanceMetrics

__all__ = [
    # Models
    'TaskPriority',
    'TaskStatus',
    'TaskDefinition',
    'TaskInstance',
    'TaskResult',
    'ExecutionConfig',
    # Registry
    'TaskRegistry',
    'task_handler',
    # Queue
    'OptimizedTaskQueue',
    'QueueStats',
    # Worker
    'WorkerPool',
    'WorkerConfig',
    # Scheduler
    'OptimizedScheduler',
    'SchedulerConfig',
    # State
    'StateManager',
    'MemoryBackend',
    'StateBackend',
    # Metrics
    'MetricsCollector',
    'PerformanceMetrics',
]
