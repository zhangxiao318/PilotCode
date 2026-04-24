"""Task orchestration system for multi-agent workflows.

Provides P-EVR (Plan-Execute-Verify-Reflect) task orchestration framework.
Also maintains backward compatibility with legacy orchestration interfaces.
"""

# Legacy orchestration interfaces (backward compatible)
from .decomposer import TaskDecomposer, DecompositionStrategy
from .executor import TaskExecutor, ExecutionPlan
from .coordinator import AgentCoordinator, WorkflowResult

# P-EVR orchestration framework (new)
from .task_spec import TaskSpec, Phase, Mission, Constraints, AcceptanceCriterion
from .state_machine import TaskState, StateMachine, Transition, InvalidTransitionError
from .dag import DagNode, DagEdge, DagExecutor, build_dag_from_phases
from .tracker import MissionTracker, AgentProgress, MissionSnapshot
from .orchestrator import Orchestrator, OrchestratorConfig, ExecutionResult, VerificationResult

__all__ = [
    # Legacy
    "TaskDecomposer",
    "DecompositionStrategy",
    "TaskExecutor",
    "ExecutionPlan",
    "AgentCoordinator",
    "WorkflowResult",
    # P-EVR
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
]
