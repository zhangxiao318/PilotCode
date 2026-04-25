"""Agent orchestrator for multi-agent workflows."""

import asyncio
import os
from enum import Enum
from typing import Any, Callable
from dataclasses import dataclass, field
from datetime import datetime

from .agent_manager import (
    get_agent_manager,
    SubAgent,
    AgentStatus,
)
from ..utils.model_client import get_model_client
from ..tools.base import ToolUseContext


class WorkflowType(Enum):
    """Types of multi-agent workflows."""

    SEQUENTIAL = "sequential"  # Agents run one after another
    PARALLEL = "parallel"  # Agents run simultaneously
    MAP_REDUCE = "map_reduce"  # Map task to multiple agents, then reduce
    SUPERVISOR = "supervisor"  # Supervisor delegates to workers
    DEBATE = "debate"  # Agents debate/discuss a topic
    PIPELINE = "pipeline"  # Output of one agent feeds into next


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

    async def _run_via_adapter(
        self,
        request: str,
        strategy: str,
        context: dict[str, Any] | None = None,
    ) -> WorkflowResult:
        """Delegate workflow execution to the unified MissionAdapter."""
        workflow_id = f"wf_{datetime.now().timestamp()}"
        started_at = datetime.now().isoformat()

        self._notify_progress(
            "workflow:started",
            {
                "workflow_id": workflow_id,
                "type": strategy,
                "request": request,
            },
        )

        try:
            from ..orchestration.adapter import MissionAdapter

            adapter = MissionAdapter()
            result = await adapter.run(
                request,
                progress_callback=self._notify_progress,
                explore_first=False,
            )

            success = result.get("success", False)
            task_outputs = result.get("task_outputs", {})

            # Flatten task outputs into results dict
            results: dict[str, Any] = {}
            for task_id, info in task_outputs.items():
                if isinstance(info, dict):
                    results[task_id] = info.get("output", "")
                else:
                    results[task_id] = info

            # Special keys for workflow_cmd.py compatibility
            if strategy == "supervisor" and results:
                results["final_answer"] = (
                    "\n\n".join(str(v) for v in results.values() if isinstance(v, str))
                    or "No output available"
                )

            if strategy == "debate" and results:
                results["debate_history"] = [
                    {
                        "round": 1,
                        "responses": [
                            {"agent": k, "response": v}
                            for k, v in results.items()
                            if isinstance(v, str)
                        ],
                    }
                ]

            errors = [result.get("error")] if result.get("error") else []

            self._notify_progress(
                "workflow:completed",
                {
                    "workflow_id": workflow_id,
                    "status": "completed" if success else "failed",
                },
            )

            return WorkflowResult(
                workflow_id=result.get("mission_id", workflow_id),
                status=AgentStatus.COMPLETED if success else AgentStatus.FAILED,
                results=results,
                errors=errors,
                started_at=started_at,
                completed_at=datetime.now().isoformat(),
            )

        except Exception as e:
            self._notify_progress(
                "workflow:failed",
                {
                    "workflow_id": workflow_id,
                    "error": str(e),
                },
            )
            return WorkflowResult(
                workflow_id=workflow_id,
                status=AgentStatus.FAILED,
                errors=[str(e)],
                started_at=started_at,
                completed_at=datetime.now().isoformat(),
            )

    async def run_sequential(
        self,
        steps: list[WorkflowStep],
        context: dict[str, Any] | None = None,
    ) -> WorkflowResult:
        """Run steps sequentially via MissionAdapter."""
        request = "Execute the following workflow steps sequentially:\n\n"
        for step in steps:
            deps = f" (after: {', '.join(step.depends_on)})" if step.depends_on else ""
            request += f"- [{step.agent_type}] {step.step_id}{deps}: {step.prompt}\n"
        if context and context.get("original_prompt"):
            request += f"\nOriginal task: {context['original_prompt']}"
        return await self._run_via_adapter(request, "sequential", context)

    async def run_parallel(
        self,
        steps: list[WorkflowStep],
        context: dict[str, Any] | None = None,
        max_concurrency: int = 5,
    ) -> WorkflowResult:
        """Run steps in parallel via MissionAdapter."""
        request = f"Execute the following {len(steps)} tasks in parallel:\n\n"
        for step in steps:
            request += f"- [{step.agent_type}] {step.step_id}: {step.prompt}\n"
        if context and context.get("original_prompt"):
            request += f"\nOriginal task: {context['original_prompt']}"
        return await self._run_via_adapter(request, "parallel", context)

    async def run_supervisor(
        self,
        task: str,
        worker_types: list[str],
        supervisor_type: str = "planner",
    ) -> WorkflowResult:
        """Run supervisor-worker pattern via MissionAdapter."""
        request = (
            f"Supervisor ({supervisor_type}) manages workers ({', '.join(worker_types)}) "
            f"to complete this task:\n\n{task}\n\n"
            f"The supervisor should break down the task, delegate to workers, "
            f"and synthesize the final answer."
        )
        return await self._run_via_adapter(request, "supervisor")

    async def run_debate(
        self,
        topic: str,
        agent_types: list[str],
        rounds: int = 3,
    ) -> WorkflowResult:
        """Run a debate between multiple agents via MissionAdapter."""
        request = (
            f"Debate on topic: {topic}\n\n"
            f"Participants: {', '.join(agent_types)}\n"
            f"Rounds: {rounds}\n\n"
            f"Each participant should provide their perspective, responding to previous points. "
            f"After all rounds, provide a comprehensive debate summary."
        )
        return await self._run_via_adapter(request, "debate")

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
            for resp in round_data["responses"]:
                prompt += (
                    f"  {resp['agent']}: {resp.get('response', resp.get('error', ''))[:200]}...\n"
                )

        prompt += (
            "\nProvide your perspective on the topic, responding to previous points if relevant."
        )

        return prompt

    def _parse_subtasks(self, decomposition: str) -> list[str]:
        """Parse subtasks from decomposition."""
        # Simplified parsing - in reality would use proper JSON parsing
        import re

        # Try to find JSON array
        match = re.search(r"\[.*\]", decomposition, re.DOTALL)
        if match:
            try:
                import json

                data = json.loads(match.group())
                return [item.get("description", str(item)) for item in data]
            except json.JSONDecodeError:
                pass

        # Fallback: split by numbered items
        lines = [line.strip() for line in decomposition.split("\n") if line.strip()]
        return [line for line in lines if line and not line.startswith(("```", "["))]

    async def _run_agent_task(
        self,
        agent: SubAgent,
        prompt: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> str:
        """Run a single agent task with tool support and allowed_tools filtering."""
        import json
        from ..tools.registry import get_tool_by_name
        from ..utils.model_client import Message as MCMessage, ToolCall

        client = get_model_client()
        ctx = ToolUseContext(cwd=os.getcwd())

        # Build tool list from allowed_tools
        all_tools = []
        for tool_name in agent.definition.allowed_tools:
            tool = get_tool_by_name(tool_name)
            if tool:
                # description may be a callable; invoke it to get the string
                raw_desc = tool.description
                if callable(raw_desc):
                    try:
                        desc = raw_desc(tool.input_schema(), {})
                    except Exception:
                        desc = tool.name
                else:
                    desc = raw_desc
                all_tools.append(
                    {
                        "name": tool.name,
                        "description": desc,
                        "input_schema": tool.input_schema.model_json_schema(),
                    }
                )

        messages = [
            MCMessage(role="system", content=agent.definition.system_prompt),
            MCMessage(role="user", content=prompt),
        ]

        agent.status = AgentStatus.RUNNING
        max_iterations = agent.definition.max_turns

        try:
            for _ in range(max_iterations):
                agent.turns += 1
                response = None
                async for chunk in client.chat_completion(messages, tools=all_tools, stream=False):
                    response = chunk

                if not response:
                    break

                choice = response.get("choices", [{}])[0]
                delta = choice.get("delta", {})

                content = delta.get("content") or ""
                tool_calls_raw = delta.get("tool_calls")

                # Build assistant message with content and/or tool_calls
                assistant_msg = MCMessage(role="assistant", content=content or None)
                if tool_calls_raw:
                    assistant_msg.tool_calls = []
                    for tc in tool_calls_raw:
                        fn = tc.get("function", {})
                        try:
                            args = json.loads(fn.get("arguments", "{}"))
                        except json.JSONDecodeError:
                            args = {}
                        assistant_msg.tool_calls.append(
                            ToolCall(
                                id=tc.get("id", ""),
                                name=fn.get("name", ""),
                                arguments=args,
                            )
                        )
                messages.append(assistant_msg)

                if content and not tool_calls_raw:
                    # Plain text response (no tool calls) — agent is done
                    agent.status = AgentStatus.COMPLETED
                    agent.output = content
                    return content

                if tool_calls_raw:
                    # Execute tool calls and feed results back
                    for tc in tool_calls_raw:
                        fn = tc.get("function", {})
                        tool_name = fn.get("name", "")
                        tool_call_id = tc.get("id", "")
                        try:
                            args = json.loads(fn.get("arguments", "{}"))
                        except json.JSONDecodeError:
                            args = {}

                        if progress_callback:
                            progress_callback(f"  [agent {agent.definition.name}] {tool_name}")

                        tool = get_tool_by_name(tool_name)
                        if tool and tool.name in agent.definition.allowed_tools:
                            parsed = tool.input_schema(**args)

                            async def _allow(*a, **k):
                                return {"behavior": "allow"}

                            result = await tool.call(parsed, ctx, _allow, None, lambda x: None)
                            result_text = (
                                str(result.data)
                                if result.data and not result.is_error
                                else (result.error or "Error")
                            )
                        else:
                            result_text = (
                                f"Tool '{tool_name}' is not available or not allowed "
                                f"for this agent. Allowed tools: {agent.definition.allowed_tools}"
                            )

                        messages.append(
                            MCMessage(
                                role="tool",
                                content=result_text,
                                tool_call_id=tool_call_id,
                                name=tool_name,
                            )
                        )
                    continue

                # No content and no tool calls
                break

            agent.status = AgentStatus.COMPLETED
            return agent.output or ""
        except Exception as e:
            import traceback

            traceback.print_exc()
            agent.status = AgentStatus.FAILED
            agent.error = str(e)
            return f"[Agent {agent.agent_id} failed: {e}]"


# Global orchestrator
_orchestrator: AgentOrchestrator | None = None


def get_orchestrator() -> AgentOrchestrator:
    """Get global orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator
