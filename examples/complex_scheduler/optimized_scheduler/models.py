"""Task models - Optimized, type-safe, serializable."""

from __future__ import annotations

import uuid
from enum import Enum
from datetime import datetime
from typing import Any, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


class TaskPriority(int, Enum):
    """Task priority levels. Higher value = higher priority."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class ExecutionConfig(BaseModel):
    """Task execution configuration - Serializable, no callables."""

    model_config = ConfigDict(frozen=True)

    timeout_seconds: float = Field(default=60.0, ge=0.1, le=3600)
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_delay_seconds: float = Field(default=1.0, ge=0.1)
    retry_backoff_multiplier: float = Field(default=2.0, ge=1.0)

    # Resource limits
    max_memory_mb: Optional[int] = Field(default=None, ge=1)
    cpu_limit_percent: Optional[float] = Field(default=None, ge=1, le=100)


class TaskDefinition(BaseModel):
    """Task definition - Fully serializable, immutable."""

    model_config = ConfigDict(frozen=True)

    # Identity
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(min_length=1, max_length=256)
    handler_path: str = Field(min_length=1)  # registry key, not callable

    # Configuration
    priority: TaskPriority = TaskPriority.NORMAL
    execution_config: ExecutionConfig = Field(default_factory=ExecutionConfig)

    # Scheduling
    scheduled_at: Optional[datetime] = None
    cron_expression: Optional[str] = Field(default=None, pattern=r"^[\*\d\-,/\s]*$")

    # Dependencies
    dependencies: list[str] = Field(default_factory=list)  # task IDs

    # Input data (must be JSON serializable)
    input_data: dict[str, Any] = Field(default_factory=dict)

    # Metadata
    tags: set[str] = Field(default_factory=set, max_length=10)
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=100)

    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def is_scheduled(self) -> bool:
        """Check if this is a scheduled (delayed) task."""
        return self.scheduled_at is not None or self.cron_expression is not None

    def with_status(self, status: TaskStatus) -> TaskInstance:
        """Create a TaskInstance from this definition."""
        return TaskInstance.from_definition(self, status)


class TaskResult(BaseModel):
    """Task execution result."""

    model_config = ConfigDict(frozen=True)

    success: bool
    data: Any = None
    error_message: Optional[str] = None
    error_type: Optional[str] = None

    # Performance metrics
    execution_time_ms: float = 0.0
    memory_peak_mb: Optional[float] = None


class TaskInstance(BaseModel):
    """Task runtime instance - Tracks mutable state."""

    model_config = ConfigDict(validate_assignment=True)

    # Reference to definition
    definition_id: str

    # Instance identity
    instance_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # State
    status: TaskStatus = TaskStatus.PENDING
    retry_count: int = Field(default=0, ge=0)

    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Result (stored separately to limit memory)
    result: Optional[TaskResult] = None
    result_reference: Optional[str] = None  # External storage key

    # Execution tracking
    worker_id: Optional[str] = None
    execution_host: Optional[str] = None

    @property
    def execution_time_ms(self) -> float:
        """Calculate execution time."""
        if self.started_at is None:
            return 0.0
        end = self.completed_at or datetime.utcnow()
        return (end - self.started_at).total_seconds() * 1000

    @property
    def wait_time_ms(self) -> float:
        """Calculate wait time before execution."""
        if self.started_at is None:
            return (datetime.utcnow() - self.created_at).total_seconds() * 1000
        return (self.started_at - self.created_at).total_seconds() * 1000

    @property
    def is_terminal(self) -> bool:
        """Check if task reached terminal state."""
        return self.status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.TIMEOUT,
        )

    @classmethod
    def from_definition(
        cls, definition: TaskDefinition, status: TaskStatus = TaskStatus.PENDING
    ) -> TaskInstance:
        """Create instance from definition."""
        return cls(
            definition_id=definition.id,
            status=status,
        )

    def to_summary(self) -> dict[str, Any]:
        """Create lightweight summary for logging."""
        return {
            "instance_id": self.instance_id,
            "definition_id": self.definition_id,
            "status": self.status.value,
            "retry_count": self.retry_count,
            "execution_time_ms": self.execution_time_ms,
        }


# Type alias for task handler
TaskHandler = Any  # Actually Callable[[TaskInstance, ...], Any]
