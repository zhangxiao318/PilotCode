"""UI adapter for P-EVR orchestration.

Bridges natural language requests to structured Mission execution via LLM.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
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
from .orchestrator import Orchestrator, OrchestratorConfig
from .results import ExecutionResult
from .verifier.base import VerificationResult, Verdict
from .context_strategy import (
    ContextStrategy,
    ContextStrategySelector,
    MissionPlanAdjuster,
    StrategyMetrics,
)
from .project_memory import ProjectMemory, FailedAttempt


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
    ):
        self._cancel_event = cancel_event or asyncio.Event()
        self._max_worker_turns = max_worker_turns
        self.context_budget = context_budget
        self.project_memory = project_memory or ProjectMemory()
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
        """Register L1/L2/L3 verifiers."""
        self._orchestrator.register_verifier(1, self._simple_verifier)
        self._orchestrator.register_verifier(2, self._test_verifier)
        self._orchestrator.register_verifier(3, self._code_review_verifier)

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
        """L1: Basic verifier — execution must succeed and produce output."""
        if not exec_result.success:
            return VerificationResult(
                task_id=task.id,
                level=1,
                passed=False,
                score=0.0,
                feedback=exec_result.error or "Execution failed without details",
                verdict=Verdict.REJECT,
            )
        if not exec_result.output and not exec_result.artifacts.get("changed_files"):
            return VerificationResult(
                task_id=task.id,
                level=1,
                passed=False,
                score=30.0,
                feedback="Execution succeeded but produced no output or file changes",
                verdict=Verdict.NEEDS_REWORK,
            )
        return VerificationResult(
            task_id=task.id,
            level=1,
            passed=True,
            score=100.0,
            verdict=Verdict.APPROVE,
        )

    @staticmethod
    async def _test_verifier(task: TaskSpec, exec_result: ExecutionResult) -> VerificationResult:
        """L2: Test verifier — run acceptance criteria as tests if possible."""
        import subprocess
        import os

        # If the task mentions tests or pytest, try to run them
        changed_files = exec_result.artifacts.get("changed_files", [])
        has_test_file = any("test" in f.lower() for f in changed_files)

        # Run pytest if there are test files or if acceptance criteria suggest testing
        should_run_tests = has_test_file or any(
            ac.verification_method in ("test", "pytest") for ac in task.acceptance_criteria
        )

        if not should_run_tests:
            # No tests to run — auto-pass L2
            return VerificationResult(
                task_id=task.id,
                level=2,
                passed=True,
                score=100.0,
                verdict=Verdict.APPROVE,
            )

        cwd = os.getcwd()
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pytest",
                "-xvs",
                "-q",
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            output = stdout.decode("utf-8", errors="replace") + stderr.decode(
                "utf-8", errors="replace"
            )
            if proc.returncode == 0:
                return VerificationResult(
                    task_id=task.id,
                    level=2,
                    passed=True,
                    score=100.0,
                    verdict=Verdict.APPROVE,
                )
            else:
                return VerificationResult(
                    task_id=task.id,
                    level=2,
                    passed=False,
                    score=50.0,
                    feedback=f"Tests failed:\n{output}",
                    verdict=Verdict.NEEDS_REWORK,
                )
        except Exception as e:
            return VerificationResult(
                task_id=task.id,
                level=2,
                passed=False,
                score=0.0,
                feedback=f"Could not run tests: {e}",
                verdict=Verdict.NEEDS_REWORK,
            )

    @staticmethod
    async def _code_review_verifier(
        task: TaskSpec, exec_result: ExecutionResult
    ) -> VerificationResult:
        """L3: LLM-based code review verifier."""
        changed_files = exec_result.artifacts.get("changed_files", [])
        if not changed_files:
            return VerificationResult(
                task_id=task.id,
                level=3,
                passed=True,
                score=100.0,
                verdict=Verdict.APPROVE,
            )

        client = get_model_client()
        review_prompt = (
            f"Review the following code changes for correctness, style, and alignment with the task objective.\n\n"
            f"Task: {task.title}\n"
            f"Objective: {task.objective}\n\n"
            f"Changed files: {', '.join(changed_files)}\n\n"
            f"Worker output summary:\n{exec_result.output[:2000]}\n\n"
            f"Provide a brief review: APPROVE if correct, NEEDS_REWORK if issues found."
        )
        try:
            messages = [
                Message(role="system", content="You are a code reviewer. Be concise."),
                Message(role="user", content=review_prompt),
            ]
            accumulated = ""
            async for chunk in client.chat_completion(
                messages=messages, temperature=0.2, stream=False
            ):
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                c = delta.get("content")
                if c:
                    accumulated += c

            review = accumulated.lower()
            if "approve" in review or "looks good" in review or "correct" in review:
                return VerificationResult(
                    task_id=task.id,
                    level=3,
                    passed=True,
                    score=100.0,
                    verdict=Verdict.APPROVE,
                )
            else:
                return VerificationResult(
                    task_id=task.id,
                    level=3,
                    passed=False,
                    score=60.0,
                    feedback=f"Code review feedback: {accumulated[:500]}",
                    verdict=Verdict.NEEDS_REWORK,
                )
        except Exception as e:
            return VerificationResult(
                task_id=task.id,
                level=3,
                passed=False,
                score=0.0,
                feedback=f"Review failed: {e}",
                verdict=Verdict.NEEDS_REWORK,
            )

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

        plan_data = self._extract_json(accumulated)

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
            match = re.search(r"\{.*?\}", text, re.DOTALL)
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

        config = QueryEngineConfig(
            cwd=app_state.cwd,
            tools=autonomous_tools,
            get_app_state=store.get_state,
            set_app_state=store.set_state,
            max_turns=max(5, max_turns // 2),  # QueryEngine internal budget
        )
        engine = QueryEngine(config)
        executor = get_tool_executor()

        final_content = ""
        artifacts: dict[str, Any] = {}
        total_turns = 0
        file_reads_this_task: list[tuple[str, str]] = []  # (path, summary_hint)

        try:
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
                    user_prompt = self._build_continue_prompt(engine, task)

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
                        from pilotcode.tools.bash_tool import strip_ansi

                        final_content = strip_ansi(str(msg.content))
                    if isinstance(msg, ToolUseMessage):
                        pending_tools.append(msg)

                if not pending_tools:
                    break

                # Execute tools and feed results back
                tool_ctx = ToolUseContext(
                    get_app_state=store.get_state,
                    set_app_state=lambda f: store.set_state(f),
                    cwd=getattr(store.get_state(), "cwd", ""),
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

                    # Update project memory from tool results
                    self._update_memory_from_tool(
                        tu, result_text, exec_result.success, file_reads_this_task
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
    # Continue prompt with context
    # ------------------------------------------------------------------

    def _build_continue_prompt(self, engine: QueryEngine, task: TaskSpec) -> str:
        """Build a contextual continue prompt instead of bare 'Please continue.'."""
        # Summarize what has happened so far
        actions: list[str] = []
        changed: list[str] = []
        errors: list[str] = []

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
                    actions.append(f"edited {path}")
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
    # Explore-Plan Loop (P2)
    # ------------------------------------------------------------------

    async def _explore_codebase(self, user_request: str) -> dict[str, Any]:
        """Quickly explore the codebase to understand structure before planning.

        Returns a dict with keys: files, conventions, architecture_notes.
        """
        import os
        import glob as pyglob

        exploration: dict[str, Any] = {"files": [], "conventions": {}, "architecture_notes": []}

        # Quick scan of Python files (offload sync I/O to thread)
        try:
            py_files = await asyncio.to_thread(pyglob.glob, "**/*.py", recursive=True)
            exploration["files"] = py_files[:50]
        except Exception:
            import logging

            logging.getLogger(__name__).debug("Exploration glob failed", exc_info=True)

        # Try to find key files mentioned in request
        keywords = [w for w in user_request.lower().split() if len(w) > 3]
        key_files_found = []
        for keyword in keywords[:5]:
            for fpath in exploration["files"]:
                if keyword in fpath.lower() and fpath not in key_files_found:
                    key_files_found.append(fpath)
                    if len(key_files_found) >= 10:
                        break
            if len(key_files_found) >= 10:
                break

        # Read top-level files to understand project structure
        top_level_files = [
            "README.md",
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "requirements.txt",
        ]
        for fname in top_level_files:
            fpath = os.path.join(os.getcwd(), fname)
            try:
                exists = await asyncio.to_thread(os.path.exists, fpath)
                if not exists:
                    continue
                content = await asyncio.to_thread(
                    lambda p: open(p, "r", encoding="utf-8").read(), fpath
                )
                self.project_memory.record_file_read(
                    fname, content, summary=content[:200].replace("\n", " ")
                )
                if fname == "pyproject.toml":
                    if "fastapi" in content.lower():
                        self.project_memory.record_convention("framework", "FastAPI")
                    elif "django" in content.lower():
                        self.project_memory.record_convention("framework", "Django")
                    elif "flask" in content.lower():
                        self.project_memory.record_convention("framework", "Flask")
            except Exception:
                import logging

                logging.getLogger(__name__).debug(
                    "Exploration file read failed for %s", fname, exc_info=True
                )

        exploration["key_files"] = key_files_found
        return exploration

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
                exploration = await self._explore_codebase(user_request)

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
