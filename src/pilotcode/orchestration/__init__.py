"""Task orchestration system for multi-agent workflows.

Provides ClaudeCode-style task decomposition and execution.
"""

from .decomposer import TaskDecomposer, DecompositionStrategy
from .executor import TaskExecutor, ExecutionPlan
from .coordinator import AgentCoordinator, WorkflowResult

__all__ = [
    "TaskDecomposer",
    "DecompositionStrategy",
    "TaskExecutor",
    "ExecutionPlan",
    "AgentCoordinator",
    "WorkflowResult",
]
