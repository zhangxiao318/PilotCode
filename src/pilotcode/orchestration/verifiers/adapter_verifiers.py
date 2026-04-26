"""L1/L2/L3 verifier implementations used by MissionAdapter.

These are standalone async functions that can be registered with the Orchestrator.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from pilotcode.utils.model_client import get_model_client, Message

from ..results import ExecutionResult
from ..task_spec import TaskSpec
from ..verifier.base import VerificationResult, Verdict


async def l1_simple_verifier(task: TaskSpec, exec_result: ExecutionResult) -> VerificationResult:
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
