"""UI adapter for P-EVR orchestration.

Bridges natural language requests to structured Mission execution via LLM.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import py_compile
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pilotcode.utils.model_client import get_model_client, Message, ModelClient
from pilotcode.utils.model_router import ModelRouter, ModelTier
from pilotcode.query_engine import QueryEngine, QueryEngineConfig
from pilotcode.tools.registry import get_core_tools
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
from pilotcode.services import prompts as prompt_service

from .task_spec import Mission, TaskSpec, ComplexityLevel, Constraints, AcceptanceCriterion
from .shared import CODE_FILE_EXTENSIONS
from .orchestrator import Orchestrator, OrchestratorConfig
from .results import ExecutionResult
from .verifier.base import VerificationResult
from .verifier.adapter_verifiers import (
    l1_simple_verifier,
    l3_code_review_verifier,
)
from .verifier.level2_tests import TestRunnerVerifier
from .explorers.code_explorer import explore_codebase
from .context_strategy import (
    ContextStrategySelector,
    MissionPlanAdjuster,
    StrategyMetrics,
)
from .project_memory import ProjectMemory
from ..model_capability import (
    load_capability_or_default,
    AdaptiveConfigMapper,
    RuntimeTracker,
    VerifierStrategy,
)
from .plan_mode import should_plan
from .plan_files import write_plan

logger = logging.getLogger(__name__)


class MissionAdapter:
    """Adapter that converts user requests into executed missions.

    Usage:
        adapter = MissionAdapter()
        result = await adapter.run("Implement OAuth2 login")
    """

    # Complexity-to-turns mapping for the LLM worker loop
    DEFAULT_TURN_LIMITS: dict[ComplexityLevel, int] = {
        ComplexityLevel.VERY_SIMPLE: 3,
        ComplexityLevel.SIMPLE: 6,
        ComplexityLevel.MODERATE: 10,
        ComplexityLevel.COMPLEX: 15,
        ComplexityLevel.VERY_COMPLEX: 25,
    }

    # Tiered JSON schema prompts: strong models don't need inline schemas
    _PLAN_SCHEMA_STRONG = (
        "Output valid JSON: {title, phases[{phase_id, title, description, "
        "tasks[{id, title, objective, inputs, outputs, dependencies, "
        "estimated_complexity, acceptance_criteria[{description, verification_method}], "
        "constraints{max_lines, must_use, must_not_use, patterns}, worker_type}]}]}"
    )

    _PLAN_SCHEMA_MEDIUM = (
        "Output ONLY a JSON object. Schema: {\n"
        '  "title": str, "phases": [{\n'
        '    "phase_id": str, "title": str, "description": str,\n'
        '    "tasks": [{\n'
        '      "id": str, "title": str, "objective": str,\n'
        '      "inputs": [str], "outputs": [str], "dependencies": [str],\n'
        '      "estimated_complexity": int (1-5),\n'
        '      "acceptance_criteria": [{"description": str, "verification_method": str}],\n'
        '      "constraints": {"max_lines": int|null, "must_use": [str], "must_not_use": [str], "patterns": [str]},\n'
        '      "worker_type": "auto"|"simple"|"standard"|"complex"\n'
        "    }]\n"
        "  }]\n"
        "}"
    )

    _PLAN_SCHEMA_WEAK = (
        "Output ONLY a JSON object with no markdown formatting. "
        "The JSON must match this schema:\n\n"
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
        "}"
    )

    def __init__(
        self,
        cancel_event: asyncio.Event | None = None,
        max_worker_turns: int | None = None,
        context_budget: int = 16000,
        project_memory: ProjectMemory | None = None,
        capability_path: str | None = None,
        cwd: str | None = None,
    ):
        self._cancel_event = cancel_event or asyncio.Event()
        self._max_worker_turns = max_worker_turns
        self.context_budget = context_budget
        self.project_memory = project_memory or ProjectMemory()
        self._cwd = cwd or str(Path.cwd())

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
        self.calibrator = RuntimeTracker()

        # Compensation engine for dimension-specific weak-model compensation
        from .adaptive_edit import CompensationEngine

        self.compensation = CompensationEngine(self.adaptive_config, self.capability)

        # P0: FileEdit failure streak counter for real-time compensation escalation
        self._fileedit_failure_streak = 0

        # Per-task compiler check cache: avoid re-verifying unchanged files
        self._verified_files_this_task: set[str] = set()

        # Multi-model router for tiered task routing
        self.router = ModelRouter()

        # Tool concurrency limit from user config (local models default 2, remote 5)
        self._tool_concurrency_limit = get_global_config().tool_concurrency_limit
        # Instance-level semaphore (NOT recreated per loop iteration)
        self._tool_semaphore = asyncio.Semaphore(self._tool_concurrency_limit)

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
        orch_config.cancel_event = self._cancel_event
        self.plan_adjuster.apply_to_orchestrator_config(orch_config)
        orch_config.default_task_timeout = self.adaptive_config.stagnation_threshold_seconds
        self._orchestrator = Orchestrator(config=orch_config)

        self._register_workers()
        self._register_verifiers()
        self._setup_permission_callback()

        # Progressive disclosure: allow _llm_worker to emit real-time progress
        self._progress_callback: Callable[[str, dict], None] | None = None

        # Track user's preferred language so workers respond consistently
        self._user_language: str = "en"

    # ------------------------------------------------------------------
    # Internal setup
    # ------------------------------------------------------------------

    def _register_workers(self) -> None:
        """Register the LLM-based worker for all task types."""
        for worker_type in ("simple", "standard", "complex", "auto", "explorer", "verifier"):
            self._orchestrator.register_worker(worker_type, self._llm_worker)

    def _register_verifiers(self) -> None:
        """Register L1/L2/L3 verifiers based on adaptive configuration."""
        self._orchestrator.register_verifier(1, l1_simple_verifier)

        # L2: language-aware verifier (pytest + compiler checks)
        l2_handler = self._make_l2_verifier()
        self._orchestrator.register_verifier(2, l2_handler)

        if self.adaptive_config.verifier_strategy == VerifierStrategy.FULL_L3:
            self._orchestrator.register_verifier(3, l3_code_review_verifier)
        elif self.adaptive_config.verifier_strategy == VerifierStrategy.SIMPLIFIED_L3:
            from .verifier.adaptive_verifiers import simplified_l3_verifier

            self._orchestrator.register_verifier(3, simplified_l3_verifier)
        elif self.adaptive_config.verifier_strategy == VerifierStrategy.STATIC_ONLY:
            from .verifier.adaptive_verifiers import static_analysis_l3_verifier

            self._orchestrator.register_verifier(3, static_analysis_l3_verifier)

    def _make_l2_verifier(self) -> Callable:
        """Build the L2 verifier: TestRunnerVerifier with optional enforcement."""
        verifier = TestRunnerVerifier()

        async def handler(task: TaskSpec, exec_result: ExecutionResult) -> VerificationResult:
            # Optionally inject test criterion for weak models (only if code was produced)
            if self.adaptive_config.enforce_test_before_mark_complete:
                changed_files = exec_result.artifacts.get("changed_files", []) or []
                code_files = [f for f in changed_files if f.endswith(CODE_FILE_EXTENSIONS)]
                if code_files and not any(
                    ac.verification_method in ("test", "pytest") for ac in task.acceptance_criteria
                ):
                    task.acceptance_criteria.append(
                        AcceptanceCriterion(
                            description="Run project tests to verify no regressions",
                            verification_method="test",
                        )
                    )
            return await verifier.verify(task, exec_result)

        return handler

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

    def _get_plan_schema(self) -> str:
        """Return JSON schema prompt appropriate for model capability."""
        p = self.capability.planning.score
        j = self.capability.json_formatting.score
        if p >= 0.70 and j >= 0.70:
            return self._PLAN_SCHEMA_STRONG
        elif p >= 0.40:
            return self._PLAN_SCHEMA_MEDIUM
        return self._PLAN_SCHEMA_WEAK

    async def _plan_mission(
        self, user_request: str, exploration: dict[str, Any] | None = None
    ) -> Mission:
        """Use an LLM to decompose a user request into a Mission.

        If exploration data is provided, the plan is grounded in actual codebase structure.
        """
        if self._cancel_event.is_set():
            raise asyncio.CancelledError("Cancelled by user")

        client = get_model_client()

        # Use unified prompts module for planner
        planning_capability = self.capability.planning.score
        json_capability = self.capability.json_formatting.score >= 0.5
        base_prompt = prompt_service.get_planner_prompt(
            complexity=planning_capability,
            json_capable=json_capability,
        )

        # Add task-type guidance
        base_prompt += (
            "\n\n"
            "## Task Type Guidance\n"
            "- ONLY generate implementation/coding tasks when the user explicitly asks to\n"
            "  CREATE, IMPLEMENT, BUILD, or ADD something.\n"
            "- Match the user's intent: analysis → analysis tasks, implementation → coding tasks.\n"
            "- ALL task titles, descriptions, and objectives MUST be in the SAME LANGUAGE as the\n"
            "  user's request. If the user wrote in Chinese, every task must be in Chinese.\n"
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

        # Some models wrap the mission in a {"mission": {...}} envelope.
        # Unwrap it if present.
        if "mission" in plan_data and isinstance(plan_data["mission"], dict):
            plan_data = plan_data["mission"]

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

        # Write plan to disk for persistence (Phase 2: plan file)
        try:
            write_plan(plan_data)
        except Exception as exc:
            logger.warning("Failed to write plan file: %s", exc, exc_info=True)

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
                                    fixed = MissionAdapter._fix_common_json_errors(candidate)
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
        """Build execution prompt for a single task.

        Injects project memory, agent memory, and plan context.
        """
        from ..agent.agent_memory import load_agent_memory_prompt

        parts = []

        # Inject project root so the worker knows where it is operating
        parts.append(f"[Project Root] {self._cwd}")
        parts.append("")

        # Inject project memory so worker knows what has been discovered
        if self.project_memory:
            mem_section = self.project_memory.to_prompt_section()
            if mem_section:
                parts.append(mem_section)
                parts.append("")

        # Inject agent memory if available (Phase 3: agent memory integration)
        worker_type = context.get("worker_type", task.worker_type or "auto")
        if worker_type and worker_type != "auto":
            agent_memory = load_agent_memory_prompt(worker_type, scope="project")
            if agent_memory:
                parts.append(agent_memory)
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

        # Extract explicit file references from objective and inputs to tighten scope
        allowed_files = self._extract_allowed_files(task)
        if allowed_files:
            parts.extend(["", "[Allowed Files]"])
            for f in allowed_files:
                parts.append(f"  - {f}")
            parts.append(
                "CRITICAL: Only read files listed above for project-internal code. "
                "You MAY also read any external reference files the user explicitly mentioned (e.g. templates, examples, file lists). "
                "Do NOT browse, search, or glob for unrelated files unless the task explicitly asks you to."
            )

        # Language directive
        lang_instruction = (
            "Respond in Chinese." if self._user_language == "cn" else "Respond in English."
        )

        parts.extend(
            [
                "",
                "[Instructions]",
                f"1. {lang_instruction}",
                "2. Focus on the task objective. Do not modify unrelated code.",
                "3. Use the available tools to read, write, and edit files as needed.",
                "4. Check PROJECT MEMORY before reading files — avoid re-reading known files.",
                "5. After making changes, verify they meet the acceptance criteria.",
                "6. Run compiler checks and tests using Bash, NOT TaskCreate. "
                "TaskCreate is for tracking progress of independent work, not for compilation.",
                "7. Return a concise summary of what you did and any new files discovered.",
            ]
        )

        # Worker-type specific instructions
        worker_type = context.get("worker_type", task.worker_type or "auto")
        if worker_type == "simple":
            parts.extend(
                [
                    "",
                    "[Worker Mode: SIMPLE]",
                    "You are a focused, single-file editor. Rules:",
                    "- ONLY modify the target file(s) explicitly mentioned in the task.",
                    "- Do NOT use search, grep, or glob to browse unrelated files.",
                    "- Read the target file first, then make minimal, precise changes.",
                    "- Return immediately after completing the edit.",
                ]
            )
        elif worker_type == "complex":
            parts.extend(
                [
                    "",
                    "[Worker Mode: COMPLEX]",
                    "You are an architect-level engineer handling cross-module changes. Rules:",
                    "- First, understand the project structure and dependencies.",
                    "- Design the interface/contracts BEFORE implementing.",
                    "- Ensure consistency across all affected modules.",
                    "- Run tests for all modified components.",
                ]
            )
        elif worker_type == "debug":
            parts.extend(
                [
                    "",
                    "[Worker Mode: DEBUG]",
                    "You are a surgical debugger. Rules:",
                    "- Make the MINIMUM possible change to fix the issue.",
                    "- Do NOT refactor, rename, or reformat unrelated code.",
                    "- Prefer ApplyPatch or precise FileEdit over FileWrite.",
                    "- Verify the fix with the provided test or reproduction steps.",
                ]
            )

        # Inject compensation guidance based on dimension-specific weaknesses
        compensation_guidance = self.compensation.get_worker_prompt_suffix()
        if compensation_guidance:
            parts.append(compensation_guidance)

        return "\n".join(parts)

    @staticmethod
    def _extract_allowed_files(task: TaskSpec) -> list[str]:
        """Extract explicit file paths mentioned in task objective or inputs."""
        import re

        candidates: list[str] = []
        text = " ".join([task.objective or "", *(task.inputs or [])])
        # Match Unix/Windows absolute or relative paths with common source extensions
        pattern = re.compile(r"(?:[\w\-]+/)*[\w\-]+(?:\.[a-zA-Z0-9]+)+")
        for m in pattern.finditer(text):
            val = m.group(0)
            # Keep only values that look like file paths (contain a dot and a slash)
            if "/" in val and "." in val and val not in candidates:
                candidates.append(val)
        return candidates

    async def _run_agent_for_task(
        self,
        task: TaskSpec,
        context: dict[str, Any],
        agent_type: str = "explorer",
        max_turns: int = 8,
    ) -> ExecutionResult:
        """Execute a task by spawning a specialized Agent.

        Phase 3: Uses agent_manager.create_agent() + orchestrator to run
        dedicated agents (explorer, verifier) for appropriate task types.
        """
        from ..agent import get_agent_manager, save_agent_memory

        manager = get_agent_manager()
        agent = manager.create_agent(
            agent_type=agent_type,
            name=f"{agent_type}-{task.id}",
            is_background=False,
            is_ephemeral=True,
        )

        prompt = self._build_worker_prompt(task, context)
        agent.max_turns = max_turns

        try:
            from ..agent.agent_orchestrator import get_orchestrator as get_agent_orch

            orch = get_agent_orch()

            # Forward real-time tool-use events so the TUI can show agent activity
            def _agent_progress(msg: str) -> None:
                if self._progress_callback:
                    self._progress_callback("worker:tool_start", {"tool_name": msg, "params": {}})

            result = await orch._run_agent_task(agent, prompt, progress_callback=_agent_progress)

            # Detect agent internal failure (agent_orchestrator returns error string
            # instead of raising when it catches an exception).
            agent_failed = (
                isinstance(result, str) and result.startswith("[Agent") and "failed:" in result
            )

            # Save execution knowledge to agent memory
            if not agent_failed:
                try:
                    result_snippet = str(result)[:500] if result is not None else ""
                    knowledge = f"## Task: {task.title}\n- Objective: {task.objective}\n- Result: {result_snippet}\n"
                    save_agent_memory(agent_type, knowledge, scope="project", append=True)
                except Exception as exc:
                    logger.warning("Failed to save agent memory: %s", exc, exc_info=True)

            if agent_failed:
                return ExecutionResult(
                    task_id=task.id,
                    success=False,
                    error=result,
                    artifacts={
                        "changed_files": [],
                        "agent_id": agent.agent_id,
                        "agent_type": agent_type,
                        "conversation_length": agent.turns,
                    },
                )

            return ExecutionResult(
                task_id=task.id,
                success=True,
                output=result,
                artifacts={
                    "changed_files": [],
                    "agent_id": agent.agent_id,
                    "agent_type": agent_type,
                    "conversation_length": agent.turns,
                    "final_response": result,
                },
            )
        except Exception as e:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error=f"Agent {agent_type} failed: {e}",
            )
        finally:
            # Clean up the temporary agent so it doesn't accumulate in memory
            # and on disk across repeated PLAN mode runs.
            try:
                manager.delete_agent(agent.agent_id)
            except Exception:
                pass

    async def _llm_worker(self, task: TaskSpec, context: dict[str, Any]) -> ExecutionResult:
        """Execute a task using QueryEngine with tool access.

        Updates project_memory with discovered files, conventions, and failures.

        Phase 3 integration:
        - Routes analysis tasks to explorer Agent
        - Routes verification tasks to verifier Agent
        - Supports worktree isolation for implementation tasks
        - Saves execution knowledge to agent memory on completion
        """
        if self._cancel_event.is_set():
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error="Cancelled by user",
            )

        # Phase 3: Route analysis-only tasks to explorer agent
        worker_type = context.get("worker_type", task.worker_type or "auto")
        # A task is read-only if it has no output files declared.
        is_read_only = not task.outputs
        use_explorer = worker_type in ("explorer", "simple") or is_read_only
        has_test_criterion = any(
            ac.verification_method in ("test", "pytest") for ac in task.acceptance_criteria
        )
        use_verifier = worker_type == "verifier" or has_test_criterion

        if use_explorer:
            return await self._run_agent_for_task(task, context, agent_type="explorer", max_turns=8)
        if use_verifier:
            return await self._run_agent_for_task(
                task, context, agent_type="verifier", max_turns=15
            )

        prompt = self._build_worker_prompt(task, context)

        app_state = get_default_app_state()
        store = Store(app_state)
        from dataclasses import replace

        store.set_state(lambda s: replace(s, cwd=self._cwd))

        # Determine turn limit based on task complexity
        complexity = task.estimated_complexity
        max_turns = (
            self._max_worker_turns
            if self._max_worker_turns is not None
            else self.DEFAULT_TURN_LIMITS.get(complexity, 20)
        )

        # Exclude interactive/blocking tools and plan-mode tools from autonomous workers.
        # Plan-mode tools (EnterPlanMode/ExitPlanMode) are meant for conversational
        # chat only; inside a P-EVR mission the orchestrator already manages phases
        # and tasks, so the worker must not create nested sub-plans.
        excluded_tools = {
            "AskUser",
            "ask",
            "question",
            "PlanMode",
            "Sleep",
            "sleep",
            "TaskCreate",
            "TaskGet",
            "TaskList",
            "TaskUpdate",
            "TaskStop",
            "Cron",
        }
        # Worker-type specific tool exclusions
        worker_type = context.get("worker_type", task.worker_type or "auto")
        if worker_type == "simple":
            # Simple worker should not browse or search; only edit target files
            excluded_tools.update(
                {
                    "Glob",
                    "glob",
                    "Grep",
                    "grep",
                    "Search",
                    "search",
                }
            )
        elif worker_type == "debug":
            # Debug worker should not create new files or do large rewrites
            excluded_tools.update(
                {
                    "FileWrite",
                    "file_write",
                    "Sleep",
                }
            )
        autonomous_tools = [t for t in get_core_tools(self._cwd) if t.name not in excluded_tools]

        # Select model client based on task complexity / worker type
        model_client = self._select_model_client(task)

        config = QueryEngineConfig(
            cwd=self._cwd,
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

        # Reset per-task compiler check cache
        self._verified_files_this_task = set()

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

                # --- Multi-Agent: Architect phase for complex tasks ---
                complexity = task.estimated_complexity
                if complexity.value >= ComplexityLevel.COMPLEX.value:
                    self._emit_progress(
                        "worker:tool_start",
                        {"task_id": task.id, "tool_name": "ArchitectAgent", "params": {}},
                    )
                    arch_prompt = (
                        f"[Architect Agent] Task: {task.title}\n"
                        f"Objective: {task.objective}\n\n"
                        "Analyze and produce a concise implementation plan:\n"
                        "1. Which files need modification/creation\n"
                        "2. Key interfaces/functions to define\n"
                        "3. Dependencies between changes\n"
                        "Do NOT write code yet. Only the plan."
                    )
                    arch_buffer = ""
                    async for aresult in engine.submit_message(arch_prompt):
                        msg = aresult.message
                        if isinstance(msg, AssistantMessage) and msg.content:
                            arch_buffer += str(msg.content)
                    if arch_buffer:
                        engine.add_system_message(f"[Architect Plan] {arch_buffer[:2000]}")
                        task_details.append(
                            {"type": "architect_plan", "content": arch_buffer[:500]}
                        )
                    self._emit_progress(
                        "worker:tool_result",
                        {
                            "task_id": task.id,
                            "tool_name": "ArchitectAgent",
                            "success": True,
                            "summary": arch_buffer[:200],
                        },
                    )

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
                        cwd=self._cwd,
                    )

                    if self._cancel_event.is_set():
                        return ExecutionResult(
                            task_id=task.id,
                            success=False,
                            error="Cancelled by user",
                        )

                    # Limit concurrent tool execution using instance semaphore
                    # (created in __init__, NOT recreated per loop iteration).
                    async def _exec_one(tu: ToolUseMessage) -> tuple[str, bool]:
                        """Execute a single tool and return (result_text, success)."""
                        async with self._tool_semaphore:
                            er = await executor.execute_tool_by_name(tu.name, tu.input, tool_ctx)
                        if er.success and er.result is not None:
                            text = (
                                er.result.get_text_for_assistant() if er.result.data else "Success"
                            )
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

                        # --- P0: Real-time FileEdit failure detection ---
                        if tu.name in ("FileEdit", "edit"):
                            if not success or "String not found" in result_text:
                                self._fileedit_failure_streak += 1
                                if self._fileedit_failure_streak >= 2:
                                    self._escalate_compensation()
                            else:
                                self._fileedit_failure_streak = 0

                        # Real-time: emit tool result
                        summary = (
                            result_text[:500] + "..." if len(result_text) > 500 else result_text
                        )
                        self._emit_progress(
                            "worker:tool_result",
                            {
                                "task_id": task.id,
                                "tool_name": tu.name,
                                "success": success,
                                "summary": summary,
                            },
                        )

                    # --- Inline verification after file modifications ---
                    changed_paths = []
                    for tu, (result_text, success) in zip(pending_tools, tool_results):
                        if not success:
                            continue
                        if tu.name in (
                            "FileWrite",
                            "write",
                            "FileEdit",
                            "edit",
                            "ApplyPatch",
                            "apply_patch",
                        ):
                            for key in ("path", "file_path", "filepath"):
                                val = tu.input.get(key)
                                if val and isinstance(val, str):
                                    changed_paths.append(val)
                                    break

                    if changed_paths:
                        inline_issues = await self._run_inline_verification(task, changed_paths)
                        if inline_issues:
                            engine.add_system_message(
                                f"[INLINE VERIFICATION] Issues found in recent changes:\n{inline_issues}\n"
                                "Please address these issues in your next turn."
                            )
                            self._emit_progress(
                                "worker:inline_verification",
                                {
                                    "task_id": task.id,
                                    "issues": inline_issues,
                                },
                            )

                    total_turns += 1

                # --- Multi-Agent: Reviewer phase for complex tasks ---
                if complexity.value >= ComplexityLevel.COMPLEX.value and total_turns < max_turns:
                    self._emit_progress(
                        "worker:tool_start",
                        {"task_id": task.id, "tool_name": "ReviewerAgent", "params": {}},
                    )
                    review_prompt = (
                        "[Reviewer Agent] Review the changes you just made against the objective.\n"
                        "Check: logic correctness, boundary cases, design consistency, missing tests.\n"
                        "If you find issues, list them concisely. If everything looks good, say 'APPROVED'."
                    )
                    review_buffer = ""
                    async for rresult in engine.submit_message(review_prompt):
                        msg = rresult.message
                        if isinstance(msg, AssistantMessage) and msg.content:
                            review_buffer += str(msg.content)
                    if review_buffer and "APPROVED" not in review_buffer.upper():
                        # Inject reviewer feedback as system message for potential fix turn
                        engine.add_system_message(f"[Reviewer Feedback] {review_buffer[:1500]}")
                        task_details.append(
                            {"type": "reviewer_feedback", "content": review_buffer[:500]}
                        )
                    self._emit_progress(
                        "worker:tool_result",
                        {
                            "task_id": task.id,
                            "tool_name": "ReviewerAgent",
                            "success": True,
                            "summary": review_buffer[:200],
                        },
                    )

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

                # Phase 3: Save execution knowledge to agent memory
                try:
                    from ..agent.agent_memory import save_agent_memory

                    memory_text = (
                        f"## Task: {task.title}\n"
                        f"- Objective: {task.objective}\n"
                        f"- Files: {artifacts.get('changed_files', [])}\n"
                        f"- Result: {final_content[:300]}\n"
                    )
                    save_agent_memory(
                        task.worker_type or "coder",
                        memory_text,
                        scope="project",
                        append=True,
                    )
                except Exception as exc:
                    logger.warning("Failed to save agent memory: %s", exc, exc_info=True)

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
        worker_type = str(task.worker_type or "auto").lower()

        if worker_type == "simple" or complexity.value <= 2:
            tier = ModelTier.FAST
        elif worker_type == "complex" or complexity.value >= 4:
            tier = ModelTier.POWERFUL
        else:
            tier = ModelTier.BALANCED

        model_config = self.router.get_model_for_tier(tier)
        return self.router._get_client(model_config.name)

    # ------------------------------------------------------------------
    # P0: Real-time compensation escalation on FileEdit failures
    # ------------------------------------------------------------------

    def _escalate_compensation(self) -> None:
        """Automatically increase compensation level when FileEdit keeps failing.

        This is triggered in real-time during tool execution (not after task
        completion), so the very next LLM turn receives stronger guidance.
        """
        config = self.compensation.config
        escalations: list[str] = []

        # Strategy 1: Force atomic edits (one change per FileEdit call)
        if config.max_edits_per_round > 1:
            config.max_edits_per_round = 1
            escalations.append("max_edits_per_round=1")

        # Strategy 2: Enable SmartEditPlanner if not already on
        if not config.enable_smart_edit_planner:
            config.enable_smart_edit_planner = True
            escalations.append("enable_smart_edit_planner")

        # Strategy 3: Force verify-after-each-edit
        if not config.verify_after_each_edit:
            config.verify_after_each_edit = True
            escalations.append("verify_after_each_edit")

        # Strategy 4: Reduce task granularity to fine
        if config.task_granularity.value != "fine":
            from pilotcode.model_capability.adaptive_config import TaskGranularity

            config.task_granularity = TaskGranularity.FINE
            escalations.append("task_granularity=fine")

        if escalations:
            import logging

            logger = logging.getLogger(__name__)
            logger.info(
                "Compensation escalated after %d FileEdit failures: %s",
                self._fileedit_failure_streak,
                ", ".join(escalations),
            )

    # ------------------------------------------------------------------
    # Continue prompt with context
    # ------------------------------------------------------------------

    async def _build_continue_prompt(self, engine: QueryEngine, task: TaskSpec) -> str:
        """Build a contextual continue prompt instead of bare 'Please continue.'."""
        # Strong models don't need detailed progress summaries — a short
        # continuation nudge is sufficient and saves ~700 tokens per turn.
        if self.capability.planning.score >= 0.70:
            return "Continue."
        logger = logging.getLogger(__name__)
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
                elif name in ("ApplyPatch", "apply_patch"):
                    path = msg.input.get("file_path") or msg.input.get("path", "?")
                    actions.append(f"patched {path}")
                    changed.append(path)
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
            # Check which files actually need re-reading (skip recently touched files)
            stale_paths = [f for f in changed if self.project_memory.needs_re_read(f)]
            hint_lines = [
                "\n[FRAMEWORK HINT] You have had multiple FileEdit failures in a row.\n"
                "1. Use SmartEditPlanner to get the exact checklist of all locations.\n"
            ]
            if stale_paths:
                hint_lines.append(
                    f"2. Re-read these files before editing (state unknown/stale): "
                    f"{', '.join(stale_paths[:3])}\n"
                )
                hint_lines.append(
                    "3. Pay attention to indentation (spaces vs tabs) — copy the exact whitespace.\n"
                )
                hint_lines.append(
                    "4. If FileEdit keeps failing, consider using FileWrite for small files ONLY."
                )
            else:
                hint_lines.append(
                    "2. You recently read or wrote these files — skip FileRead.\n"
                    "3. Pay attention to indentation — copy the exact whitespace from your last edit.\n"
                    "4. If FileEdit keeps failing, switch to FileWrite for small files ONLY."
                )
            parts.append("".join(hint_lines))

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

        # --- Compiler / syntax verification for changed code files ---
        # Detect whether LLM already ran a compile command this turn
        # Only check the most recent turn (after last AssistantMessage)
        recent_tool_msgs: list[ToolUseMessage] = []
        for msg in reversed(engine.messages):
            if isinstance(msg, AssistantMessage):
                break
            if isinstance(msg, ToolUseMessage):
                recent_tool_msgs.append(msg)

        has_compile_command = any(
            msg.name in ("Bash", "bash", "BashTool", "PowerShell", "powershell")
            and any(
                kw in (msg.input.get("command", "") + " " + msg.input.get("script", "")).lower()
                for kw in (
                    "gcc",
                    "g++",
                    "make",
                    "cmake",
                    "msbuild",
                    "rustc",
                    "cargo",
                    "go build",
                    "javac",
                    "npm run build",
                    "tsc",
                )
            )
            for msg in recent_tool_msgs
        )

        if changed and not has_compile_command:
            code_files = [
                f
                for f in changed
                if f.endswith(CODE_FILE_EXTENSIONS) and f not in self._verified_files_this_task
            ]
            if code_files:
                temp_exec = ExecutionResult(
                    task_id=task.id,
                    success=True,
                    artifacts={
                        "changed_files": code_files,
                        "cwd": getattr(engine.config, "cwd", ".") or ".",
                    },
                )
                verifier = TestRunnerVerifier()
                try:
                    # If the worker is still writing files this turn, skip project build
                    has_file_write = any(
                        msg.name
                        in ("FileWrite", "write", "FileEdit", "edit", "ApplyPatch", "apply_patch")
                        for msg in recent_tool_msgs
                    )
                    v_result = await verifier.verify(
                        task, temp_exec, skip_project_build=has_file_write
                    )
                    self._verified_files_this_task.update(code_files)
                    if not v_result.passed and v_result.feedback:
                        parts.append(
                            f"\n[FRAMEWORK VERIFICATION - COMPILE CHECK]\n"
                            f"{v_result.feedback}\n"
                            f"Fix these errors before proceeding."
                        )
                    elif v_result.passed:
                        parts.append(
                            "\n[FRAMEWORK VERIFICATION - COMPILE CHECK] All code changes passed syntax check."
                        )
                except Exception as exc:
                    logger.debug("Compiler check skipped due to internal error: %s", exc)

        # --- Detect repeated identical commands (hang prevention) ---
        recent_bash_cmds: list[str] = []
        for msg in reversed(engine.messages):
            if isinstance(msg, ToolUseMessage) and msg.name in ("Bash", "bash", "BashTool"):
                cmd = msg.input.get("command", "")[:100]
                if cmd:
                    recent_bash_cmds.append(cmd)
            if len(recent_bash_cmds) >= 3:
                break

        if len(recent_bash_cmds) >= 3 and len(set(recent_bash_cmds)) == 1:
            parts.append(
                "\n[FRAMEWORK HINT] You have run the same command 3+ times without progress. "
                "Stop repeating it. Read error output carefully and fix the underlying issue, "
                "or try a different approach. Do NOT sleep or wait."
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
                self.project_memory.record_file_written(path)

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

    @staticmethod
    def _detect_language(text: str) -> str:
        """Detect if text is primarily Chinese."""
        for ch in text:
            if "\u4e00" <= ch <= "\u9fff":
                return "cn"
        return "en"

    @staticmethod
    def _should_explore_and_plan(user_request: str) -> bool:
        """Heuristically decide if a request needs exploration + LLM planning.

        Delegates to the unified plan_mode module which provides
        Claude Code-style decision logic (plan vs analyze vs direct).

        Returns:
            True if full exploration + plan is needed, False to skip straight to execute.
        """
        decision = should_plan(user_request)
        return decision in ("plan", "analyze", "auto")

    @staticmethod
    def _should_analyze_only(user_request: str) -> bool:
        """Check if this is a pure analysis task (no execution needed)."""
        from .plan_mode import should_plan

        return should_plan(user_request) == "analyze"

    async def run(
        self,
        user_request: str,
        progress_callback: Callable[[str, dict], None] | None = None,
        explore_first: bool | None = None,
        cwd: str | None = None,
    ) -> dict[str, Any]:
        """Plan and execute a mission from a natural language request.

        Args:
            user_request: The user's natural language request.
            progress_callback: Optional callback(event_type, data) for progress updates.
            explore_first: Whether to explore codebase before planning.
                - None (default): auto-detect based on task complexity heuristics.
                - True: always run full P-EVR plan + execute cycle.
                - False: skip exploration and planning, execute directly.
            cwd: Working directory override. If omitted, auto-detect from user_request.

        Returns:
            Execution summary dict with keys: mission_id, snapshot, success, error, mission, metrics.
        """
        # Resolve auto-detect for explore_first
        if explore_first is None:
            explore_first = self._should_explore_and_plan(user_request)

        # Allow per-run override of the working directory
        if cwd and cwd != str(Path.cwd()):
            # Caller explicitly provided a non-default cwd — use it
            self._cwd = cwd
        else:
            # Auto-detect target directory from user request when not explicitly provided
            from ..components.repl import _extract_target_path

            detected = _extract_target_path(user_request)
            if detected:
                self._cwd = detected

        # Detect and preserve user's language preference for all tasks
        self._user_language = self._detect_language(user_request)

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
                exploration = await explore_codebase(
                    user_request, self.project_memory, cwd=self._cwd
                )

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
            snapshot = result.get("snapshot", {})
            result["success"] = snapshot.get("status") == "completed"
            if not result["success"] and not result.get("error"):
                failed = snapshot.get("failed_tasks", 0)
                total = snapshot.get("total_tasks", 0)
                result["error"] = f"{failed}/{total} task(s) failed or were rejected"

            # Collect non-blocking verification warnings from all tasks
            warnings: list[dict[str, Any]] = []
            dag = self._orchestrator.tracker.get_dag(mission.mission_id)
            if dag:
                for task_id, node in dag.nodes.items():
                    for level in (1, 2, 3):
                        vkey = f"_verification_{level}"
                        vresult = node.artifacts.get(vkey)
                        if vresult is not None and hasattr(vresult, "issues"):
                            for issue in vresult.issues:
                                if issue.get("severity") == "warning" or (
                                    issue.get("severity") == "error"
                                    and not issue.get("blocking", True)
                                ):
                                    warnings.append(
                                        {
                                            "task_id": task_id,
                                            "level": level,
                                            "category": issue.get("category", "unknown"),
                                            "message": issue.get("message", ""),
                                        }
                                    )
            result["warnings"] = warnings

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

    async def _run_inline_verification(
        self, task: TaskSpec, changed_paths: list[str]
    ) -> str | None:
        """Run lightweight L1+L2 verification on recently changed files.

        Returns a human-readable issue summary, or None if all clear.
        """
        issues: list[str] = []
        checked: set[str] = set()

        for path in changed_paths:
            if path in checked:
                continue
            checked.add(path)
            abs_path = os.path.join(self._cwd, path) if not os.path.isabs(path) else path

            # L1: existence + non-empty
            if not os.path.exists(abs_path):
                issues.append(f"  - {path}: file not found after write")
                continue
            if os.path.getsize(abs_path) == 0:
                issues.append(f"  - {path}: file is empty")

            # L2: syntax check for Python
            if path.endswith(".py"):
                try:
                    py_compile.compile(abs_path, doraise=True)
                except py_compile.PyCompileError as e:
                    issues.append(f"  - {path}: syntax error – {e}")

            # L2: syntax check for JavaScript (lightweight)
            elif path.endswith(".js"):
                import shutil

                if shutil.which("node"):
                    proc = await asyncio.create_subprocess_exec(
                        "node",
                        "--check",
                        abs_path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    _, stderr = await proc.communicate()
                    if proc.returncode != 0:
                        err = stderr.decode("utf-8", errors="replace")[:200]
                        issues.append(f"  - {path}: JS syntax error – {err}")

            # L1: line count constraint
            if task.constraints.max_lines and os.path.isfile(abs_path):
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    line_count = sum(1 for _ in f)
                if line_count > task.constraints.max_lines:
                    issues.append(
                        f"  - {path}: {line_count} lines exceeds limit "
                        f"({task.constraints.max_lines})"
                    )

        return "\n".join(issues) if issues else None

    def _calibrate_from_mission_result(self, mission_id: str) -> None:
        """Analyze mission execution results and update capability scores."""
        from .results import ExecutionResult
        from ..model_capability.runtime_tracker import TaskOutcome

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
        stats = self.calibrator.get_stats()
        logger.info(
            "Runtime tracking: success_rate=%.1f%% json=%.1f%% code=%.1f%% planning=%.1f%%",
            self.calibrator.get_success_rate() * 100,
            stats.get_rate("json") * 100,
            stats.get_rate("code") * 100,
            stats.get_rate("planning") * 100,
        )
