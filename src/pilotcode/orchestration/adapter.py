"""UI adapter for P-EVR orchestration.

Bridges natural language requests to structured Mission execution via LLM.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any, Callable

from pilotcode.utils.model_client import get_model_client, Message, ModelClient
from pilotcode.utils.model_router import ModelRouter, ModelTier, TaskType
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
from pilotcode.types.message import ToolUseMessage, AssistantMessage
from pilotcode.services.cleanup import SessionCleanup

from .task_spec import Mission, Phase, TaskSpec, ComplexityLevel, Constraints, AcceptanceCriterion
from .orchestrator import Orchestrator, OrchestratorConfig
from .results import ExecutionResult
from .verifier.base import VerificationResult, Verdict
from .verifiers.adapter_verifiers import (
    l1_simple_verifier,
    l2_test_verifier,
    l3_code_review_verifier,
)
from .explorers.code_explorer import explore_codebase
from .context_strategy import (
    ContextStrategy,
    ContextStrategySelector,
    MissionPlanAdjuster,
    StrategyMetrics,
)
from .project_memory import ProjectMemory, FailedAttempt
from ..model_capability import (
    load_capability_or_default,
    AdaptiveConfigMapper,
    RuntimeCalibrator,
    TaskOutcome,
    classify_failure,
    classify_planning_failure,
    PlanningStrategy,
    VerifierStrategy,
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
        project_memory: ProjectMemory | None = None,
        capability_path: str | None = None,
    ):
        self._cancel_event = cancel_event or asyncio.Event()
        self._max_worker_turns = max_worker_turns
        self.context_budget = context_budget
        self.project_memory = project_memory or ProjectMemory()

        # Load model capability profile (adaptive configuration)
        from pilotcode.utils.config import get_global_config

        current_model = get_global_config().default_model or "unknown"
        self.capability = load_capability_or_default(
            path=capability_path,
            model_name=current_model,
        )

        # Warn if capability profile is for a different model
        if self.capability.model_name != current_model and self.capability.model_name != "unknown":
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                "Capability profile mismatch: stored='%s' vs current='%s'. "
                "Run 'pilotcode config --test capability' to regenerate.",
                self.capability.model_name,
                current_model,
            )

        self.adaptive_config = AdaptiveConfigMapper.from_capability(self.capability)
        self.calibrator = RuntimeCalibrator(self.capability)

        # Compensation engine for dimension-specific weak-model compensation
        from .adaptive_edit import CompensationEngine

        self.compensation = CompensationEngine(self.adaptive_config, self.capability)

        # Multi-model router for tiered task routing
        self.router = ModelRouter()

        # Tool concurrency limit from user config (local models default 2, remote 5)
        self._tool_concurrency_limit = get_global_config().tool_concurrency_limit

        # Context strategy (legacy) + adaptive override
        self.strategy = ContextStrategySelector.select(context_budget, capability=self.capability)
        self.plan_adjuster = MissionPlanAdjuster(strategy=self.strategy)

        # Apply adaptive configuration to strategy config
        from ..model_capability.adaptive_config import apply_adaptive_config_to_strategy_config

        self.plan_adjuster.config = apply_adaptive_config_to_strategy_config(
            self.adaptive_config, self.plan_adjuster.config
        )

        # Apply strategy to orchestrator config
        orch_config = OrchestratorConfig()
        self.plan_adjuster.apply_to_orchestrator_config(orch_config)
        orch_config.default_task_timeout = self.adaptive_config.stagnation_threshold_seconds
        self._orchestrator = Orchestrator(config=orch_config)

        self._register_workers()
        self._register_verifiers()
        self._setup_permission_callback()

        # Progressive disclosure: allow _llm_worker to emit real-time progress
        self._progress_callback: Callable[[str, dict], None] | None = None

    # ------------------------------------------------------------------
    # Internal setup
    # ------------------------------------------------------------------

    def _register_workers(self) -> None:
        """Register the LLM-based worker for all task types."""
        for worker_type in ("simple", "standard", "complex", "auto"):
            self._orchestrator.register_worker(worker_type, self._llm_worker)

    def _register_verifiers(self) -> None:
        """Register L1/L2/L3 verifiers based on adaptive configuration."""
        self._orchestrator.register_verifier(1, l1_simple_verifier)

        # L2: test verifier — optionally enforce tests for weak code-review models
        if self.adaptive_config.enforce_test_before_mark_complete:
            self._orchestrator.register_verifier(2, self._enforced_l2_verifier)
        else:
            self._orchestrator.register_verifier(2, l2_test_verifier)

        if self.adaptive_config.verifier_strategy == VerifierStrategy.FULL_L3:
            self._orchestrator.register_verifier(3, l3_code_review_verifier)
        elif self.adaptive_config.verifier_strategy == VerifierStrategy.SIMPLIFIED_L3:
            from .verifiers.adaptive_verifiers import simplified_l3_verifier

            self._orchestrator.register_verifier(3, simplified_l3_verifier)
        elif self.adaptive_config.verifier_strategy == VerifierStrategy.STATIC_ONLY:
            from .verifiers.adaptive_verifiers import static_analysis_l3_verifier

            self._orchestrator.register_verifier(3, static_analysis_l3_verifier)

    async def _enforced_l2_verifier(
        self, task: TaskSpec, exec_result: ExecutionResult
    ) -> VerificationResult:
        """L2 verifier wrapper that forces test runs for weak review models."""
        from .task_spec import AcceptanceCriterion

        # Inject a synthetic test criterion if none exists
        if not any(ac.verification_method in ("test", "pytest") for ac in task.acceptance_criteria):
            task.acceptance_criteria.append(
                AcceptanceCriterion(
                    description="Run project tests to verify no regressions",
                    verification_method="test",
                )
            )
        return await l2_test_verifier(task, exec_result)

    def _setup_permission_callback(self) -> None:
        """Set a non-interactive permission callback for tool execution."""
        pm = get_permission_manager()
        pm.set_permission_callback(self._auto_allow_permission)

    @staticmethod
    async def _auto_allow_permission(request: PermissionRequest) -> PermissionLevel:
        """Auto-allow all tool requests during autonomous execution."""
        return PermissionLevel.ALLOW

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    async def _plan_mission(
        self, user_request: str, exploration: dict[str, Any] | None = None
    ) -> Mission:
        """Use an LLM to decompose a user request into a Mission.

        If exploration data is provided, the plan is grounded in actual codebase structure.
        """
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
            "CRITICAL RULES:\n"
            "- complexity: 1 (very simple) to 5 (very complex)\n"
            "- dependencies: list of task ids that must complete before this task\n"
            "- Keep tasks granular (ideally 50-200 lines of code each)\n"
            "- Use snake_case for all IDs\n"
            "- Include at least one phase, but no more than 5 phases for typical requests\n"
            "- ONLY reference files that actually exist in the codebase (see exploration data below)\n"
            "- If a file doesn't exist, the task must create it\n"
        )
        strategy_suffix = self.plan_adjuster.get_plan_prompt_suffix()
        system_prompt = base_prompt + strategy_suffix

        # Inject planning compensation for weak planners
        planning_comp = self.compensation.get_planning_prompt_suffix()
        if planning_comp:
            system_prompt += planning_comp

        # Inject exploration context if available
        user_content = user_request
        if exploration:
            explore_section = "\n\n[CODEBASE EXPLORATION DATA]\n"
            if exploration.get("files"):
                files = exploration["files"][:30]
                explore_section += (
                    f"Known files ({len(files)}):\n" + "\n".join(f"  - {f}" for f in files) + "\n"
                )
            if exploration.get("key_files"):
                explore_section += (
                    f"Key files matching request: {', '.join(exploration['key_files'][:10])}\n"
                )
            if self.project_memory.conventions:
                explore_section += "Detected conventions:\n"
                for k, v in self.project_memory.conventions.items():
                    explore_section += f"  - {k}: {v}\n"
            user_content = user_request + explore_section

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_content),
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

        # Try to parse JSON, with optional self-correction for weak models
        try:
            plan_data = self._extract_json_static(accumulated)
        except ValueError as exc:
            if (
                self.adaptive_config.json_retry_on_failure
                and self.adaptive_config.json_max_retries > 0
            ):
                try:
                    plan_data = await self._attempt_json_correction(accumulated, user_request)
                except Exception:
                    self.calibrator.record_planning_outcome(
                        task_id="plan_extract",
                        raw_plan=accumulated,
                        parse_error=str(exc),
                        success=False,
                    )
                    raise ValueError(f"Failed to parse plan JSON after correction: {exc}") from exc
            else:
                self.calibrator.record_planning_outcome(
                    task_id="plan_extract",
                    raw_plan=accumulated,
                    parse_error=str(exc),
                    success=False,
                )
                raise

        # Ensure required keys exist before from_dict (LLM may omit fields)
        if "mission_id" not in plan_data:
            plan_data["mission_id"] = (
                f"mission_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            )
        if "title" not in plan_data:
            plan_data["title"] = user_request[:80]
        if "requirement" not in plan_data:
            plan_data["requirement"] = user_request
        if "phases" not in plan_data:
            plan_data["phases"] = []
        if "created_at" not in plan_data:
            plan_data["created_at"] = datetime.now(timezone.utc).isoformat()

        raw_mission = Mission.from_dict(plan_data)

        # Ensure mission_id is set
        if not raw_mission.mission_id:
            raw_mission.mission_id = (
                f"mission_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            )
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

    async def _attempt_json_correction(self, raw_text: str, original_prompt: str) -> dict[str, Any]:
        """Ask the model to fix malformed JSON output."""
        if not self.adaptive_config.enable_self_correction:
            raise ValueError("JSON self-correction disabled by adaptive config")

        client = get_model_client()
        correction_prompt = (
            f"The following text was supposed to be valid JSON but has errors.\n\n"
            f"Original request: {original_prompt[:200]}\n\n"
            f"Malformed output:\n```\n{raw_text[:800]}\n```\n\n"
            f"Please output ONLY the corrected JSON, with no markdown fences or explanations."
        )
        accumulated = ""
        async for chunk in client.chat_completion(
            messages=[
                Message(role="system", content="You fix malformed JSON. Output valid JSON only."),
                Message(role="user", content=correction_prompt),
            ],
            temperature=0.1,
            stream=False,
        ):
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            c = delta.get("content")
            if c:
                accumulated += c

        # Try to extract JSON from corrected output
        corrected = self._extract_json_static(accumulated)
        if corrected:
            # Record successful self-correction as positive signal
            self.calibrator.record_planning_outcome(
                task_id="json_correction",
                raw_plan=accumulated,
                success=True,
            )
            return corrected

        raise ValueError("JSON self-correction failed")

    def _extract_json_with_correction(self, text: str, original_prompt: str) -> dict[str, Any]:
        """Extract JSON with optional self-correction loop."""
        try:
            return self._extract_json_static(text)
        except ValueError as exc:
            if (
                self.adaptive_config.json_retry_on_failure
                and self.adaptive_config.json_max_retries > 0
            ):
                # Schedule async correction — since this is called from async context,
                # we need to handle it in the caller. For now, record the failure.
                self.calibrator.record_planning_outcome(
                    task_id="plan_extract",
                    raw_plan=text,
                    parse_error=str(exc),
                    success=False,
                )
            raise

    @staticmethod
    def _extract_json_static(text: str) -> dict[str, Any]:
        """Extract JSON from LLM output, stripping markdown fences if present.

        Uses bracket-counting to find the first balanced JSON object,
        avoiding the pitfalls of greedy regex matching.
        """
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
            # Bracket-counting: find the first balanced { ... } block
            start = text.find("{")
            if start != -1:
                depth = 0
                in_string = False
                escape = False
                for i, ch in enumerate(text[start:], start=start):
                    if escape:
                        escape = False
                        continue
                    if ch == "\\":
                        escape = True
                        continue
                    if ch == '"' and not in_string:
                        in_string = True
                    elif ch == '"' and in_string:
                        in_string = False
                    elif not in_string:
                        if ch == "{":
                            depth += 1
                        elif ch == "}":
                            depth -= 1
                            if depth == 0:
                                candidate = text[start : i + 1]
                                try:
                                    return json.loads(candidate)
                                except json.JSONDecodeError:
                                    # Try common LLM fixes: trailing commas, single quotes
                                    fixed = _fix_common_json_errors(candidate)
                                    try:
                                        return json.loads(fixed)
                                    except json.JSONDecodeError:
                                        pass
                                break
            raise ValueError(f"Failed to parse plan JSON: {exc}") from exc

    @staticmethod
    def _fix_common_json_errors(text: str) -> str:
        """Fix common JSON errors produced by LLMs."""
        # Remove trailing commas before } or ]
        text = re.sub(r",(\s*[}\]])", r"\1", text)
        # Convert single-quoted strings to double-quoted (naive, best-effort)
        # Only handles simple cases like {'key': 'value'}
        text = re.sub(r"(?<!\\)'([^']*?)'(\s*[:}\],])", r'"\1"\2', text)
        return text

    # Backward-compatible alias
    _extract_json = _extract_json_static

    # ------------------------------------------------------------------
    # LLM Worker
    # ------------------------------------------------------------------

    def _build_worker_prompt(self, task: TaskSpec, context: dict[str, Any]) -> str:
        """Build execution prompt for a single task."""
        parts = []

        # Inject project memory so worker knows what has been discovered
        if self.project_memory:
            mem_section = self.project_memory.to_prompt_section()
            if mem_section:
                parts.append(mem_section)
                parts.append("")

        parts.extend(
            [
                f"[Task] {task.title}",
                f"[Objective] {task.objective}",
                "",
            ]
        )

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
                "3. Check PROJECT MEMORY before reading files — avoid re-reading known files.",
                "4. After making changes, verify they meet the acceptance criteria.",
                "5. Return a concise summary of what you did and any new files discovered.",
            ]
        )

        # Inject compensation guidance based on dimension-specific weaknesses
        compensation_guidance = self.compensation.get_worker_prompt_suffix()
        if compensation_guidance:
            parts.append(compensation_guidance)

        return "\n".join(parts)

    async def _llm_worker(self, task: TaskSpec, context: dict[str, Any]) -> ExecutionResult:
        """Execute a task using QueryEngine with tool access.

        Updates project_memory with discovered files, conventions, and failures.
        """
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

        # Exclude interactive/blocking tools from autonomous workers
        excluded_tools = {"AskUser", "ask", "question"}
        autonomous_tools = [t for t in get_all_tools() if t.name not in excluded_tools]

        # Select model client based on task complexity / worker type
        model_client = self._select_model_client(task)

        config = QueryEngineConfig(
            cwd=app_state.cwd,
            tools=autonomous_tools,
            get_app_state=store.get_state,
            set_app_state=store.set_state,
            max_turns=max(5, max_turns // 2),  # QueryEngine internal budget
            model_client=model_client,
        )
        engine = QueryEngine(config)
        executor = get_tool_executor()

        final_content = ""
        artifacts: dict[str, Any] = {}
        total_turns = 0
        file_reads_this_task: list[tuple[str, str]] = []  # (path, summary_hint)
        # Progressive disclosure: collect thinking + tool timeline
        task_details: list[dict[str, Any]] = []

        try:
            async with SessionCleanup() as cleanup:
                # Register cleanup: mark any unfinished tool calls as aborted
                async def _abort_pending_tools():
                    for msg in engine.messages:
                        if isinstance(msg, ToolUseMessage) and msg.name != "AskUser":
                            engine.add_tool_result(
                                msg.tool_use_id,
                                "[ABORTED] Session ended before tool completed.",
                                is_error=True,
                            )

                cleanup.on_cleanup(_abort_pending_tools)

                while total_turns < max_turns:
                    if self._cancel_event.is_set():
                        return ExecutionResult(
                            task_id=task.id,
                            success=False,
                            error="Cancelled by user",
                        )

                    # Build continue prompt with progress summary if not first turn
                    if total_turns == 0:
                        user_prompt = prompt
                    else:
                        user_prompt = await self._build_continue_prompt(engine, task)

                    pending_tools: list[ToolUseMessage] = []
                    turn_buffer = ""
                    async for result in engine.submit_message(user_prompt):
                        if self._cancel_event.is_set():
                            return ExecutionResult(
                                task_id=task.id,
                                success=False,
                                error="Cancelled by user",
                            )
                        msg = result.message
                        # Real-time streaming: emit assistant text chunks as they arrive
                        if isinstance(msg, AssistantMessage) and msg.content:
                            chunk = str(msg.content)
                            turn_buffer += chunk
                            if not result.is_complete:
                                self._emit_progress(
                                    "worker:text_delta",
                                    {"task_id": task.id, "content": chunk},
                                )
                            else:
                                from pilotcode.tools.bash_tool import strip_ansi

                                final_content = strip_ansi(turn_buffer)
                                self._emit_progress(
                                    "worker:turn_complete",
                                    {
                                        "task_id": task.id,
                                        "content": final_content,
                                    },
                                )
                        if isinstance(msg, ToolUseMessage):
                            pending_tools.append(msg)
                            self._emit_progress(
                                "worker:tool_start",
                                {
                                    "task_id": task.id,
                                    "tool_name": msg.name,
                                    "params": msg.input,
                                },
                            )

                    if not pending_tools:
                        break

                    # Execute tools and feed results back
                    tool_ctx = ToolUseContext(
                        get_app_state=store.get_state,
                        set_app_state=lambda f: store.set_state(f),
                        cwd=getattr(store.get_state(), "cwd", ""),
                    )

                    if self._cancel_event.is_set():
                        return ExecutionResult(
                            task_id=task.id,
                            success=False,
                            error="Cancelled by user",
                        )

                    # Limit concurrent tool execution to avoid overwhelming local
                    # models (Ollama/vLLM typically handle 1-2 concurrent reqs)
                    # or external APIs. Value is configurable via settings.json.
                    _tool_semaphore = asyncio.Semaphore(self._tool_concurrency_limit)

                    async def _exec_one(tu: ToolUseMessage) -> tuple[str, bool]:
                        """Execute a single tool and return (result_text, success)."""
                        async with _tool_semaphore:
                            er = await executor.execute_tool_by_name(tu.name, tu.input, tool_ctx)
                        if er.success and er.result is not None:
                            text = str(er.result.data) if er.result.data else "Success"
                        else:
                            text = er.message or "Tool execution failed"
                        return text, er.success

                    # Run independent tool calls in parallel (e.g., reading 3 files)
                    tool_results = await asyncio.gather(*[_exec_one(tu) for tu in pending_tools])

                    # Feed results back in original order to keep message history consistent
                    for tu, (result_text, success) in zip(pending_tools, tool_results):
                        engine.add_tool_result(
                            tu.tool_use_id,
                            result_text,
                            is_error=not success,
                        )
                        self._update_memory_from_tool(
                            tu, result_text, success, file_reads_this_task
                        )
                        # Real-time: emit tool result
                        summary = result_text[:500] + "..." if len(result_text) > 500 else result_text
                        self._emit_progress(
                            "worker:tool_result",
                            {
                                "task_id": task.id,
                                "tool_name": tu.name,
                                "success": success,
                                "summary": summary,
                            },
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
                    self.project_memory.record_changes(artifacts["changed_files"])

                artifacts["conversation_length"] = len(engine.messages)
                artifacts["final_response"] = final_content

                # Record success conventions from worker output
                if final_content:
                    self._extract_conventions_from_output(final_content)

                return ExecutionResult(
                    task_id=task.id,
                    success=True,
                    output=final_content,
                    artifacts=artifacts,
                    token_usage=engine.count_tokens(),
                    details=task_details,
                )

        except Exception as exc:
            # Record failure in project memory
            self.project_memory.record_failure(
                task_id=task.id,
                attempt=1,
                approach=f"worker execution ({task.worker_type})",
                error=str(exc),
                root_cause="worker_exception",
            )
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error=f"Worker execution failed: {exc}",
            )

    # ------------------------------------------------------------------
    # Model selection
    # ------------------------------------------------------------------

    def _select_model_client(self, task: TaskSpec) -> ModelClient:
        """Select an appropriate ModelClient based on task characteristics.

        Maps task complexity / worker_type to ModelTier and returns the
        corresponding client from the multi-model router.
        """
        # Map complexity to tier
        complexity = task.estimated_complexity
        worker_type = task.worker_type.lower()

        if worker_type == "simple" or complexity.value <= 2:
            tier = ModelTier.FAST
        elif worker_type == "complex" or complexity.value >= 4:
            tier = ModelTier.POWERFUL
        else:
            tier = ModelTier.BALANCED

        model_config = self.router.get_model_for_tier(tier)
        return self.router._get_client(model_config.name)

    # ------------------------------------------------------------------
    # Continue prompt with context
    # ------------------------------------------------------------------

    async def _build_continue_prompt(self, engine: QueryEngine, task: TaskSpec) -> str:
        """Build a contextual continue prompt instead of bare 'Please continue.'."""
        # Summarize what has happened so far
        actions: list[str] = []
        changed: list[str] = []
        errors: list[str] = []
        recent_edits: list[tuple[str, str]] = []  # (file_path, old_string)

        for msg in engine.messages:
            if isinstance(msg, ToolUseMessage):
                name = msg.name
                if name in ("FileRead", "read"):
                    path = msg.input.get("file_path") or msg.input.get("path", "?")
                    actions.append(f"read {path}")
                elif name in ("FileWrite", "write"):
                    path = msg.input.get("file_path") or msg.input.get("path", "?")
                    actions.append(f"wrote {path}")
                    changed.append(path)
                elif name in ("FileEdit", "edit"):
                    path = msg.input.get("file_path") or msg.input.get("path", "?")
                    old_str = msg.input.get("old_string", "")
                    actions.append(f"edited {path}")
                    changed.append(path)
                    recent_edits.append((path, old_str))
                elif name in ("BashTool", "Bash", "bash"):
                    cmd = msg.input.get("command", "?")[:60]
                    actions.append(f"ran bash: {cmd}")
                elif name in ("Grep", "grep", "Glob", "glob"):
                    actions.append(f"searched with {name}")
                else:
                    actions.append(f"used {name}")

        # Check last tool results for errors
        for msg in engine.messages:
            if hasattr(msg, "is_error") and msg.is_error:
                content = getattr(msg, "content", "") or ""
                errors.append(content[:200])

        parts = ["Continue working on the task. Progress so far:"]
        if actions:
            parts.append("Actions taken:\n" + "\n".join(f"  - {a}" for a in actions[-8:]))
        if changed:
            parts.append(f"Files modified: {', '.join(changed)}")
        if errors:
            parts.append("Errors encountered:\n" + "\n".join(f"  - {e}" for e in errors[-3:]))

        # --- Detect repeated FileEdit failures and suggest alternatives ---
        fileedit_errors = [e for e in errors if "FileEdit" in e or "String not found" in e]
        if len(fileedit_errors) >= 2 and self.compensation.config.enable_smart_edit_planner:
            parts.append(
                "\n[FRAMEWORK HINT] You have had multiple FileEdit failures in a row.\n"
                "1. Use SmartEditPlanner to get the exact checklist of all locations.\n"
                "2. Re-read the target file before editing to get the exact text.\n"
                "3. Pay attention to indentation (spaces vs tabs) — copy the exact whitespace.\n"
                "4. If FileEdit keeps failing, consider using FileWrite for small files ONLY."
            )

        # --- Auto-verification for weak execution models ---
        if recent_edits and self.compensation.config.enable_auto_verify:
            from .adaptive_edit import EditValidator

            # Verify scope depends on config
            edits_to_verify = (
                recent_edits[-1:]
                if not self.compensation.config.verify_after_each_edit
                else recent_edits
            )

            for edit_path, edit_old in edits_to_verify:
                if not edit_old:
                    continue
                validator = EditValidator()
                val_result = validator.validate(
                    changed_files=[edit_path],
                    expected_pattern=edit_old,
                    cwd=getattr(engine.config, "cwd", "."),
                    model_name=self.capability.model_name,
                )
                if not val_result.passed:
                    parts.append(f"\n[FRAMEWORK VERIFICATION]\n{val_result.nudge_message}")
                else:
                    parts.append(
                        f"\n[FRAMEWORK VERIFICATION] Edit in {edit_path} passed all checks."
                    )

        parts.append(f"\nTask objective: {task.objective}")
        parts.append("Continue where you left off. Do not repeat completed actions.")

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Project memory helpers
    # ------------------------------------------------------------------

    def _update_memory_from_tool(
        self,
        tu: ToolUseMessage,
        result_text: str,
        success: bool,
        file_reads: list[tuple[str, str]],
    ) -> None:
        """Update project memory based on tool usage."""
        name = tu.name

        if name in ("FileRead", "read"):
            path = tu.input.get("file_path") or tu.input.get("path", "")
            if path and not self.project_memory.has_read_file(path):
                # Store a truncated summary
                summary = result_text[:300].replace("\n", " ") if success else ""
                self.project_memory.record_file_read(path, result_text, summary=summary)
                file_reads.append((path, summary))

        elif name in ("FileWrite", "write", "FileEdit", "edit", "ApplyPatch", "apply_patch"):
            path = (
                tu.input.get("file_path") or tu.input.get("path") or tu.input.get("base_path", "")
            )
            if path:
                self.project_memory.record_changes([path])

        elif name in ("BashTool", "Bash", "bash"):
            cmd = tu.input.get("command", "")
            # Detect framework from commands
            if "pytest" in cmd or "unittest" in cmd:
                self.project_memory.record_convention("testing_framework", "pytest")
            if "pip install" in cmd:
                pkg = (
                    cmd.split("pip install")[-1].strip().split()[0] if "pip install" in cmd else ""
                )
                if pkg:
                    self.project_memory.record_convention("dependency_manager", "pip")

    def _extract_conventions_from_output(self, output: str) -> None:
        """Heuristically extract conventions from worker final output."""
        output_lower = output.lower()
        if "fastapi" in output_lower:
            self.project_memory.record_convention("framework", "FastAPI")
        elif "django" in output_lower:
            self.project_memory.record_convention("framework", "Django")
        elif "flask" in output_lower:
            self.project_memory.record_convention("framework", "Flask")

        if "pytest" in output_lower:
            self.project_memory.record_convention("testing_framework", "pytest")
        elif "unittest" in output_lower:
            self.project_memory.record_convention("testing_framework", "unittest")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _emit_progress(self, event: str, data: dict) -> None:
        """Emit a progress event to the registered callback (if any)."""
        cb = self._progress_callback
        if cb is not None:
            try:
                result = cb(event, data)
                if result is not None and asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception:
                pass

    async def run(
        self,
        user_request: str,
        progress_callback: Callable[[str, dict], None] | None = None,
        explore_first: bool = True,
    ) -> dict[str, Any]:
        """Plan and execute a mission from a natural language request.

        Args:
            user_request: The user's natural language request.
            progress_callback: Optional callback(event_type, data) for progress updates.
            explore_first: Whether to explore codebase before planning (default True).

        Returns:
            Execution summary dict with keys: mission_id, snapshot, success, error, mission, metrics.
        """
        # Wire the progress callback so _llm_worker can emit real-time events
        self._progress_callback = progress_callback

        try:
            # Phase 0: Explore codebase (if enabled)
            exploration: dict[str, Any] | None = None

            def _invoke_progress(event: str, data: dict) -> None:
                if progress_callback:
                    result = progress_callback(event, data)
                    if result is not None and asyncio.iscoroutine(result):
                        asyncio.create_task(result)

            if explore_first:
                _invoke_progress(
                    "mission:exploring", {"message": "Exploring codebase structure..."}
                )
                exploration = await explore_codebase(user_request, self.project_memory)

            # Phase 1: Plan mission
            mission = await self._plan_mission(user_request, exploration)

            _invoke_progress(
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
            # Clear previous callbacks to prevent memory leak on repeated runs
            self._orchestrator.clear_progress_callbacks()

            def _wrapped_progress(event: str, data: dict) -> None:
                if self._cancel_event.is_set():
                    mid = data.get("mission_id")
                    if mid:
                        self._orchestrator.cancel_mission(mid)
                _invoke_progress(event, data)

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

            # Runtime calibration: analyze each task outcome
            self._calibrate_from_mission_result(mission.mission_id)

            return result

        except asyncio.CancelledError:
            # Return a clean cancellation result instead of raising,
            # so callers (e.g. WebSocket handlers) don't need extra try/except.
            return {
                "success": False,
                "error": "Cancelled by user",
                "mission_id": getattr(locals().get("mission"), "mission_id", ""),
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "mission_id": "",
            }

    def _calibrate_from_mission_result(self, mission_id: str) -> None:
        """Analyze mission execution results and update capability scores."""
        from .results import ExecutionResult
        from ..model_capability.runtime_calibrator import TaskOutcome

        dag = self._orchestrator.tracker.get_dag(mission_id)
        if not dag:
            return

        for task_id, node in dag.nodes.items():
            exec_res = node.artifacts.get("_exec_result")
            if not isinstance(exec_res, ExecutionResult):
                continue

            # Determine completion percentage and correctness
            success = exec_res.success
            error_text = exec_res.error or ""
            output_text = exec_res.output or ""

            # Check verification results if available
            verification_passed = True
            for level in (1, 2, 3):
                vkey = f"_verification_{level}"
                vresult = node.artifacts.get(vkey)
                if vresult is not None and hasattr(vresult, "passed"):
                    if not vresult.passed:
                        verification_passed = False
                        break

            correctness = 1.0 if success and verification_passed else 0.5 if success else 0.0
            completion_pct = 1.0 if success else 0.0

            outcome = TaskOutcome(
                task_id=task_id,
                success=success and verification_passed,
                completion_percentage=completion_pct,
                correctness_score=correctness,
                error_text=error_text,
                output_text=output_text,
            )
            self.calibrator.record_task_outcome(outcome)

        # Log calibration summary
        import logging

        logger = logging.getLogger(__name__)
        cap = self.calibrator.get_calibrated_capability()
        logger.info(
            "Runtime calibration updated: overall=%.2f -> %.2f (success_rate=%.1f%%)",
            self.capability.overall_score,
            cap.overall_score,
            self.calibrator.get_success_rate() * 100,
        )
