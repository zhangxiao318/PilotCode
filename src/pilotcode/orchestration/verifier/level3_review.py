"""Level 3 verification: LLM Code Review.

Uses an LLM to perform semantic code review for:
- Design compliance
- Logic correctness
- Boundary handling
- Maintainability

Falls back to heuristic checks when LLM review is unavailable.
"""

from __future__ import annotations

import json
import os
from typing import Any

from .base import BaseVerifier, VerificationResult, Verdict
from ..task_spec import TaskSpec
from ..results import ExecutionResult


class CodeReviewVerifier(BaseVerifier):
    """Level 3 verifier: LLM-based code review.

    Primary path: calls an LLM with a structured review prompt.
    Fallback path: heuristic-based review when LLM is unavailable.
    """

    level = 3

    async def verify(self, task: TaskSpec, execution_result: ExecutionResult) -> VerificationResult:
        """Run code review.

        Tries LLM-driven review first, falls back to heuristic checks.
        """
        # Primary: LLM-driven semantic review
        try:
            llm_result = await self._llm_review(task, execution_result)
            if llm_result is not None:
                return llm_result
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "LLM L3 review failed, falling back to heuristic: %s", exc, exc_info=True
            )

        # Fallback: heuristic checks
        return await self._heuristic_review(task, execution_result)

    async def _llm_review(
        self, task: TaskSpec, execution_result: ExecutionResult
    ) -> VerificationResult | None:
        """Call an LLM to perform semantic code review.

        Returns None if LLM is not configured or review fails.
        """
        from pilotcode.utils.model_client import get_model_client, Message

        client = get_model_client()

        # Read all output files
        outputs_content: dict[str, str] = {}
        for output_path in task.outputs:
            if os.path.isfile(output_path):
                try:
                    with open(output_path, "r", encoding="utf-8", errors="replace") as f:
                        outputs_content[output_path] = f.read()
                except Exception:
                    pass

        if not outputs_content:
            return None

        # Build diff/content block
        code_blocks = []
        for path, content in outputs_content.items():
            code_blocks.append(f"--- {path} ---\n{content}\n")
        code_text = "\n".join(code_blocks)

        # Build acceptance criteria text
        ac_text = ""
        if task.acceptance_criteria:
            ac_text = "\n".join(f"- {ac.description}" for ac in task.acceptance_criteria)

        # --- Verification Synergy: read L1/L2 context ---
        synergy_parts = []
        l1_result = execution_result.artifacts.get("_verification_1")
        if l1_result and l1_result.issues:
            synergy_parts.append("L1 Static Analysis findings:")
            for issue in l1_result.issues:
                synergy_parts.append(
                    f"  - [{issue.get('severity', 'info')}] {issue.get('message', '')}"
                )

        l2_result = execution_result.artifacts.get("_verification_2")
        if l2_result and l2_result.issues:
            synergy_parts.append("L2 Test/Compile findings:")
            for issue in l2_result.issues:
                synergy_parts.append(
                    f"  - [{issue.get('severity', 'info')}] {issue.get('message', '')}"
                )
            if l2_result.feedback:
                synergy_parts.append(f"L2 Feedback: {l2_result.feedback[:500]}")

        synergy_text = "\n".join(synergy_parts) if synergy_parts else ""

        prompt = (
            "You are a senior code reviewer. Review the following code changes "
            "and respond with a JSON object only.\n\n"
            f"Task Objective: {task.objective}\n\n"
            f"Acceptance Criteria:\n{ac_text}\n\n"
        )
        if synergy_text:
            prompt += f"Previous Verification Results:\n{synergy_text}\n\n"
        prompt += (
            f"Code:\n```\n{code_text[:8000]}\n```\n\n"
            "Review dimensions:\n"
            "1. Logic correctness (boundary conditions, edge cases, concurrency)\n"
            "2. Design consistency (follows project patterns, no architectural violations)\n"
            "3. Test coverage (are critical paths tested?)\n"
            "4. Regression risk (could this break existing functionality?)\n"
        )
        if synergy_text:
            prompt += (
                "5. Address any L1/L2 findings above that were not already fixed.\n"
                "Focus your review on the files/functions mentioned in L2 failures.\n"
            )
        prompt += (
            "\nRespond ONLY with valid JSON in this exact format:\n"
            '{"verdict": "APPROVE|NEEDS_REWORK|REJECT", '
            '"score": 0-100, '
            '"issues": [{"severity": "error|warning|info", "message": "..."}], '
            '"feedback": "concise summary"}'
        )

        messages = [Message(role="user", content=prompt)]

        # Use non-streaming to get a single response
        chunks = []
        async for chunk in client.chat_completion(messages, stream=False, temperature=0.2):
            chunks.append(chunk)

        if not chunks:
            return None

        # Extract content from the chunk
        content = ""
        for chunk in chunks:
            choices = chunk.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                content += delta.get("content", "")

        if not content:
            return None

        # Try to extract JSON from the response
        review = self._extract_json(content)
        if review is None:
            return None

        verdict_str = review.get("verdict", "NEEDS_REWORK").upper()
        score = float(review.get("score", 0))
        issues = review.get("issues", [])
        feedback = review.get("feedback", "LLM review completed.")

        verdict = Verdict.NEEDS_REWORK
        if verdict_str == "APPROVE":
            verdict = Verdict.APPROVE
        elif verdict_str == "REJECT":
            verdict = Verdict.REJECT

        passed = verdict == Verdict.APPROVE and score >= 60.0

        # Normalize issue severity
        normalized_issues = []
        for issue in issues:
            normalized_issues.append(
                {
                    "severity": issue.get("severity", "warning"),
                    "category": "llm_review",
                    "message": issue.get("message", ""),
                }
            )

        return VerificationResult(
            task_id=task.id,
            level=self.level,
            passed=passed,
            score=score,
            issues=normalized_issues,
            feedback=f"Code Review (L3) Score: {score:.0f}/100\n{feedback}",
            verdict=verdict,
            metrics={"review_method": "llm", "output_files": len(outputs_content)},
        )

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any] | None:
        """Extract JSON object from LLM response text."""
        # Try direct JSON parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object between braces
        import re

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return None

    async def _heuristic_review(
        self, task: TaskSpec, execution_result: ExecutionResult
    ) -> VerificationResult:
        """Heuristic fallback review when LLM is unavailable."""
        issues = []
        metrics = {}
        score = 100.0

        # Read all output files
        outputs_content = {}
        for output_path in task.outputs:
            if os.path.isfile(output_path):
                try:
                    with open(output_path, "r", encoding="utf-8", errors="replace") as f:
                        outputs_content[output_path] = f.read()
                except Exception:
                    import logging

                    logging.getLogger(__name__).debug(
                        "Output file read failed for %s", output_path, exc_info=True
                    )

        total_lines = sum(len(c.splitlines()) for c in outputs_content.values())
        metrics["total_output_lines"] = total_lines
        metrics["output_files"] = len(outputs_content)
        metrics["review_method"] = "heuristic"

        # 1. Check acceptance criteria
        ac_met = 0
        for ac in task.acceptance_criteria:
            if self._check_criterion(ac, outputs_content, task):
                ac_met += 1
            else:
                issues.append(
                    {
                        "severity": "warning",
                        "category": "acceptance_criteria",
                        "message": f"Acceptance criteria not met: {ac.description}",
                    }
                )
                score -= 15.0

        metrics["acceptance_criteria_met"] = ac_met
        metrics["acceptance_criteria_total"] = len(task.acceptance_criteria)

        # 2. Check objective alignment (keyword matching)
        objective_keywords = self._extract_keywords(task.objective)
        if objective_keywords:
            found_keywords = 0
            for content in outputs_content.values():
                for kw in objective_keywords:
                    if kw.lower() in content.lower():
                        found_keywords += 1
                        break
            alignment = found_keywords / len(objective_keywords) if objective_keywords else 1.0
            metrics["objective_alignment"] = alignment
            if alignment < 0.5:
                issues.append(
                    {
                        "severity": "warning",
                        "category": "objective_alignment",
                        "message": f"Code may not align with objective (alignment: {alignment:.1%})",
                    }
                )
                score -= 20.0

        # 3. Code quality heuristics
        for path, content in outputs_content.items():
            lines = content.splitlines()

            # Check for TODO/FIXME comments
            todos = [line for line in lines if "TODO" in line or "FIXME" in line or "HACK" in line]
            if todos:
                issues.append(
                    {
                        "severity": "info",
                        "category": "todos",
                        "message": f"Found {len(todos)} TODO/FIXME comment(s) in {path}",
                    }
                )
                score -= 5.0

            # Check for error handling
            has_try = "try:" in content
            has_except = "except" in content
            if not has_try and not has_except and len(lines) > 20:
                issues.append(
                    {
                        "severity": "info",
                        "category": "error_handling",
                        "message": f"No error handling found in {path}",
                    }
                )
                score -= 5.0

            # Check function length
            func_lengths = self._analyze_function_lengths(content)
            long_funcs = [f for f in func_lengths if f["lines"] > 50]
            if long_funcs:
                issues.append(
                    {
                        "severity": "info",
                        "category": "function_length",
                        "message": f"{len(long_funcs)} function(s) exceed 50 lines in {path}",
                    }
                )
                score -= 3.0 * len(long_funcs)

            # Check for docstrings
            if len(lines) > 30:
                has_docstring = '"""' in content or "'''" in content
                if not has_docstring:
                    issues.append(
                        {
                            "severity": "info",
                            "category": "documentation",
                            "message": f"No docstrings found in {path}",
                        }
                    )
                    score -= 3.0

        score = max(0.0, min(100.0, score))
        passed = score >= 60.0 and not any(i["severity"] == "error" for i in issues)

        verdict = Verdict.APPROVE if passed else Verdict.NEEDS_REWORK
        if score < 30.0:
            verdict = Verdict.REJECT

        feedback_parts = [f"Code Review (L3) Score: {score:.0f}/100"]
        if issues:
            feedback_parts.append(f"\nFound {len(issues)} observation(s):")
            for issue in issues:
                feedback_parts.append(f"  [{issue['severity']}] {issue['message']}")
        else:
            feedback_parts.append("\nAll review checks passed.")

        return VerificationResult(
            task_id=task.id,
            level=self.level,
            passed=passed,
            score=score,
            issues=issues,
            feedback="\n".join(feedback_parts),
            verdict=verdict,
            metrics=metrics,
        )

    def _check_criterion(self, ac: Any, outputs: dict[str, str], task: TaskSpec) -> bool:
        """Check if an acceptance criterion is met."""
        desc = ac.description.lower()

        # Simple keyword-based checks
        keywords = self._extract_keywords(desc)
        for content in outputs.values():
            content_lower = content.lower()
            matched = sum(1 for kw in keywords if kw in content_lower)
            if matched >= len(keywords) * 0.5:
                return True
        return False

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract meaningful keywords from text."""
        import re

        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "can",
            "need",
            "dare",
            "ought",
            "used",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "under",
            "and",
            "but",
            "or",
            "yet",
            "so",
            "if",
            "because",
            "although",
            "though",
            "while",
            "where",
            "when",
            "that",
            "which",
            "who",
            "whom",
            "whose",
            "what",
            "this",
            "these",
            "those",
            "i",
            "you",
            "he",
            "she",
            "it",
            "we",
            "they",
            "me",
            "him",
            "her",
            "us",
            "them",
        }
        words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text.lower())
        return [w for w in words if len(w) > 2 and w not in stop_words][:20]

    def _analyze_function_lengths(self, content: str) -> list[dict[str, Any]]:
        """Analyze function lengths in Python code."""
        import re

        functions = []
        lines = content.splitlines()
        i = 0
        while i < len(lines):
            match = re.match(r"^\s*def\s+(\w+)\s*\(", lines[i])
            if match:
                func_name = match.group(1)
                start = i
                indent = len(lines[i]) - len(lines[i].lstrip())
                i += 1
                while i < len(lines):
                    line = lines[i]
                    if line.strip() and (len(line) - len(line.lstrip())) <= indent:
                        break
                    i += 1
                functions.append(
                    {
                        "name": func_name,
                        "lines": i - start,
                    }
                )
            else:
                i += 1
        return functions
