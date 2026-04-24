"""UI adapter for P-EVR orchestration.

Bridges natural language requests to structured Mission execution via LLM.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any, Callable

from pilotcode.utils.model_client import get_model_client, Message
from pilotcode.query_engine import QueryEngine, QueryEngineConfig
from pilotcode.tools.registry import get_all_tools
from pilotcode.state.app_state import get_default_app_state
from pilotcode.state.store import Store
from pilotcode.tools.base import ToolUseContext
from pilotcode.permissions.tool_executor import get_tool_executor
from pilotcode.permissions.permission_manager import (
    get_permission_manager,
    PermissionLevel,
    PermissionRequest,
)
from pilotcode.types.message import ToolUseMessage

from .task_spec import Mission, Phase, TaskSpec, ComplexityLevel, Constraints, AcceptanceCriterion
from .orchestrator import Orchestrator, OrchestratorConfig, ExecutionResult, VerificationResult
from .context_strategy import (
    ContextStrategy,
    ContextStrategySelector,
    MissionPlanAdjuster,
    StrategyMetrics,
)


class MissionAdapter:
    """Adapter that converts user requests into executed missions.

    Usage:
        adapter = MissionAdapter()
        result = await adapter.run("Implement OAuth2 login")
    """

    # Complexity-to-turns mapping for the LLM worker loop
    DEFAULT_TURN_LIMITS: dict[ComplexityLevel, int] = {
        ComplexityLevel.VERY_SIMPLE: 5,
        ComplexityLevel.SIMPLE: 10,
        ComplexityLevel.MODERATE: 20,
        ComplexityLevel.COMPLEX: 30,
        ComplexityLevel.VERY_COMPLEX: 50,
    }

    def __init__(
        self,
        cancel_event: asyncio.Event | None = None,
        max_worker_turns: int | None = None,
        context_budget: int = 16000,
    ):
        self._cancel_event = cancel_event or asyncio.Event()
        self._max_worker_turns = max_worker_turns
        self.context_budget = context_budget
        self.strategy = ContextStrategySelector.select(context_budget)
        self.plan_adjuster = MissionPlanAdjuster(strategy=self.strategy)

        # Apply strategy to orchestrator config
        orch_config = OrchestratorConfig()
        self.plan_adjuster.apply_to_orchestrator_config(orch_config)
        self._orchestrator = Orchestrator(config=orch_config)

        self._register_workers()
        self._register_verifiers()
        self._setup_permission_callback()

    # ------------------------------------------------------------------
    # Internal setup
    # ------------------------------------------------------------------

    def _register_workers(self) -> None:
        """Register the LLM-based worker for all task types."""
        for worker_type in ("simple", "standard", "complex", "auto"):
            self._orchestrator.register_worker(worker_type, self._llm_worker)

    def _register_verifiers(self) -> None:
        """Register a minimal L1 verifier that checks execution success."""
        self._orchestrator.register_verifier(1, self._simple_verifier)

    def _setup_permission_callback(self) -> None:
        """Set a non-interactive permission callback for tool execution."""
        pm = get_permission_manager()
        pm.set_permission_callback(self._auto_allow_permission)

    @staticmethod
    async def _auto_allow_permission(request: PermissionRequest) -> PermissionLevel:
        """Auto-allow all tool requests during autonomous execution."""
        return PermissionLevel.ALLOW

    @staticmethod
    async def _simple_verifier(task: TaskSpec, exec_result: ExecutionResult) -> VerificationResult:
        """Basic verifier: execution must succeed."""
        if not exec_result.success:
            return VerificationResult(
                task_id=task.id,
                level=1,
                passed=False,
                score=0.0,
                feedback=exec_result.error or "Execution failed without details",
                verdict="REJECT",
            )
        return VerificationResult(
            task_id=task.id,
            level=1,
            passed=True,
            score=100.0,
            verdict="APPROVE",
        )

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    async def _plan_mission(self, user_request: str) -> Mission:
        """Use an LLM to decompose a user request into a Mission."""
        if self._cancel_event.is_set():
            raise asyncio.CancelledError("Cancelled by user")

        client = get_model_client()

        # Build base prompt + strategy-specific guidance
        base_prompt = (
            "You are a mission planner for a software development AI system.\n"
            "Given a user's request, decompose it into a structured plan with phases and tasks.\n"
            "Output ONLY a JSON object with no markdown formatting. The JSON must match this schema:\n"
            "\n"
            "{\n"
            '  "title": "Short mission title",\n'
            '  "phases": [\n'
            "    {\n"
            '      "phase_id": "phase_1",\n'
            '      "title": "Phase title",\n'
            '      "description": "What this phase accomplishes",\n'
            '      "tasks": [\n'
            "        {\n"
            '          "id": "task_1",\n'
            '          "title": "Task title",\n'
            '          "objective": "Detailed description of what to implement",\n'
            '          "inputs": ["input files or context"],\n'
            '          "outputs": ["expected output files"],\n'
            '          "dependencies": [],\n'
            '          "estimated_complexity": 3,\n'
            '          "acceptance_criteria": [\n'
            '            {"description": "Criterion 1", "verification_method": "test"}\n'
            "          ],\n"
            '          "constraints": {\n'
            '            "max_lines": null,\n'
            '            "must_use": [],\n'
            '            "must_not_use": [],\n'
            '            "patterns": []\n'
            "          },\n"
            '          "worker_type": "auto"\n'
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "\n"
            "Rules:\n"
            "- complexity: 1 (very simple) to 5 (very complex)\n"
            "- dependencies: list of task ids that must complete before this task\n"
            "- Keep tasks granular (ideally 50-200 lines of code each)\n"
            "- Use snake_case for all IDs\n"
            "- Include at least one phase, but no more than 5 phases for typical requests\n"
        )
        strategy_suffix = self.plan_adjuster.get_plan_prompt_suffix()
        system_prompt = base_prompt + strategy_suffix

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_request),
        ]

        accumulated = ""
        async for chunk in client.chat_completion(
            messages=messages,
            temperature=0.3,
            stream=False,
        ):
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            c = delta.get("content")
            if c:
                accumulated += c

        if not accumulated:
            raise ValueError("LLM returned an empty plan")

        plan_data = self._extract_json(accumulated)
        raw_mission = Mission.from_dict(plan_data)

        # Ensure mission_id is set
        if not raw_mission.mission_id:
            raw_mission.mission_id = f"mission_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        if not raw_mission.title:
            raw_mission.title = user_request[:80]
        if not raw_mission.requirement:
            raw_mission.requirement = user_request
        if not raw_mission.created_at:
            raw_mission.created_at = datetime.now(timezone.utc).isoformat()

        # Tag with context budget and strategy
        raw_mission.context_budget = self.context_budget
        raw_mission.context_strategy = self.strategy.value

        # Apply strategy-aware plan adjustments
        mission = self.plan_adjuster.adjust(raw_mission)

        return mission

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        """Extract JSON from LLM output, stripping markdown fences if present."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # Some models wrap JSON in a single backtick block without language tag
        if text.startswith("`") and text.endswith("`"):
            text = text.strip("`").strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            # Attempt to find the first JSON object in the text
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            raise ValueError(f"Failed to parse plan JSON: {exc}") from exc

    # ------------------------------------------------------------------
    # LLM Worker
    # ------------------------------------------------------------------

    def _build_worker_prompt(self, task: TaskSpec, context: dict[str, Any]) -> str:
        """Build execution prompt for a single task."""
        parts = [
            f"[Task] {task.title}",
            f"[Objective] {task.objective}",
            "",
        ]

        constraints: Constraints = context.get("constraints") or task.constraints
        if constraints.max_lines:
            parts.append(f"[Constraint] File must not exceed {constraints.max_lines} lines")
        if constraints.must_use:
            parts.append(f"[Must Use] {', '.join(constraints.must_use)}")
        if constraints.must_not_use:
            parts.append(f"[Must Not Use] {', '.join(constraints.must_not_use)}")
        if constraints.patterns:
            parts.append(f"[Patterns] {', '.join(constraints.patterns)}")

        acceptance_criteria = context.get("acceptance_criteria") or task.acceptance_criteria
        if acceptance_criteria:
            parts.extend(["", "[Acceptance Criteria]"])
            for ac in acceptance_criteria:
                parts.append(f"  - {ac.description}")

        parts.extend(
            [
                "",
                "[Instructions]",
                "1. Focus on the task objective. Do not modify unrelated code.",
                "2. Use the available tools to read, write, and edit files as needed.",
                "3. After making changes, verify they meet the acceptance criteria.",
                "4. Return a concise summary of what you did.",
            ]
        )

        return "\n".join(parts)

    async def _llm_worker(self, task: TaskSpec, context: dict[str, Any]) -> ExecutionResult:
        """Execute a task using QueryEngine with tool access."""
        if self._cancel_event.is_set():
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error="Cancelled by user",
            )

        prompt = self._build_worker_prompt(task, context)

        app_state = get_default_app_state()
        store = Store(app_state)

        # Determine turn limit based on task complexity
        complexity = task.estimated_complexity
        max_turns = (
            self._max_worker_turns
            if self._max_worker_turns is not None
            else self.DEFAULT_TURN_LIMITS.get(complexity, 20)
        )

        config = QueryEngineConfig(
            cwd=app_state.cwd,
            tools=get_all_tools(),
            get_app_state=store.get_state,
            set_app_state=store.set_state,
            max_turns=max(5, max_turns // 2),  # QueryEngine internal budget
        )
        engine = QueryEngine(config)
        executor = get_tool_executor()

        final_content = ""
        artifacts: dict[str, Any] = {}
        total_turns = 0

        try:
            while total_turns < max_turns:
                if self._cancel_event.is_set():
                    return ExecutionResult(
                        task_id=task.id,
                        success=False,
                        error="Cancelled by user",
                    )

                # Submit to LLM
                user_prompt = prompt if total_turns == 0 else "Please continue."
                pending_tools: list[ToolUseMessage] = []
                async for result in engine.submit_message(user_prompt):
                    if self._cancel_event.is_set():
                        return ExecutionResult(
                            task_id=task.id,
                            success=False,
                            error="Cancelled by user",
                        )
                    msg = result.message
                    if hasattr(msg, "content") and msg.content and result.is_complete:
                        final_content = str(msg.content)
                    if isinstance(msg, ToolUseMessage):
                        pending_tools.append(msg)

                if not pending_tools:
                    break

                # Execute tools and feed results back
                tool_ctx = ToolUseContext(
                    get_app_state=store.get_state,
                    set_app_state=lambda f: store.set_state(f),
                )

                for tu in pending_tools:
                    if self._cancel_event.is_set():
                        return ExecutionResult(
                            task_id=task.id,
                            success=False,
                            error="Cancelled by user",
                        )

                    exec_result = await executor.execute_tool_by_name(tu.name, tu.input, tool_ctx)

                    if exec_result.success and exec_result.result is not None:
                        result_text = (
                            str(exec_result.result.data) if exec_result.result.data else "Success"
                        )
                    else:
                        result_text = exec_result.message or "Tool execution failed"

                    engine.add_tool_result(
                        tu.tool_use_id,
                        result_text,
                        is_error=not exec_result.success,
                    )

                total_turns += 1

            # Collect changed files as artifacts
            changed_files: list[str] = []
            for msg in engine.messages:
                if isinstance(msg, ToolUseMessage) and msg.name in (
                    "FileWrite",
                    "FileEdit",
                    "ApplyPatch",
                ):
                    for key in ("path", "file_path", "filepath"):
                        val = msg.input.get(key)
                        if val and isinstance(val, str):
                            changed_files.append(val)
                            break

            if changed_files:
                # Deduplicate while preserving order
                seen: set[str] = set()
                artifacts["changed_files"] = [
                    f for f in changed_files if not (f in seen or seen.add(f))
                ]

            artifacts["conversation_length"] = len(engine.messages)
            artifacts["final_response"] = final_content

            return ExecutionResult(
                task_id=task.id,
                success=True,
                output=final_content,
                artifacts=artifacts,
                token_usage=engine.count_tokens(),
            )

        except Exception as exc:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error=f"Worker execution failed: {exc}",
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        user_request: str,
        progress_callback: Callable[[str, dict], None] | None = None,
    ) -> dict[str, Any]:
        """Plan and execute a mission from a natural language request.

        Args:
            user_request: The user's natural language request.
            progress_callback: Optional callback(event_type, data) for progress updates.

        Returns:
            Execution summary dict with keys: mission_id, snapshot, success, error, mission, metrics.
        """
        try:
            mission = await self._plan_mission(user_request)

            if progress_callback:
                progress_callback(
                    "mission:planned",
                    {
                        "mission_id": mission.mission_id,
                        "title": mission.title,
                        "phases": [p.to_dict() for p in mission.phases],
                        "strategy": self.strategy.value,
                        "context_budget": self.context_budget,
                    },
                )

            # Wire cancellation through progress callbacks
            def _wrapped_progress(event: str, data: dict) -> None:
                if self._cancel_event.is_set():
                    mid = data.get("mission_id")
                    if mid:
                        self._orchestrator.cancel_mission(mid)
                if progress_callback:
                    progress_callback(event, data)

            self._orchestrator.on_progress(_wrapped_progress)

            result = await self._orchestrator.run(mission)
            result["mission"] = mission.to_dict()
            result["success"] = result.get("snapshot", {}).get("status") == "completed"

            # Collect strategy metrics
            metrics = StrategyMetrics(self.strategy, self.context_budget)
            metrics.total_tasks = len(mission.all_tasks())
            metrics.total_phases = len(mission.phases)
            result["metrics"] = metrics.to_dict()
            result["strategy"] = self.strategy.value

            return result

        except asyncio.CancelledError:
            return {
                "success": False,
                "error": "Cancelled by user",
                "mission_id": "",
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "mission_id": "",
            }
