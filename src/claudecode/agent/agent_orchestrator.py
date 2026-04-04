"""Agent orchestrator for multi-agent workflows."""

import asyncio
from enum import Enum
from typing import Any, Callable
from dataclasses import dataclass, field
from datetime import datetime

from .agent_manager import (
    get_agent_manager,
    SubAgent,
    AgentStatus,
    ENHANCED_AGENT_DEFINITIONS,
)


class WorkflowType(Enum):
    """Types of multi-agent workflows."""
    SEQUENTIAL = "sequential"  # Agents run one after another
    PARALLEL = "parallel"      # Agents run simultaneously
    MAP_REDUCE = "map_reduce"  # Map task to multiple agents, then reduce
    SUPERVISOR = "supervisor"  # Supervisor delegates to workers
    DEBATE = "debate"          # Agents debate/discuss a topic
    PIPELINE = "pipeline"      # Output of one agent feeds into next


@dataclass
class WorkflowStep:
    """A step in a workflow."""
    step_id: str
    agent_type: str
    prompt: str
    depends_on: list[str] = field(default_factory=list)
    output_key: str | None = None
    condition: str | None = None  # Conditional execution


@dataclass
class WorkflowResult:
    """Result of a workflow execution."""
    workflow_id: str
    status: AgentStatus
    results: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    started_at: str | None = None
    completed_at: str | None = None


class AgentOrchestrator:
    """Orchestrates multi-agent workflows."""
    
    def __init__(self):
        self.agent_manager = get_agent_manager()
        self._progress_callbacks: list[Callable[[str, dict], None]] = []
    
    def register_progress_callback(self, callback: Callable[[str, dict], None]):
        """Register progress callback."""
        self._progress_callbacks.append(callback)
    
    def _notify_progress(self, event: str, data: dict):
        """Notify progress callbacks."""
        for callback in self._progress_callbacks:
            try:
                callback(event, data)
            except Exception:
                pass
    
    async def run_sequential(
        self,
        steps: list[WorkflowStep],
        context: dict[str, Any] | None = None,
    ) -> WorkflowResult:
        """Run steps sequentially."""
        workflow_id = f"wf_{datetime.now().timestamp()}"
        results = {}
        errors = []
        
        self._notify_progress("workflow:started", {
            "workflow_id": workflow_id,
            "type": "sequential",
            "steps": len(steps),
        })
        
        started_at = datetime.now().isoformat()
        
        for i, step in enumerate(steps):
            self._notify_progress("step:started", {
                "workflow_id": workflow_id,
                "step_id": step.step_id,
                "step_number": i + 1,
            })
            
            # Check dependencies
            if step.depends_on:
                for dep in step.depends_on:
                    if dep not in results:
                        errors.append(f"Dependency {dep} not satisfied for step {step.step_id}")
                        continue
            
            # Create and run agent
            agent = self.agent_manager.create_agent(agent_type=step.agent_type)
            self.agent_manager.set_agent_status(agent.agent_id, AgentStatus.RUNNING)
            
            try:
                # Build prompt with context
                prompt = self._build_prompt(step.prompt, results, context)
                
                # Run agent (simplified - would use actual query engine)
                result = await self._run_agent_task(agent, prompt)
                
                if step.output_key:
                    results[step.output_key] = result
                
                results[step.step_id] = result
                
                self.agent_manager.set_agent_status(agent.agent_id, AgentStatus.COMPLETED)
                
                self._notify_progress("step:completed", {
                    "workflow_id": workflow_id,
                    "step_id": step.step_id,
                    "result": result,
                })
                
            except Exception as e:
                errors.append(f"Step {step.step_id} failed: {e}")
                self.agent_manager.set_agent_status(agent.agent_id, AgentStatus.FAILED)
                
                self._notify_progress("step:failed", {
                    "workflow_id": workflow_id,
                    "step_id": step.step_id,
                    "error": str(e),
                })
        
        completed_at = datetime.now().isoformat()
        
        status = AgentStatus.COMPLETED if not errors else AgentStatus.FAILED
        
        self._notify_progress("workflow:completed", {
            "workflow_id": workflow_id,
            "status": status.value,
        })
        
        return WorkflowResult(
            workflow_id=workflow_id,
            status=status,
            results=results,
            errors=errors,
            started_at=started_at,
            completed_at=completed_at,
        )
    
    async def run_parallel(
        self,
        steps: list[WorkflowStep],
        context: dict[str, Any] | None = None,
        max_concurrency: int = 5,
    ) -> WorkflowResult:
        """Run steps in parallel."""
        workflow_id = f"wf_{datetime.now().timestamp()}"
        results = {}
        errors = []
        
        self._notify_progress("workflow:started", {
            "workflow_id": workflow_id,
            "type": "parallel",
            "steps": len(steps),
        })
        
        started_at = datetime.now().isoformat()
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrency)
        
        async def run_step(step: WorkflowStep) -> tuple[str, Any, str | None]:
            async with semaphore:
                self._notify_progress("step:started", {
                    "workflow_id": workflow_id,
                    "step_id": step.step_id,
                })
                
                agent = self.agent_manager.create_agent(agent_type=step.agent_type)
                self.agent_manager.set_agent_status(agent.agent_id, AgentStatus.RUNNING)
                
                try:
                    prompt = self._build_prompt(step.prompt, results, context)
                    result = await self._run_agent_task(agent, prompt)
                    
                    self.agent_manager.set_agent_status(agent.agent_id, AgentStatus.COMPLETED)
                    
                    self._notify_progress("step:completed", {
                        "workflow_id": workflow_id,
                        "step_id": step.step_id,
                    })
                    
                    return step.step_id, result, None
                    
                except Exception as e:
                    self.agent_manager.set_agent_status(agent.agent_id, AgentStatus.FAILED)
                    return step.step_id, None, str(e)
        
        # Run all steps
        tasks = [run_step(step) for step in steps]
        step_results = await asyncio.gather(*tasks)
        
        for step_id, result, error in step_results:
            if error:
                errors.append(f"Step {step_id} failed: {error}")
            else:
                results[step_id] = result
        
        completed_at = datetime.now().isoformat()
        status = AgentStatus.COMPLETED if not errors else AgentStatus.FAILED
        
        self._notify_progress("workflow:completed", {
            "workflow_id": workflow_id,
            "status": status.value,
        })
        
        return WorkflowResult(
            workflow_id=workflow_id,
            status=status,
            results=results,
            errors=errors,
            started_at=started_at,
            completed_at=completed_at,
        )
    
    async def run_supervisor(
        self,
        task: str,
        worker_types: list[str],
        supervisor_type: str = "planner",
    ) -> WorkflowResult:
        """Run supervisor-worker pattern."""
        workflow_id = f"wf_{datetime.now().timestamp()}"
        started_at = datetime.now().isoformat()
        
        self._notify_progress("workflow:started", {
            "workflow_id": workflow_id,
            "type": "supervisor",
            "workers": len(worker_types),
        })
        
        # Create supervisor
        supervisor = self.agent_manager.create_agent(agent_type=supervisor_type)
        self.agent_manager.set_agent_status(supervisor.agent_id, AgentStatus.RUNNING)
        
        # Supervisor breaks down task
        decompose_prompt = f"""Break down this task into subtasks for {len(worker_types)} workers.

Task: {task}

Available worker types: {', '.join(worker_types)}

Provide a JSON array of subtasks, where each subtask has:
- "worker_type": which worker should handle it
- "description": what the worker should do
- "expected_output": what result to expect

Output only valid JSON."""
        
        try:
            decomposition = await self._run_agent_task(supervisor, decompose_prompt)
            # Parse subtasks (simplified)
            subtasks = self._parse_subtasks(decomposition)
        except Exception as e:
            return WorkflowResult(
                workflow_id=workflow_id,
                status=AgentStatus.FAILED,
                errors=[f"Task decomposition failed: {e}"],
                started_at=started_at,
                completed_at=datetime.now().isoformat(),
            )
        
        # Create workers and assign tasks
        workers = []
        worker_tasks = []
        
        for worker_type, subtask in zip(worker_types, subtasks):
            worker = self.agent_manager.create_agent(agent_type=worker_type)
            self.agent_manager.set_agent_status(worker.agent_id, AgentStatus.RUNNING)
            workers.append(worker)
            
            worker_tasks.append(self._run_agent_task(worker, subtask))
        
        # Run workers in parallel
        worker_results = await asyncio.gather(*worker_tasks, return_exceptions=True)
        
        # Collect results
        results = {}
        errors = []
        
        for i, (worker, result) in enumerate(zip(workers, worker_results)):
            if isinstance(result, Exception):
                errors.append(f"Worker {i} failed: {result}")
                self.agent_manager.set_agent_status(worker.agent_id, AgentStatus.FAILED)
            else:
                results[f"worker_{i}"] = result
                self.agent_manager.set_agent_status(worker.agent_id, AgentStatus.COMPLETED)
        
        # Supervisor synthesizes results
        synthesis_prompt = f"""Synthesize the results from all workers into a final answer.

Original task: {task}

Worker results:
{results}

Provide a comprehensive final answer."""
        
        try:
            final_answer = await self._run_agent_task(supervisor, synthesis_prompt)
            results["final_answer"] = final_answer
            self.agent_manager.set_agent_status(supervisor.agent_id, AgentStatus.COMPLETED)
        except Exception as e:
            errors.append(f"Result synthesis failed: {e}")
            self.agent_manager.set_agent_status(supervisor.agent_id, AgentStatus.FAILED)
        
        status = AgentStatus.COMPLETED if not errors else AgentStatus.FAILED
        
        self._notify_progress("workflow:completed", {
            "workflow_id": workflow_id,
            "status": status.value,
        })
        
        return WorkflowResult(
            workflow_id=workflow_id,
            status=status,
            results=results,
            errors=errors,
            started_at=started_at,
            completed_at=datetime.now().isoformat(),
        )
    
    async def run_debate(
        self,
        topic: str,
        agent_types: list[str],
        rounds: int = 3,
    ) -> WorkflowResult:
        """Run a debate between multiple agents."""
        workflow_id = f"wf_{datetime.now().timestamp()}"
        started_at = datetime.now().isoformat()
        
        self._notify_progress("workflow:started", {
            "workflow_id": workflow_id,
            "type": "debate",
            "participants": len(agent_types),
            "rounds": rounds,
        })
        
        # Create debate agents
        agents = [
            self.agent_manager.create_agent(agent_type=at)
            for at in agent_types
        ]
        
        for agent in agents:
            self.agent_manager.set_agent_status(agent.agent_id, AgentStatus.RUNNING)
        
        debate_history = []
        
        # Run debate rounds
        for round_num in range(rounds):
            self._notify_progress("debate:round", {
                "workflow_id": workflow_id,
                "round": round_num + 1,
            })
            
            round_responses = []
            
            for i, agent in enumerate(agents):
                # Build prompt with debate history
                prompt = self._build_debate_prompt(topic, debate_history, agent.definition.name)
                
                try:
                    response = await self._run_agent_task(agent, prompt)
                    round_responses.append({
                        "agent": agent.definition.name,
                        "response": response,
                    })
                except Exception as e:
                    round_responses.append({
                        "agent": agent.definition.name,
                        "error": str(e),
                    })
            
            debate_history.append({
                "round": round_num + 1,
                "responses": round_responses,
            })
        
        # Mark all as completed
        for agent in agents:
            self.agent_manager.set_agent_status(agent.agent_id, AgentStatus.COMPLETED)
        
        self._notify_progress("workflow:completed", {
            "workflow_id": workflow_id,
            "status": "completed",
        })
        
        return WorkflowResult(
            workflow_id=workflow_id,
            status=AgentStatus.COMPLETED,
            results={
                "topic": topic,
                "rounds": rounds,
                "debate_history": debate_history,
            },
            started_at=started_at,
            completed_at=datetime.now().isoformat(),
        )
    
    def _build_prompt(
        self,
        template: str,
        results: dict[str, Any],
        context: dict[str, Any] | None,
    ) -> str:
        """Build prompt with context."""
        prompt = template
        
        # Substitute previous results
        for key, value in results.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in prompt:
                prompt = prompt.replace(placeholder, str(value))
        
        # Add context
        if context:
            prompt += f"\n\nContext: {context}"
        
        return prompt
    
    def _build_debate_prompt(
        self,
        topic: str,
        history: list[dict],
        agent_name: str,
    ) -> str:
        """Build debate prompt."""
        prompt = f"""You are participating in a debate on the topic:

{topic}

Your role: {agent_name}

Previous discussion:
"""
        
        for round_data in history:
            prompt += f"\nRound {round_data['round']}:\n"
            for resp in round_data['responses']:
                prompt += f"  {resp['agent']}: {resp.get('response', resp.get('error', ''))[:200]}...\n"
        
        prompt += "\nProvide your perspective on the topic, responding to previous points if relevant."
        
        return prompt
    
    def _parse_subtasks(self, decomposition: str) -> list[str]:
        """Parse subtasks from decomposition."""
        # Simplified parsing - in reality would use proper JSON parsing
        import re
        
        # Try to find JSON array
        match = re.search(r'\[.*\]', decomposition, re.DOTALL)
        if match:
            try:
                import json
                data = json.loads(match.group())
                return [item.get("description", str(item)) for item in data]
            except json.JSONDecodeError:
                pass
        
        # Fallback: split by numbered items
        lines = [l.strip() for l in decomposition.split('\n') if l.strip()]
        return [l for l in lines if l and not l.startswith(('```', '['))]
    
    async def _run_agent_task(self, agent: SubAgent, prompt: str) -> str:
        """Run a single agent task (simplified)."""
        from ..utils.model_client import get_model_client
        
        client = get_model_client()
        
        messages = [
            {"role": "system", "content": agent.definition.system_prompt},
            {"role": "user", "content": prompt},
        ]
        
        # This would use the actual query engine in production
        # For now, simulate a response
        response_chunks = []
        
        try:
            # Try to get actual response from model
            async for chunk in client.stream_chat(messages):
                response_chunks.append(chunk)
        except Exception:
            # Fallback: return a placeholder
            return f"[Agent {agent.agent_id} would process: {prompt[:100]}...]"
        
        return "".join(response_chunks)


# Global orchestrator
_orchestrator: AgentOrchestrator | None = None


def get_orchestrator() -> AgentOrchestrator:
    """Get global orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator
