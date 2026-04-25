"""Task orchestration system for multi-agent workflows.

Provides unified P-EVR (Plan-Execute-Verify-Reflect) task orchestration framework.
"""

from .task_spec import TaskSpec, Phase, Mission, Constraints, AcceptanceCriterion
from .state_machine import TaskState, StateMachine, Transition, InvalidTransitionError
from .dag import DagNode, DagEdge, DagExecutor, build_dag_from_phases
from .tracker import MissionTracker, AgentProgress, MissionSnapshot
from .orchestrator import Orchestrator, OrchestratorConfig, ExecutionResult, VerificationResult
from .adapter import MissionAdapter
from .project_memory import ProjectMemory, FileSnapshot, FailedAttempt
from .context_strategy import ContextStrategy, ContextStrategySelector, MissionPlanAdjuster
from .report import (
    format_plan,
    format_progress,
    format_completion,
    format_failure,
    format_task_event,
)

__all__ = [
    # P-EVR Framework
    "TaskSpec",
    "Phase",
    "Mission",
    "Constraints",
    "AcceptanceCriterion",
    "TaskState",
    "StateMachine",
    "Transition",
    "InvalidTransitionError",
    "DagNode",
    "DagEdge",
    "DagExecutor",
    "build_dag_from_phases",
    "MissionTracker",
    "AgentProgress",
    "MissionSnapshot",
    "Orchestrator",
    "OrchestratorConfig",
    "ExecutionResult",
    "VerificationResult",
    # Adapter & Memory
    "MissionAdapter",
    "ProjectMemory",
    "FileSnapshot",
    "FailedAttempt",
    # Strategy & Report
    "ContextStrategy",
    "ContextStrategySelector",
    "MissionPlanAdjuster",
    "format_plan",
    "format_progress",
    "format_completion",
    "format_failure",
    "format_task_event",
]
