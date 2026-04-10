"""Task execution engine.

Executes decomposed tasks with proper dependency management.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Optional


class ExecutionStatus(Enum):
    """Status of task execution."""
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


@dataclass
class ExecutionResult:
    """Result of executing a subtask."""
    task_id: str
    status: ExecutionStatus
    output: str = ""
    error: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    tools_used: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    
    @property
    def duration_seconds(self) -> float:
        """Calculate execution duration."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0


@dataclass
class ExecutionPlan:
    """Execution plan for a decomposed task."""
    task_id: str
    original_task: str
    strategy: str
    executions: list[ExecutionResult] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    @property
    def is_complete(self) -> bool:
        """Check if all executions are complete."""
        return all(
            e.status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED)
            for e in self.executions
        )
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if not self.executions:
            return 0.0
        completed = sum(1 for e in self.executions if e.status == ExecutionStatus.COMPLETED)
        return completed / len(self.executions)
    
    def get_summary(self) -> dict:
        """Get execution summary."""
        return {
            "task_id": self.task_id,
            "original_task": self.original_task,
            "strategy": self.strategy,
            "total_subtasks": len(self.executions),
            "completed": sum(1 for e in self.executions if e.status == ExecutionStatus.COMPLETED),
            "failed": sum(1 for e in self.executions if e.status == ExecutionStatus.FAILED),
            "success_rate": self.success_rate,
            "duration_seconds": sum(e.duration_seconds for e in self.executions)
        }


class TaskExecutor:
    """Executes tasks with support for various strategies."""
    
    def __init__(
        self,
        agent_factory: Callable[[str, str], Any],
        max_parallel: int = 3,
        max_concurrency: int = None
    ):
        self.agent_factory = agent_factory
        # Support both max_parallel and max_concurrency for backward compatibility
        self.max_parallel = max_concurrency if max_concurrency is not None else max_parallel
        self._progress_callbacks: list[Callable[[str, dict], None]] = []
    
    def on_progress(self, callback: Callable[[str, dict], None]):
        """Register progress callback."""
        self._progress_callbacks.append(callback)
    
    def _notify_progress(self, event: str, data: dict):
        """Notify all progress callbacks."""
        for callback in self._progress_callbacks:
            try:
                callback(event, data)
            except Exception:
                pass
    
    async def execute_sequential(
        self,
        subtasks: list[Any],
        context: dict = None
    ) -> list[ExecutionResult]:
        """Execute subtasks sequentially, passing results forward.
        
        Each subtask receives the accumulated results of previous tasks.
        """
        results = []
        accumulated_output = ""
        context = context or {}
        
        for i, subtask in enumerate(subtasks):
            self._notify_progress("task_starting", {
                "task_id": subtask.id,
                "index": i,
                "total": len(subtasks),
                "strategy": "sequential"
            })
            
            # Enhance prompt with previous results
            enhanced_prompt = self._enhance_prompt_with_context(
                subtask.prompt,
                accumulated_output,
                subtask.dependencies
            )
            
            # Execute
            result = await self._execute_single(subtask, enhanced_prompt, context)
            results.append(result)
            
            # Accumulate output for next task
            if result.status == ExecutionStatus.COMPLETED:
                accumulated_output += f"\n\n=== {subtask.role.upper()}: {subtask.description} ===\n{result.output}"
            
            self._notify_progress("task_completed", {
                "task_id": subtask.id,
                "status": result.status.value,
                "index": i
            })
            
            # Stop on failure unless configured to continue
            if result.status == ExecutionStatus.FAILED:
                break
        
        return results
    
    async def execute_parallel(
        self,
        subtasks: list[Any],
        context: dict = None,
        max_concurrency: int = None
    ) -> list[ExecutionResult]:
        """Execute subtasks in parallel with concurrency limit."""
        concurrency = max_concurrency if max_concurrency is not None else self.max_parallel
        semaphore = asyncio.Semaphore(concurrency)
        context = context or {}
        
        async def run_with_limit(subtask: Any, index: int) -> ExecutionResult:
            async with semaphore:
                self._notify_progress("task_starting", {
                    "task_id": subtask.id,
                    "index": index,
                    "total": len(subtasks),
                    "strategy": "parallel"
                })
                
                result = await self._execute_single(subtask, subtask.prompt, context)
                
                self._notify_progress("task_completed", {
                    "task_id": subtask.id,
                    "status": result.status.value,
                    "index": index
                })
                
                return result
        
        # Create tasks
        tasks = [
            run_with_limit(subtask, i)
            for i, subtask in enumerate(subtasks)
        ]
        
        # Execute all in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        processed = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed.append(ExecutionResult(
                    task_id=subtasks[i].id,
                    status=ExecutionStatus.FAILED,
                    error=str(result)
                ))
            else:
                processed.append(result)
        
        return processed
    
    async def execute_hierarchical(
        self,
        supervisor_task: str,
        worker_subtasks: list[Any],
        context: dict = None
    ) -> list[ExecutionResult]:
        """Execute with supervisor-worker pattern.
        
        Supervisor coordinates workers and synthesizes final result.
        """
        context = context or {}
        results = []
        
        # 1. Create supervisor
        self._notify_progress("supervisor_created", {
            "task": supervisor_task[:100]
        })
        
        # 2. Execute workers in parallel
        worker_results = await self.execute_parallel(worker_subtasks, context)
        results.extend(worker_results)
        
        # 3. Synthesize results with supervisor
        successful_results = [
            r for r in worker_results
            if r.status == ExecutionStatus.COMPLETED
        ]
        
        if successful_results:
            synthesis_prompt = self._build_synthesis_prompt(
                supervisor_task,
                successful_results
            )
            
            # Create synthesis subtask
            synthesis_task = type('obj', (object,), {
                'id': 'synthesis',
                'description': 'Synthesize results',
                'prompt': synthesis_prompt,
                'role': 'planner'
            })()
            
            synthesis_result = await self._execute_single(
                synthesis_task,
                synthesis_prompt,
                context
            )
            
            results.append(synthesis_result)
        
        return results
    
    async def execute_with_dependencies(
        self,
        subtasks: list[Any],
        context: dict = None
    ) -> list[ExecutionResult]:
        """Execute subtasks respecting dependencies.
        
        Uses topological sort to determine execution order.
        """
        context = context or {}
        results: dict[str, ExecutionResult] = {}
        remaining = list(subtasks)
        
        while remaining:
            # Find tasks with satisfied dependencies
            ready = [
                t for t in remaining
                if all(dep in results and results[dep].status == ExecutionStatus.COMPLETED 
                       for dep in t.dependencies)
            ]
            
            if not ready:
                # Deadlock or missing dependencies
                break
            
            # Execute ready tasks in parallel
            batch_results = await self.execute_parallel(ready, context)
            
            for task, result in zip(ready, batch_results):
                results[task.id] = result
                remaining.remove(task)
        
        # Return in original order
        return [results.get(t.id, ExecutionResult(
            task_id=t.id,
            status=ExecutionStatus.FAILED,
            error="Dependency not satisfied"
        )) for t in subtasks]
    
    async def _execute_single(
        self,
        subtask: Any,
        prompt: str,
        context: dict
    ) -> ExecutionResult:
        """Execute a single subtask."""
        started_at = datetime.now()
        
        try:
            # Create agent
            agent = self.agent_factory(subtask.role, prompt)
            
            # Execute (this would use the actual agent execution)
            # For now, simulate
            output = await self._run_agent(agent, prompt, context)
            
            return ExecutionResult(
                task_id=subtask.id,
                status=ExecutionStatus.COMPLETED,
                output=output,
                started_at=started_at,
                completed_at=datetime.now(),
                tools_used=getattr(agent, 'tools_used', [])
            )
            
        except Exception as e:
            return ExecutionResult(
                task_id=subtask.id,
                status=ExecutionStatus.FAILED,
                error=str(e),
                started_at=started_at,
                completed_at=datetime.now()
            )
    
    async def _run_agent(
        self,
        agent: Any,
        prompt: str,
        context: dict
    ) -> str:
        """Run an agent with the given prompt."""
        # This would integrate with the actual agent execution system
        # For now, return a placeholder
        return f"[Agent execution would run here with prompt: {prompt[:50]}...]"
    
    def _enhance_prompt_with_context(
        self,
        prompt: str,
        accumulated_output: str,
        dependencies: list[str]
    ) -> str:
        """Enhance prompt with context from previous tasks."""
        if not accumulated_output:
            return prompt
        
        return f"""Previous work completed:
{accumulated_output}

---

Your task:
{prompt}

Build upon the previous work to complete your assigned task."""
    
    def _build_synthesis_prompt(
        self,
        original_task: str,
        results: list[ExecutionResult]
    ) -> str:
        """Build prompt for synthesizing worker results."""
        worker_outputs = "\n\n".join([
            f"=== {r.task_id} ===\n{r.output}"
            for r in results
        ])
        
        return f"""Synthesize the following worker results into a cohesive final answer.

Original task: {original_task}

Worker outputs:
{worker_outputs}

Provide:
1. Summary of key findings/results
2. Integrated solution or answer
3. Any recommendations or next steps"""
    
    def create_plan(
        self,
        original_task: str,
        strategy: str,
        subtasks: list[Any]
    ) -> ExecutionPlan:
        """Create an execution plan from subtasks."""
        executions = [
            ExecutionResult(task_id=st.id, status=ExecutionStatus.PENDING)
            for st in subtasks
        ]
        
        return ExecutionPlan(
            task_id=f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            original_task=original_task,
            strategy=strategy,
            executions=executions
        )
