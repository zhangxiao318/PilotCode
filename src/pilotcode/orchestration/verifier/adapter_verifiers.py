"""L1/L2/L3 verifier implementations used by MissionAdapter.

These are standalone async functions that can be registered with the Orchestrator.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from pilotcode.utils.model_client import get_model_client, Message

from ..results import ExecutionResult
from ..task_spec import TaskSpec
from .base import VerificationResult, Verdict

# Agent types that only read/explore — success = executed tools, not file changes
_READ_ONLY_AGENT_TYPES = {"explorer", "verifier", "explainer", "planner"}


def _l1_readonly_verifier(
    task: TaskSpec, exec_result: ExecutionResult
) -> VerificationResult | None:
    """Validate read-only agents: success if tools were executed."""
    has_output = bool(exec_result.output and exec_result.output.strip())
    conv_len = exec_result.artifacts.get("conversation_length", 0)
    had_tool_activity = isinstance(conv_len, (int, float)) and conv_len >= 2

    if has_output or had_tool_activity:
        return VerificationResult(
            task_id=task.id,
            level=1,
            passed=True,
            score=90.0 if has_output else 80.0,
            feedback="Analysis/exploration task completed",
            verdict=Verdict.APPROVE,
        )
    return None  # fall through to generic failure


def _l1_coder_verifier(task: TaskSpec, exec_result: ExecutionResult) -> VerificationResult | None:
    """Validate code-writing agents: success if output or file changes exist."""
    has_output = bool(exec_result.output and exec_result.output.strip())
    has_changes = bool(exec_result.artifacts.get("changed_files"))

    if has_output or has_changes:
        return VerificationResult(
            task_id=task.id,
            level=1,
            passed=True,
            score=100.0,
            verdict=Verdict.APPROVE,
        )
    return None  # fall through to generic failure


async def l1_simple_verifier(task: TaskSpec, exec_result: ExecutionResult) -> VerificationResult:
    """L1: Basic verifier — execution must succeed and produce output.

    Different agent types have different success criteria:
    - explorer/verifier/explainer/planner: tool execution is enough
    - coder/tester/debugger: need output or file changes
    """
    if not exec_result.success:
        return VerificationResult(
            task_id=task.id,
            level=1,
            passed=False,
            score=0.0,
            feedback=exec_result.error or "Execution failed without details",
            verdict=Verdict.REJECT,
        )

    agent_type = exec_result.artifacts.get("agent_type", "")
    if agent_type in _READ_ONLY_AGENT_TYPES:
        result = _l1_readonly_verifier(task, exec_result)
        if result is not None:
            return result
    else:
        result = _l1_coder_verifier(task, exec_result)
        if result is not None:
            return result

    # Generic fallback for unknown agent types or unmet criteria
    has_final_response = bool(exec_result.artifacts.get("final_response"))
    if has_final_response:
        return VerificationResult(
            task_id=task.id,
            level=1,
            passed=True,
            score=80.0,
            feedback="Task completed — response recorded",
            verdict=Verdict.APPROVE,
        )

    return VerificationResult(
        task_id=task.id,
        level=1,
        passed=False,
        score=30.0,
        feedback="Execution succeeded but produced no output or file changes",
        verdict=Verdict.NEEDS_REWORK,
    )


async def l2_test_verifier(task: TaskSpec, exec_result: ExecutionResult) -> VerificationResult:
    """L2: Test verifier — run acceptance criteria as tests if possible."""
    changed_files = exec_result.artifacts.get("changed_files", [])
    has_test_file = any("test" in f.lower() for f in changed_files)

    should_run_tests = has_test_file or any(
        ac.verification_method in ("test", "pytest") for ac in task.acceptance_criteria
    )

    if not should_run_tests:
        return VerificationResult(
            task_id=task.id,
            level=2,
            passed=True,
            score=100.0,
            verdict=Verdict.APPROVE,
        )

    # Guard: if no files were changed by this task, skip pytest.
    # Prevents running the full project test suite for analysis/planning tasks.
    if not changed_files:
        return VerificationResult(
            task_id=task.id,
            level=2,
            passed=True,
            score=100.0,
            verdict=Verdict.APPROVE,
        )

    cwd = os.getcwd()

    # Build targeted pytest args: only run tests related to changed files.
    # If changed test files exist, run those. Otherwise fall back to full suite.
    pytest_args = [sys.executable, "-m", "pytest", "-xvs", "-q"]
    test_files = [f for f in changed_files if "test" in os.path.basename(f).lower()]
    if test_files:
        # Run only the changed test files
        pytest_args.extend(test_files)
    else:
        # No test files changed: try to discover tests for changed modules.
        # Use pytest -k with module names as a best-effort filter.
        module_names: list[str] = []
        for f in changed_files:
            if f.endswith(".py"):
                name = os.path.splitext(os.path.basename(f))[0]
                if name and name not in module_names:
                    module_names.append(name)
        if module_names:
            pytest_args.extend(["-k", " or ".join(module_names)])
        # If no modules found either, pytest_args stays as full-suite default

    try:
        proc = await asyncio.create_subprocess_exec(
            *pytest_args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        output = stdout.decode("utf-8", errors="replace") + stderr.decode("utf-8", errors="replace")
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


async def l3_code_review_verifier(
    task: TaskSpec, exec_result: ExecutionResult
) -> VerificationResult:
    """L3: LLM-based code review verifier with structured JSON output."""
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
        "Respond ONLY with a JSON object in this exact format:\n"
        '{"verdict": "APPROVE|NEEDS_REWORK", "score": 0-100, "feedback": "concise review"}'
    )
    try:
        messages = [
            Message(role="system", content="You are a code reviewer. Output JSON only."),
            Message(role="user", content=review_prompt),
        ]
        accumulated = ""
        async for chunk in client.chat_completion(messages=messages, temperature=0.2, stream=False):
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            c = delta.get("content")
            if c:
                accumulated += c

        # Try structured JSON parsing first
        try:
            review_data = json.loads(accumulated)
            verdict_str = review_data.get("verdict", "NEEDS_REWORK").upper()
            score = float(review_data.get("score", 0))
            feedback = review_data.get("feedback", "No feedback provided")
            verdict = Verdict.APPROVE if verdict_str == "APPROVE" else Verdict.NEEDS_REWORK
            return VerificationResult(
                task_id=task.id,
                level=3,
                passed=(verdict == Verdict.APPROVE),
                score=score,
                feedback=feedback,
                verdict=verdict,
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

        # Fallback: string matching
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
