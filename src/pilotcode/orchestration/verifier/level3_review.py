"""Level 3 verification: LLM Code Review.

Simulates a senior engineer reviewing the code for:
- Design compliance
- Logic correctness
- Boundary handling
- Maintainability
"""

from __future__ import annotations

import os
from typing import Any

from .base import BaseVerifier, VerificationResult, Verdict
from ..task_spec import TaskSpec, AcceptanceCriterion
from ..results import ExecutionResult


class CodeReviewVerifier(BaseVerifier):
    """Level 3 verifier: LLM-based code review.

    In production, this would call an LLM with a structured review prompt.
    For now, it provides a heuristic-based review framework.
    """

    level = 3

    async def verify(self, task: TaskSpec, execution_result: ExecutionResult) -> VerificationResult:
        """Run code review.

        Heuristic checks:
        1. Check acceptance criteria are met
        2. Check objective alignment (simple keyword matching)
        3. Check code quality heuristics
        """
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

    def _check_criterion(
        self, ac: AcceptanceCriterion, outputs: dict[str, str], task: TaskSpec
    ) -> bool:
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

        # Remove common stop words
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
