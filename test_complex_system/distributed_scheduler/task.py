"""Task definitions - ISSUES: Complex hierarchy, inefficient serialization."""

import json
import uuid
from enum import Enum
from datetime import datetime
from typing import Any, Optional, Callable
from dataclasses import dataclass, field


class TaskPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """Base task class - ISSUE: Too many responsibilities."""
    
    # Core fields
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "unnamed"
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    
    # Timing
    created_at: datetime = field(default_factory=datetime.now)
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Execution
    handler: Optional[Callable] = None
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    
    # Retry logic - ISSUE: Mixed concerns
    max_retries: int = 3
    retry_count: int = 0
    retry_delay: float = 1.0
    
    # Dependencies - ISSUE: Complex dependency tracking in base class
    dependencies: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)
    
    # Results - ISSUE: Storing large results in memory
    result: Any = None
    error: Optional[str] = None
    error_traceback: Optional[str] = None
    
    # Metadata - ISSUE: Unbounded metadata
    metadata: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    
    # Timeout
    timeout: float = 60.0
    
    def to_dict(self) -> dict:
        """ISSUE: Inefficient serialization, includes callable."""
        return {
            'id': self.id,
            'name': self.name,
            'priority': self.priority.value,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'handler': str(self.handler) if self.handler else None,  # Can't serialize callable
            'args': list(self.args),  # May not be serializable
            'kwargs': dict(self.kwargs),  # May not be serializable
            'result': str(self.result) if self.result else None,  # May be large
            'error': self.error,
            'metadata': dict(self.metadata),  # Unbounded
        }
    
    def to_json(self) -> str:
        """ISSUE: No error handling for non-serializable data."""
        return json.dumps(self.to_dict())
    
    def is_ready(self) -> bool:
        """Check if task is ready to run."""
        return self.status == TaskStatus.PENDING and not self.dependencies
    
    def get_wait_time(self) -> float:
        """ISSUE: Inefficient time calculation."""
        if not self.scheduled_at:
            return 0.0
        now = datetime.now()
        diff = (self.scheduled_at - now).total_seconds()
        return max(0.0, diff)


@dataclass  
class ScheduledTask(Task):
    """Cron-based task - ISSUE: Inheritance abuse."""
    
    cron_expression: str = "* * * * *"
    timezone: str = "UTC"
    
    def get_next_run(self) -> datetime:
        """ISSUE: No actual cron parsing."""
        # Placeholder - should parse cron
        return datetime.now()


@dataclass
class ChainedTask(Task):
    """Task with dependencies - ISSUE: Overlaps with base class."""
    
    chain_results: bool = True  # Pass previous result to next
    
    def add_dependency(self, task_id: str):
        """ISSUE: Bidirectional tracking complexity."""
        self.dependencies.append(task_id)


@dataclass  
class ParallelTask(Task):
    """Task with parallel subtasks - ISSUE: Complex nested structure."""
    
    subtasks: list[Task] = field(default_factory=list)
    aggregate_results: bool = True
    require_all: bool = True  # All must succeed
    
    def add_subtask(self, task: Task):
        """ISSUE: No validation of subtask."""
        self.subtasks.append(task)
        task.dependencies.append(self.id)
