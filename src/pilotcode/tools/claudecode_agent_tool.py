"""ClaudeCode-style Agent tool for task decomposition and orchestration.

This module implements the Agent tool that matches ClaudeCode's behavior:
- Automatic task decomposition
- Sub-agent spawning with specific roles
- Result aggregation and synthesis
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Callable, Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class SubAgentStatus(Enum):
    """Status of a sub-agent execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SubAgentResult:
    """Result from a sub-agent execution."""

    agent_id: str
    role: str
    task: str
    result: str
    status: SubAgentStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


@dataclass
class TaskDecomposition:
    """Decomposed task structure."""

    original_task: str
    subtasks: list[dict] = field(default_factory=list)
    strategy: str = "sequential"  # sequential, parallel, supervisor


class AgentInput(BaseModel):
    """Input for the Agent tool.

    Matches ClaudeCode's Agent tool interface.
    """

    description: str = Field(
        description="Brief description of what this agent should do (1-2 sentences)"
    )
    prompt: str = Field(
        description="The full prompt/task for the sub-agent with all necessary context"
    )
    subagent_type: Optional[str] = Field(
        default=None,
        description="Optional: Agent type - coder, debugger, explainer, tester, reviewer, planner, explorer",
    )
    name: Optional[str] = Field(
        default=None, description="Optional: Custom name for this agent instance"
    )
    model: Optional[str] = Field(
        default=None, description="Optional: Model to use (defaults to parent's model)"
    )
    context_files: list[str] = Field(
        default_factory=list, description="Optional: Files to include in the agent's context"
    )
    max_turns: int = Field(default=10, description="Maximum number of turns this agent can take")
    temperature: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Temperature for the agent's responses"
    )


class AgentOutput(BaseModel):
    """Output from the Agent tool."""

    agent_id: str
    role: str
    result: str
    status: str
    turns_used: int
    tools_used: list[str]
    execution_time_seconds: float


class TaskOrchestrator:
    """Orchestrates task decomposition and sub-agent execution.

    Similar to ClaudeCode's internal orchestration logic.
    """

    def __init__(self, query_engine_factory: Callable, tool_executor: Any):
        self.query_engine_factory = query_engine_factory
        self.tool_executor = tool_executor
        self.active_agents: dict[str, dict] = {}

    async def decompose_task(self, task: str, context: str = "") -> TaskDecomposition:
        """Decompose a complex task into subtasks.

        Uses LLM to analyze the task and determine optimal decomposition strategy.
        """
        decomposition_prompt = f"""Analyze this task and decompose it into subtasks if beneficial.

Task: {task}

Context: {context}

Determine:
1. Should this task be decomposed? (simple tasks don't need decomposition)
2. If yes, what are the subtasks?
3. What execution strategy is best? (sequential, parallel, or supervisor)

Respond with JSON:
{{
    "should_decompose": true/false,
    "strategy": "sequential|parallel|supervisor",
    "reasoning": "explanation",
    "subtasks": [
        {{
            "description": "brief description",
            "role": "coder|debugger|explainer|tester|reviewer|planner|explorer",
            "prompt": "full prompt for this subtask",
            "dependencies": [] // indices of subtasks this depends on
        }}
    ]
}}

If should_decompose is false, return empty subtasks array."""

        # Use lightweight query to get decomposition
        try:
            response = await self._quick_query(decomposition_prompt)
            data = json.loads(self._extract_json(response))

            if data.get("should_decompose", False) and data.get("subtasks"):
                return TaskDecomposition(
                    original_task=task,
                    subtasks=data["subtasks"],
                    strategy=data.get("strategy", "sequential"),
                )
        except Exception:
            pass

        # Fallback: no decomposition
        return TaskDecomposition(original_task=task, subtasks=[], strategy="sequential")

    async def execute_subagent(
        self,
        agent_id: str,
        role: str,
        prompt: str,
        context: ToolUseContext,
        max_turns: int = 10,
        progress_callback: Optional[Callable[[str, dict], None]] = None,
    ) -> SubAgentResult:
        """Execute a single sub-agent."""
        started_at = datetime.now()

        if progress_callback:
            progress_callback(
                "agent_started", {"agent_id": agent_id, "role": role, "task_preview": prompt[:100]}
            )

        try:
            # Create query engine for this agent
            query_engine = self.query_engine_factory()

            # Build system prompt based on role
            system_prompt = self._get_role_system_prompt(role)

            # Execute the task
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]

            result_content = ""
            tools_used = []
            turns = 0

            while turns < max_turns:
                turns += 1

                # Get response from model
                response = await self._execute_query(query_engine, messages)

                if response.get("tool_calls"):
                    # Execute tool calls
                    for tool_call in response["tool_calls"]:
                        tool_name = tool_call.get("name", "")
                        tools_used.append(tool_name)

                        if progress_callback:
                            progress_callback(
                                "tool_call", {"agent_id": agent_id, "tool": tool_name}
                            )

                        # Execute tool and add result
                        tool_result = await self._execute_tool(tool_call, context)
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.get("id", ""),
                                "content": tool_result,
                            }
                        )
                else:
                    # Final response
                    result_content = response.get("content", "")
                    break

            completed_at = datetime.now()
            execution_time = (completed_at - started_at).total_seconds()

            if progress_callback:
                progress_callback(
                    "agent_completed",
                    {
                        "agent_id": agent_id,
                        "role": role,
                        "turns": turns,
                        "execution_time": execution_time,
                    },
                )

            return SubAgentResult(
                agent_id=agent_id,
                role=role,
                task=prompt,
                result=result_content,
                status=SubAgentStatus.COMPLETED,
                started_at=started_at,
                completed_at=completed_at,
                tools_used=list(set(tools_used)),
            )

        except Exception as e:
            return SubAgentResult(
                agent_id=agent_id,
                role=role,
                task=prompt,
                result="",
                status=SubAgentStatus.FAILED,
                started_at=started_at,
                error=str(e),
                tools_used=[],
            )

    async def execute_parallel(
        self,
        subtasks: list[dict],
        context: ToolUseContext,
        max_concurrency: int = 3,
        progress_callback: Optional[Callable[[str, dict], None]] = None,
    ) -> list[SubAgentResult]:
        """Execute multiple sub-agents in parallel."""
        semaphore = asyncio.Semaphore(max_concurrency)

        async def run_with_limit(task: dict) -> SubAgentResult:
            async with semaphore:
                agent_id = f"subagent_{uuid.uuid4().hex[:8]}"
                return await self.execute_subagent(
                    agent_id=agent_id,
                    role=task.get("role", "coder"),
                    prompt=task.get("prompt", ""),
                    context=context,
                    max_turns=task.get("max_turns", 10),
                    progress_callback=progress_callback,
                )

        tasks = [run_with_limit(subtask) for subtask in subtasks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(
                    SubAgentResult(
                        agent_id=f"subagent_{i}",
                        role=subtasks[i].get("role", "unknown"),
                        task=subtasks[i].get("prompt", ""),
                        result="",
                        status=SubAgentStatus.FAILED,
                        started_at=datetime.now(),
                        error=str(result),
                    )
                )
            else:
                processed_results.append(result)

        return processed_results

    async def execute_sequential(
        self,
        subtasks: list[dict],
        context: ToolUseContext,
        progress_callback: Optional[Callable[[str, dict], None]] = None,
    ) -> list[SubAgentResult]:
        """Execute sub-agents sequentially with result passing."""
        results = []
        accumulated_results = ""

        for i, subtask in enumerate(subtasks):
            agent_id = f"subagent_{uuid.uuid4().hex[:8]}"

            # Enhance prompt with previous results if needed
            prompt = subtask.get("prompt", "")
            if accumulated_results and i > 0:
                prompt = f"""Previous results:
{accumulated_results}

---

Current task:
{prompt}"""

            result = await self.execute_subagent(
                agent_id=agent_id,
                role=subtask.get("role", "coder"),
                prompt=prompt,
                context=context,
                max_turns=subtask.get("max_turns", 10),
                progress_callback=progress_callback,
            )

            results.append(result)

            # Accumulate for next iteration
            if result.status == SubAgentStatus.COMPLETED:
                accumulated_results += f"\n\n=== {result.role} ===\n{result.result}"

        return results

    def _get_role_system_prompt(self, role: str) -> str:
        """Get system prompt for a specific role."""
        prompts = {
            "coder": """You are an expert software developer. Your focus is:
- Writing clean, efficient, well-documented code
- Following best practices and design patterns
- Writing tests alongside implementation
- Using tools to read, write, and edit files

Always explain your approach before making changes.
Use <complete> when finished with the task.""",
            "debugger": """You are an expert debugging assistant. Your focus is:
- Analyzing error messages and stack traces
- Finding root causes of bugs
- Suggesting minimal fixes
- Verifying fixes work

Always trace through the code to understand the issue.
Use <complete> when the bug is identified and fixed.""",
            "explainer": """You are an expert explainer. Your focus is:
- Making complex code understandable
- Explaining architectural decisions
- Documenting code behavior
- Providing usage examples

Use clear language and relevant examples.
Use <complete> when the explanation is thorough.""",
            "tester": """You are an expert testing assistant. Your focus is:
- Writing comprehensive unit tests
- Creating integration tests
- Ensuring edge cases are covered
- Maintaining test quality

Always verify tests can run and pass.
Use <complete> when test coverage is adequate.""",
            "reviewer": """You are an expert code reviewer. Your focus is:
- Identifying potential bugs and issues
- Checking code style and conventions
- Suggesting improvements
- Verifying best practices

Be constructive and specific in your feedback.
Use <complete> when the review is complete.""",
            "planner": """You are an expert planning assistant. Your focus is:
- Breaking down complex tasks
- Creating implementation plans
- Identifying dependencies and risks
- Suggesting architectural approaches

Create clear, actionable plans.
Use <complete> when the plan is ready for execution.""",
            "explorer": """You are an expert exploration assistant. Your focus is:
- Understanding unfamiliar codebases
- Mapping project structure
- Finding relevant files and functions
- Creating codebase summaries

Be thorough in your exploration.
Use <complete> when you have a good understanding.""",
        }

        return prompts.get(role, prompts.get("coder", ""))

    def _extract_json(self, text: str) -> str:
        """Extract JSON from text that may contain markdown."""
        # Try to find JSON in code blocks
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            return text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            return text[start:end].strip()
        else:
            # Try to find JSON object/array
            start = text.find("{")
            if start != -1:
                # Find matching end brace
                brace_count = 0
                for i, char in enumerate(text[start:]):
                    if char == "{":
                        brace_count += 1
                    elif char == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            return text[start : start + i + 1]
            return text

    async def _quick_query(self, prompt: str) -> str:
        """Execute a quick query for task decomposition."""
        # Simplified - in real implementation would use proper model client
        return "{}"

    async def _execute_query(self, query_engine: Any, messages: list) -> dict:
        """Execute query and return structured response."""
        # Simplified - in real implementation would use actual query engine
        return {"content": "", "tool_calls": None}

    async def _execute_tool(self, tool_call: dict, context: ToolUseContext) -> str:
        """Execute a tool call and return result."""
        # Simplified - in real implementation would use tool executor
        return ""


class AgentExecutor:
    """Executes the Agent tool with full ClaudeCode-style behavior."""

    def __init__(self):
        self.orchestrator: Optional[TaskOrchestrator] = None

    def initialize(self, query_engine_factory: Callable, tool_executor: Any):
        """Initialize with required dependencies."""
        self.orchestrator = TaskOrchestrator(query_engine_factory, tool_executor)

    async def execute(
        self,
        input_data: AgentInput,
        context: ToolUseContext,
        can_use_tool: Any,
        parent_message: Any,
        on_progress: Any,
    ) -> ToolResult[AgentOutput]:
        """Execute the Agent tool.

        This matches ClaudeCode's Agent tool behavior.
        """
        if not self.orchestrator:
            return ToolResult(data=None, error="Agent executor not initialized")

        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        role = input_data.subagent_type or "coder"

        # Progress callback
        def progress_callback(event: str, data: dict):
            if on_progress:
                on_progress({"event": event, **data})

        # Check if task should be decomposed
        decomposition = await self.orchestrator.decompose_task(
            input_data.prompt, input_data.description
        )

        if decomposition.subtasks and len(decomposition.subtasks) > 1:
            # Execute with decomposition
            if decomposition.strategy == "parallel":
                results = await self.orchestrator.execute_parallel(
                    decomposition.subtasks, context, progress_callback=progress_callback
                )
            else:
                results = await self.orchestrator.execute_sequential(
                    decomposition.subtasks, context, progress_callback=progress_callback
                )

            # Synthesize results
            final_result = self._synthesize_results(results, input_data.prompt)
            total_turns = sum(r.tools_used.__len__() for r in results)  # Approximation
            all_tools = list(set(tool for r in results for tool in r.tools_used))

            return ToolResult(
                data=AgentOutput(
                    agent_id=agent_id,
                    role=role,
                    result=final_result,
                    status="completed",
                    turns_used=total_turns,
                    tools_used=all_tools,
                    execution_time_seconds=sum(
                        (r.completed_at - r.started_at).total_seconds()
                        for r in results
                        if r.completed_at
                    ),
                )
            )
        else:
            # Execute single agent without decomposition
            result = await self.orchestrator.execute_subagent(
                agent_id=agent_id,
                role=role,
                prompt=input_data.prompt,
                context=context,
                max_turns=input_data.max_turns,
                progress_callback=progress_callback,
            )

            execution_time = 0.0
            if result.completed_at:
                execution_time = (result.completed_at - result.started_at).total_seconds()

            return ToolResult(
                data=AgentOutput(
                    agent_id=agent_id,
                    role=role,
                    result=result.result,
                    status=result.status.value,
                    turns_used=len(result.tools_used) + 1,  # Approximation
                    tools_used=result.tools_used,
                    execution_time_seconds=execution_time,
                ),
                error=result.error,
            )

    def _synthesize_results(self, results: list[SubAgentResult], original_task: str) -> str:
        """Synthesize results from multiple sub-agents."""
        parts = ["# Task Results\n"]

        for result in results:
            status_icon = "✓" if result.status == SubAgentStatus.COMPLETED else "✗"
            parts.append(f"\n## {status_icon} {result.role.upper()}\n")
            parts.append(result.result)

        parts.append("\n---\n")
        parts.append("Task completed with decomposition.")

        return "\n".join(parts)


# Global executor instance
_agent_executor = AgentExecutor()


def get_agent_executor() -> AgentExecutor:
    """Get the global agent executor."""
    return _agent_executor


def initialize_agent_executor(query_engine_factory: Callable, tool_executor: Any):
    """Initialize the agent executor with dependencies."""
    _agent_executor.initialize(query_engine_factory, tool_executor)


async def agent_tool_call(
    input_data: AgentInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[AgentOutput]:
    """Main entry point for the Agent tool."""
    executor = get_agent_executor()
    return await executor.execute(input_data, context, can_use_tool, parent_message, on_progress)


# Create and register the tool
AgentTool = build_tool(
    name="Agent",
    description=lambda x, o: f"Spawn sub-agent: {x.description[:50]}...",
    input_schema=AgentInput,
    output_schema=AgentOutput,
    call=agent_tool_call,
    aliases=["agent", "subagent"],
    search_hint="Create a sub-agent to work on a specific task",
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: False,
    render_tool_use_message=lambda x, o: f"🤖 Creating {x.subagent_type or 'sub'} agent: {x.description[:60]}...",
)

register_tool(AgentTool)
