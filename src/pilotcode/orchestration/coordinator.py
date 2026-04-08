"""Agent coordinator for managing multi-agent workflows.

Coordinates multiple agents working together on complex tasks.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

from .decomposer import TaskDecomposer, DecompositionStrategy
from .executor import TaskExecutor, ExecutionPlan, ExecutionResult, ExecutionStatus


@dataclass
class WorkflowResult:
    """Result of a workflow execution."""
    workflow_id: str
    original_task: str
    status: str  # success, partial, failed
    results: list[ExecutionResult] = field(default_factory=list)
    summary: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)
    
    @property
    def duration_seconds(self) -> float:
        """Calculate total duration."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "workflow_id": self.workflow_id,
            "original_task": self.original_task,
            "status": self.status,
            "results": [
                {
                    "task_id": r.task_id,
                    "status": r.status.value,
                    "output": r.output[:200] if r.output else "",
                    "error": r.error
                }
                for r in self.results
            ],
            "summary": self.summary,
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata
        }


class AgentCoordinator:
    """Coordinates multi-agent task execution.
    
    Main entry point for ClaudeCode-style task decomposition and execution.
    """
    
    def __init__(
        self,
        agent_factory: Callable[[str, str], Any],
        model_client: Optional[Any] = None
    ):
        self.decomposer = TaskDecomposer(model_client)
        self.executor = TaskExecutor(agent_factory)
        self._workflows: dict[str, WorkflowResult] = {}
    
    def on_progress(self, callback: Callable[[str, dict], None]):
        """Register progress callback."""
        self.executor.on_progress(callback)
    
    async def execute(
        self,
        task: str,
        strategy: Optional[str] = None,
        context: dict = None,
        auto_decompose: bool = True
    ) -> WorkflowResult:
        """Execute a task with automatic decomposition and coordination.
        
        This is the main entry point that matches ClaudeCode's behavior.
        
        Args:
            task: The task to execute
            strategy: Optional forced strategy (sequential, parallel, hierarchical)
            context: Additional context
            auto_decompose: Whether to automatically decompose the task
            
        Returns:
            WorkflowResult with all execution details
        """
        workflow_id = f"wf_{uuid.uuid4().hex[:8]}"
        context = context or {}
        
        # Step 1: Analyze and decompose task
        if auto_decompose:
            decomposition = self.decomposer.auto_decompose(task)
        else:
            decomposition = self.decomposer.analyze(task)
        
        # Override strategy if specified
        if strategy:
            strategy_enum = DecompositionStrategy[strategy.upper()]
            decomposition.strategy = strategy_enum
        
        # Step 2: Execute based on strategy
        if decomposition.strategy == DecompositionStrategy.NONE or not decomposition.subtasks:
            # Execute as single task
            result = await self._execute_single_task(workflow_id, task, context)
            return result
        
        # Execute decomposed task
        return await self._execute_decomposed(
            workflow_id,
            task,
            decomposition,
            context
        )
    
    async def _execute_single_task(
        self,
        workflow_id: str,
        task: str,
        context: dict
    ) -> WorkflowResult:
        """Execute a single task without decomposition."""
        started_at = datetime.now()
        
        # Create a single subtask
        single_task = type('obj', (object,), {
            'id': 'main',
            'description': task,
            'prompt': task,
            'role': 'coder',
            'dependencies': []
        })()
        
        # Execute
        results = await self.executor.execute_sequential([single_task], context)
        
        completed_at = datetime.now()
        status = "success" if results[0].status == ExecutionStatus.COMPLETED else "failed"
        
        workflow = WorkflowResult(
            workflow_id=workflow_id,
            original_task=task,
            status=status,
            results=results,
            summary=results[0].output if results else "",
            started_at=started_at,
            completed_at=completed_at
        )
        
        self._workflows[workflow_id] = workflow
        return workflow
    
    async def _execute_decomposed(
        self,
        workflow_id: str,
        task: str,
        decomposition: Any,
        context: dict
    ) -> WorkflowResult:
        """Execute a decomposed task."""
        started_at = datetime.now()
        
        # Choose execution method based on strategy
        if decomposition.strategy == DecompositionStrategy.PARALLEL:
            results = await self.executor.execute_parallel(
                decomposition.subtasks,
                context
            )
        elif decomposition.strategy == DecompositionStrategy.HIERARCHICAL:
            results = await self.executor.execute_hierarchical(
                task,
                decomposition.subtasks,
                context
            )
        elif decomposition.strategy == DecompositionStrategy.SEQUENTIAL:
            results = await self.executor.execute_sequential(
                decomposition.subtasks,
                context
            )
        else:
            # Default to dependency-aware execution
            results = await self.executor.execute_with_dependencies(
                decomposition.subtasks,
                context
            )
        
        # Determine overall status
        success_count = sum(1 for r in results if r.status == ExecutionStatus.COMPLETED)
        failed_count = sum(1 for r in results if r.status == ExecutionStatus.FAILED)
        
        if failed_count == 0:
            status = "success"
        elif success_count > 0:
            status = "partial"
        else:
            status = "failed"
        
        # Generate summary
        summary = self._generate_summary(task, decomposition, results)
        
        completed_at = datetime.now()
        
        workflow = WorkflowResult(
            workflow_id=workflow_id,
            original_task=task,
            status=status,
            results=results,
            summary=summary,
            started_at=started_at,
            completed_at=completed_at,
            metadata={
                "strategy": decomposition.strategy.name,
                "decomposed": True,
                "subtask_count": len(decomposition.subtasks),
                "success_count": success_count,
                "failed_count": failed_count
            }
        )
        
        self._workflows[workflow_id] = workflow
        return workflow
    
    def _generate_summary(
        self,
        task: str,
        decomposition: Any,
        results: list[ExecutionResult]
    ) -> str:
        """Generate a summary of the workflow execution."""
        lines = [f"# Task Execution Summary\n"]
        lines.append(f"**Original Task:** {task}\n")
        lines.append(f"**Strategy:** {decomposition.strategy.name}\n")
        lines.append(f"**Subtasks:** {len(decomposition.subtasks)}\n\n")
        
        lines.append("## Results by Subtask\n")
        for i, (subtask, result) in enumerate(zip(decomposition.subtasks, results), 1):
            status_icon = "✅" if result.status == ExecutionStatus.COMPLETED else "❌"
            lines.append(f"{status_icon} **{i}. {subtask.description}** ({subtask.role})\n")
            if result.output:
                # Truncate output
                output_preview = result.output[:200].replace('\n', ' ')
                if len(result.output) > 200:
                    output_preview += "..."
                lines.append(f"   Output: {output_preview}\n")
            if result.error:
                lines.append(f"   Error: {result.error}\n")
        
        # Add synthesis if multiple results
        successful_results = [r for r in results if r.status == ExecutionStatus.COMPLETED]
        if len(successful_results) > 1:
            lines.append("\n## Synthesis\n")
            lines.append("Multiple subtasks were completed successfully. ")
            lines.append("The results have been integrated to provide a comprehensive solution.\n")
        
        return "".join(lines)
    
    def get_workflow(self, workflow_id: str) -> Optional[WorkflowResult]:
        """Get a workflow by ID."""
        return self._workflows.get(workflow_id)
    
    def list_workflows(
        self,
        status: Optional[str] = None
    ) -> list[WorkflowResult]:
        """List all workflows, optionally filtered by status."""
        workflows = list(self._workflows.values())
        if status:
            workflows = [w for w in workflows if w.status == status]
        return sorted(workflows, key=lambda w: w.started_at, reverse=True)
    
    def get_statistics(self) -> dict:
        """Get execution statistics."""
        workflows = list(self._workflows.values())
        
        if not workflows:
            return {"total": 0}
        
        total = len(workflows)
        success = sum(1 for w in workflows if w.status == "success")
        partial = sum(1 for w in workflows if w.status == "partial")
        failed = sum(1 for w in workflows if w.status == "failed")
        
        total_duration = sum(w.duration_seconds for w in workflows)
        avg_duration = total_duration / total if total > 0 else 0
        
        return {
            "total": total,
            "success": success,
            "partial": partial,
            "failed": failed,
            "success_rate": success / total if total > 0 else 0,
            "total_duration_seconds": total_duration,
            "average_duration_seconds": avg_duration
        }


# Global coordinator instance
_coordinator: Optional[AgentCoordinator] = None


def get_coordinator(
    agent_factory: Optional[Callable] = None,
    model_client: Optional[Any] = None
) -> AgentCoordinator:
    """Get or create the global coordinator."""
    global _coordinator
    if _coordinator is None:
        if agent_factory is None:
            raise ValueError("Agent factory required for first initialization")
        _coordinator = AgentCoordinator(agent_factory, model_client)
    return _coordinator
