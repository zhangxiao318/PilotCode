"""Adaptive verifier implementations that scale with model capability.

These verifiers are used when the model's code review capability is insufficient
for full structured JSON L3 review. They provide simplified or static-analysis-based
alternatives.
"""

from __future__ import annotations

import asyncio
import os
import sys

from pilotcode.utils.model_client import get_model_client, Message

from ..results import ExecutionResult
from ..task_spec import TaskSpec
from ..verifier.base import VerificationResult, Verdict


async def simplified_l3_verifier(
    task: TaskSpec, exec_result: ExecutionResult
) -> VerificationResult:
    """L3 verifier for medium-capability models.

    Uses LLM review but with simpler prompt and string-based fallback.
    Does not require strict JSON output.
    """
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
        f"Review code changes for task: {task.title}\n"
        f"Objective: {task.objective}\n"
        f"Changed files: {', '.join(changed_files)}\n\n"
        f"Is the implementation correct? Answer with one word: PASS or FAIL."
    )
    try:
        messages = [
            Message(role="system", content="You are a code reviewer. Be concise."),
            Message(role="user", content=review_prompt),
        ]
        accumulated = ""
        async for chunk in client.chat_completion(messages=messages, temperature=0.2, stream=False):
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            c = delta.get("content")
            if c:
                accumulated += c

        review_lower = accumulated.lower()
        passed = "pass" in review_lower or "correct" in review_lower or "good" in review_lower
        failed = "fail" in review_lower or "error" in review_lower or "bug" in review_lower

        if passed and not failed:
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
                score=50.0,
                feedback=f"Review: {accumulated[:300]}",
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


async def static_analysis_l3_verifier(
    task: TaskSpec, exec_result: ExecutionResult
) -> VerificationResult:
    """L3 verifier for low-capability models.

    Uses only static analysis tools (ruff, mypy if available) instead of LLM review.
    This avoids wasting tokens on a model that cannot produce reliable reviews.
    """
    changed_files = exec_result.artifacts.get("changed_files", [])
    if not changed_files:
        return VerificationResult(
            task_id=task.id,
            level=3,
            passed=True,
            score=100.0,
            verdict=Verdict.APPROVE,
        )

    issues: list[str] = []
    score = 100.0

    # Run ruff if available
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "ruff",
            "check",
            *changed_files,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            output = stdout.decode("utf-8", errors="replace")
            issue_count = output.count("\n")
            issues.append(f"ruff found {issue_count} issues")
            score -= min(30, issue_count * 3)
    except (FileNotFoundError, asyncio.TimeoutError):
        pass  # ruff not installed
    except Exception:
        pass

    # Run mypy if available
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "mypy",
            *changed_files,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            output = stdout.decode("utf-8", errors="replace")
            issue_count = output.count("error:")
            issues.append(f"mypy found {issue_count} type issues")
            score -= min(30, issue_count * 5)
    except (FileNotFoundError, asyncio.TimeoutError):
        pass  # mypy not installed
    except Exception:
        pass

    # Check for basic code quality heuristics
    for fpath in changed_files:
        if not os.path.exists(fpath):
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            # Check for obvious issues
            if "TODO" in content or "FIXME" in content:
                issues.append(f"{fpath} contains TODO/FIXME")
                score -= 5
            # Check for very long lines
            long_lines = sum(1 for line in content.splitlines() if len(line) > 120)
            if long_lines > 5:
                issues.append(f"{fpath} has {long_lines} lines > 120 chars")
                score -= min(10, long_lines)
        except Exception:
            pass

    passed = score >= 70.0
    return VerificationResult(
        task_id=task.id,
        level=3,
        passed=passed,
        score=max(0.0, score),
        feedback="; ".join(issues) if issues else "Static analysis passed",
        verdict=Verdict.APPROVE if passed else Verdict.NEEDS_REWORK,
    )
