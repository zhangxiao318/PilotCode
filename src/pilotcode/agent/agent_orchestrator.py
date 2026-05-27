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

    def __init__(self, cwd: str | None = None):
        self.agent_manager = get_agent_manager()
        self._progress_callbacks: list[Callable[[str, dict], None]] = []
        self._cwd = cwd or str(os.getcwd())

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

            adapter = MissionAdapter(cwd=self._cwd)
            result = await adapter.run(
                request,
                progress_callback=self._notify_progress,
                explore_first=False,
                cwd=self._cwd,
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
        import re

        # Try to find JSON array using balanced-bracket scan
        # (avoids greedy-regex over-matching when trailing text contains [])
        for match in re.finditer(r"\[", decomposition):
            start = match.start()
            depth = 1
            for i in range(start + 1, len(decomposition)):
                if decomposition[i] == "[":
                    depth += 1
                elif decomposition[i] == "]":
                    depth -= 1
                    if depth == 0:
                        candidate = decomposition[start : i + 1]
                        try:
                            import json

                            data = json.loads(candidate)
                            return [item.get("description", str(item)) for item in data]
                        except json.JSONDecodeError:
                            pass
                        break

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

        # Sidechain transcript: we'll record the full conversation
        sidechain_messages: list[Any] = []

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
        sidechain_messages = list(messages)

        agent.status = AgentStatus.RUNNING
        max_iterations = agent.definition.max_turns

        try:
            for iteration in range(max_iterations):
                agent.turns += 1
                response = None
                # Force text-only on the last turn so the agent cannot keep
                # calling tools forever — it MUST produce a summary.
                tools_for_turn = all_tools if iteration < max_iterations - 1 else None
                async for chunk in client.chat_completion(
                    messages, tools=tools_for_turn, stream=False
                ):
                    response = chunk

                if not response:
                    break

                # Handle both streaming (choices/delta) and non-streaming formats
                if "choices" in response:
                    choice = response.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    content = delta.get("content") or ""
                    tool_calls_raw = delta.get("tool_calls")
                else:
                    content = response.get("content") or ""
                    tool_calls_raw = response.get("tool_calls")

                # Fallback: parse XML/pseudo-XML tool calls embedded in content
                # (some local models output tool calls as text instead of native tool_calls)
                if content and not tool_calls_raw:
                    import re

                    parsed_tools: list[dict[str, Any]] = []
                    # Pattern 1: <tool_call>...<function=Name>...<parameter=key>value</parameter>...</function>...</tool_call>
                    pattern = r"<tool_call>\s*<function=(\w+)>\s*(.*?)\s*</function>\s*</tool_call>"
                    for match in re.finditer(pattern, content, re.DOTALL):
                        tool_name = match.group(1)
                        params_block = match.group(2)
                        arguments: dict[str, Any] = {}
                        param_pattern = r"<parameter=(\w+)>(.*?)</parameter>"
                        for pmatch in re.finditer(param_pattern, params_block, re.DOTALL):
                            arguments[pmatch.group(1)] = pmatch.group(2).strip()
                        if tool_name:
                            parsed_tools.append(
                                {
                                    "id": f"call_{len(parsed_tools)}",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": json.dumps(arguments),
                                    },
                                }
                            )
                    # Pattern 3: <function=Name>...<parameter=key>value</parameter>...</function>
                    if not parsed_tools:
                        pattern3 = r"<function=(\w+)>\s*(.*?)\s*</function>"
                        for match in re.finditer(pattern3, content, re.DOTALL):
                            tool_name = match.group(1)
                            params_block = match.group(2)
                            arguments: dict[str, Any] = {}
                            param_pattern = r"<parameter=(\w+)>(.*?)</parameter>"
                            for pmatch in re.finditer(param_pattern, params_block, re.DOTALL):
                                arguments[pmatch.group(1)] = pmatch.group(2).strip()
                            if tool_name:
                                parsed_tools.append(
                                    {
                                        "id": f"call_{len(parsed_tools)}",
                                        "function": {
                                            "name": tool_name,
                                            "arguments": json.dumps(arguments),
                                        },
                                    }
                                )
                    if parsed_tools:
                        tool_calls_raw = parsed_tools
                        # Remove XML tool call blocks from content so it doesn't appear in output
                        content = re.sub(
                            r"<tool_call>\s*<function=\w+>\s*.*?\s*</function>\s*</tool_call>",
                            "",
                            content,
                            flags=re.DOTALL,
                        )
                        content = re.sub(
                            r"<function=\w+>\s*.*?\s*</function>", "", content, flags=re.DOTALL
                        )
                        content = content.strip()

                # Build assistant message with content and/or tool_calls
                # Always include content (even empty string) so local backends
                # like llama.cpp don't choke on missing field.
                assistant_msg = MCMessage(role="assistant", content=content or "")
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
                sidechain_messages.append(assistant_msg)

                if content and not tool_calls_raw:
                    # Plain text response (no tool calls) — agent is done
                    agent.status = AgentStatus.COMPLETED
                    agent.output = content
                    # Persist state so crash recovery knows this agent finished
                    try:
                        get_agent_manager()._save_agent(agent)
                    except Exception:
                        pass
                    # Save sidechain transcript
                    self._save_sidechain(agent, sidechain_messages)
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
                                result.get_text_for_assistant()
                                if result.data and not result.is_error
                                else (result.error or "Error")
                            )
                        else:
                            result_text = (
                                f"Tool '{tool_name}' is not available or not allowed "
                                f"for this agent. Allowed tools: {agent.definition.allowed_tools}"
                            )

                        tool_result_msg = MCMessage(
                            role="tool",
                            content=result_text,
                            tool_call_id=tool_call_id,
                            name=tool_name,
                        )
                        messages.append(tool_result_msg)
                        sidechain_messages.append(tool_result_msg)
                    # Nudge the agent to summarize when we are near the turn limit.
                    if iteration >= max_iterations - 3:
                        messages.append(
                            MCMessage(
                                role="user",
                                content="You have gathered enough information. Based on the tool results above, provide a concise summary of your findings. Do NOT call any more tools.",
                            )
                        )
                    continue

                # No content and no tool calls
                break

            # Fallback: if agent executed tools but never produced a final
            # text summary, synthesize a basic report from the tool results
            # instead of flooding the UI with raw JSON/repr.
            if not agent.output and agent.turns > 1:
                summary_parts: list[str] = []
                files_read: list[str] = []
                searches_done: list[str] = []
                commands_run: list[str] = []
                for msg in messages:
                    if getattr(msg, "role", None) != "tool":
                        continue
                    tname = getattr(msg, "name", "tool")
                    tcontent = str(getattr(msg, "content", "") or "")
                    if tname in ("FileRead", "read"):
                        # Extract file path from the first line or JSON
                        m = __import__("re").search(r'"file_path"\s*:\s*"([^"]+)"', tcontent)
                        if m:
                            files_read.append(m.group(1))
                        else:
                            m = __import__("re").search(r"file_path='([^']+)'", tcontent)
                            if m:
                                files_read.append(m.group(1))
                    elif tname in ("Grep", "CodeSearch"):
                        # Count matches roughly
                        lines = [line for line in tcontent.splitlines() if line.strip()]
                        searches_done.append(f"{tname} ({len(lines)} matches)")
                    elif tname == "Bash":
                        # Keep command brief
                        first = tcontent.splitlines()[0] if tcontent else ""
                        if len(first) > 80:
                            first = first[:77] + "..."
                        commands_run.append(first)
                if files_read:
                    summary_parts.append("Files examined: " + ", ".join(files_read[-5:]))
                if searches_done:
                    summary_parts.append("Searches: " + "; ".join(searches_done[-3:]))
                if commands_run:
                    summary_parts.append("Commands: " + "; ".join(commands_run[-3:]))
                if summary_parts:
                    agent.output = "\n".join(summary_parts)
                else:
                    tools_used = [
                        getattr(msg, "name", "tool")
                        for msg in messages
                        if getattr(msg, "role", None) == "tool"
                    ]
                    agent.output = (
                        f"[Agent completed {agent.turns} turn(s) using "
                        f"{', '.join(tools_used[-3:]) or 'tools'} but did not return a summary.]"
                    )

            agent.status = AgentStatus.COMPLETED
            # Persist final state for crash-recovery cleanup
            try:
                get_agent_manager()._save_agent(agent)
            except Exception:
                pass
            # Save sidechain transcript
            self._save_sidechain(agent, sidechain_messages)
            return agent.output or ""
        except asyncio.CancelledError:
            agent.status = AgentStatus.FAILED
            # Persist state so restart cleanup can identify this dead worker
            try:
                get_agent_manager()._save_agent(agent)
            except Exception:
                pass
            raise
        except Exception as e:
            import traceback

            tb = traceback.format_exc()
            agent.status = AgentStatus.FAILED
            agent.error = f"{e}\n{tb}"
            # Persist state so restart cleanup can identify this dead worker
            try:
                get_agent_manager()._save_agent(agent)
            except Exception:
                pass
            return f"[Agent {agent.agent_id} failed: {e}]\n{tb}"

    def _save_sidechain(self, agent: SubAgent, messages: list[Any]) -> None:
        """Save sub-agent conversation to a sidechain transcript file."""
        try:
            from ..services.sidechain_transcript import save_sidechain_transcript

            sidechain_path = save_sidechain_transcript(
                agent_id=agent.agent_id,
                messages=messages,
                summary=agent.output or "",
                agent_type=agent.definition.name,
                tools_used=agent.tools_used,
                worktree_path=agent.worktree_path,
            )
            agent.transcript_path = sidechain_path
        except Exception:
            pass


# Global orchestrator
_orchestrator: AgentOrchestrator | None = None


def get_orchestrator() -> AgentOrchestrator:
    """Get global orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator
