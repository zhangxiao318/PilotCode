"""Level 2 verification: test execution.

Runs unit tests and integration tests for task outputs.
Supports multiple languages via compiler/syntax checks.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from typing import Any

from .base import BaseVerifier, VerificationResult, Verdict
from ..task_spec import TaskSpec
from ..results import ExecutionResult


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

_LANGUAGE_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".rs": "rust",
    ".go": "go",
    ".js": "javascript",
    ".ts": "typescript",
    ".java": "java",
    ".sh": "shell",
}

_COMPILER_CHECKS: dict[str, tuple[str, ...]] = {
    "c": ("gcc", "-fsyntax-only"),
    "cpp": ("g++", "-fsyntax-only"),
    "rust": ("rustc", "--crate-type", "bin", "--emit=metadata"),
    "go": ("go", "build", "-o", "/dev/null"),
    "javascript": ("node", "--check"),
    "typescript": ("tsc", "--noEmit"),
    "java": ("javac", "-d", "/tmp"),
}


class PytestRunnerVerifier(BaseVerifier):
    """Level 2 verifier: runs tests against task outputs.

    Supports:
    - Python: pytest (if available) + py_compile fallback
    - C/C++: gcc/clang -fsyntax-only
    - Rust: rustc --emit=metadata
    - Go: go build
    - JS/TS: node --check / tsc --noEmit
    - Java: javac
    - Others: syntax-only heuristics
    """

    level = 2

    def __init__(self, test_command: str | None = None):
        self.test_command = test_command

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def verify(self, task: TaskSpec, execution_result: ExecutionResult) -> VerificationResult:
        issues: list[dict[str, Any]] = []
        metrics: dict[str, Any] = {}
        score = 100.0

        # Detect languages from task outputs
        langs = self._detect_languages(task)
        metrics["languages"] = list(langs.keys())

        # If no outputs to verify, skip
        if not langs:
            return self._make_result(
                task, passed=True, score=80.0, issues=[],
                feedback="No code outputs to verify.",
                verdict=Verdict.APPROVE, metrics=metrics,
            )

        results: list[dict[str, Any]] = []

        for lang, files in langs.items():
            if lang == "python":
                res = await self._verify_python(files, task)
            elif lang in _COMPILER_CHECKS:
                res = await self._verify_compiled(lang, files)
            else:
                res = await self._verify_generic(files)
            results.append(res)
            issues.extend(res.get("issues", []))
            score -= res.get("score_penalty", 0.0)

        score = max(0.0, min(100.0, score))
        # Blocking errors trigger NEEDS_REWORK; warnings are recorded but don't block
        has_blocking_error = any(
            i["severity"] == "error" and i.get("blocking", True)
            for i in issues
        )
        passed = score >= 60.0 and not has_blocking_error

        verdict = Verdict.APPROVE if passed else Verdict.NEEDS_REWORK
        if score < 30.0:
            verdict = Verdict.REJECT

        # Build summary feedback
        lines: list[str] = []
        for r in results:
            status = "✓" if r.get("ok") else "✗"
            lines.append(f"{status} {r['lang']}: {r['feedback']}")
        feedback = "\n".join(lines)

        metrics["score"] = score
        metrics["passed"] = passed

        return self._make_result(
            task, passed=passed, score=score,
            issues=issues, feedback=feedback,
            verdict=verdict, metrics=metrics,
        )

    # ------------------------------------------------------------------
    # Language-specific verifiers
    # ------------------------------------------------------------------

    async def _verify_python(self, files: list[str], task: TaskSpec) -> dict[str, Any]:
        """Verify Python files: try pytest, fall back to py_compile."""
        issues: list[dict[str, Any]] = []
        ok = True
        feedback = ""
        penalty = 0.0

        # First: syntax check all files with py_compile
        for f in files:
            try:
                import py_compile as pc
                pc.compile(f, doraise=True)
            except Exception as e:
                ok = False
                penalty += 20.0
                issues.append({
                    "severity": "error",
                    "category": "syntax_error",
                    "message": f"{os.path.basename(f)}: {e}",
                    "blocking": True,
                })

        # Second: pytest if available
        test_files = self._discover_tests(task)
        if test_files and self._pytest_available():
            result = await self._run_pytest(test_files)
            if result["exit_code"] != 0:
                ok = False
                penalty += 30.0
                failed = self._parse_failures(result["stdout"] + result["stderr"])
                issues.append({
                    "severity": "error",
                    "category": "test_failure",
                    "message": f"pytest exit={result['exit_code']}, failed: {failed[:3]}",
                    "blocking": True,
                })
                feedback = f"pytest failed ({len(failed)} failures)"
            else:
                feedback = "pytest passed"
        elif test_files:
            feedback = "pytest not installed; skipped runtime tests"
        else:
            feedback = "no pytest tests found; syntax OK"

        if not ok:
            feedback = f"Python verification failed. {feedback}"

        return {
            "lang": "python",
            "ok": ok,
            "issues": issues,
            "score_penalty": penalty,
            "feedback": feedback,
        }

    async def _verify_compiled(self, lang: str, files: list[str]) -> dict[str, Any]:
        """Verify compiled languages via compiler syntax check."""
        compiler = _COMPILER_CHECKS.get(lang)
        if not compiler:
            return {
                "lang": lang,
                "ok": True,
                "issues": [],
                "score_penalty": 0.0,
                "feedback": f"no compiler configured for {lang}",
            }

        # Check compiler exists
        binary = compiler[0]
        if not shutil.which(binary):
            return {
                "lang": lang,
                "ok": True,
                "issues": [{
                    "severity": "warning",
                    "category": "compiler_missing",
                    "message": f"{binary} not found; skipping {lang} compile check",
                    "blocking": False,
                }],
                "score_penalty": 0.0,
                "feedback": f"{binary} not installed; skipped",
            }

        issues: list[dict[str, Any]] = []
        ok = True
        penalty = 0.0

        for f in files:
            cmd = list(compiler) + [f]
            result = await self._run_command(*cmd)
            if result["exit_code"] != 0:
                ok = False
                penalty += 25.0
                err = (result["stderr"] or result["stdout"])[:300]
                issues.append({
                    "severity": "error",
                    "category": "compile_error",
                    "message": f"{os.path.basename(f)}: {err}",
                    "blocking": True,
                })

        if ok:
            feedback = f"{binary} syntax check passed for {len(files)} file(s)"
        else:
            feedback = f"{binary} found compile errors in {len([i for i in issues if i['category'] == 'compile_error'])} file(s)"

        return {
            "lang": lang,
            "ok": ok,
            "issues": issues,
            "score_penalty": penalty,
            "feedback": feedback,
        }

    async def _verify_generic(self, files: list[str]) -> dict[str, Any]:
        """Fallback for unsupported languages: just check file exists and is non-empty."""
        issues: list[dict[str, Any]] = []
        ok = True
        for f in files:
            if os.path.getsize(f) == 0:
                ok = False
                issues.append({
                    "severity": "warning",
                    "category": "empty_file",
                    "message": f"{os.path.basename(f)} is empty",
                    "blocking": True,
                })
        return {
            "lang": "generic",
            "ok": ok,
            "issues": issues,
            "score_penalty": 0.0,
            "feedback": "generic check (file existence + non-empty)",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _detect_languages(self, task: TaskSpec) -> dict[str, list[str]]:
        """Group task outputs by detected language."""
        langs: dict[str, list[str]] = {}
        for output in getattr(task, "outputs", []) or []:
            _, ext = os.path.splitext(output)
            lang = _LANGUAGE_BY_EXT.get(ext, "generic")
            langs.setdefault(lang, []).append(output)
        return langs

    def _pytest_available(self) -> bool:
        """Check if pytest is installed in the current environment."""
        return shutil.which("pytest") is not None

    def _discover_tests(self, task: TaskSpec) -> list[str]:
        """Discover test files related to task outputs."""
        test_files = []
        for output in getattr(task, "outputs", []) or []:
            base = os.path.splitext(output)[0]
            candidates = [
                f"{base}_test.py",
                f"test_{os.path.basename(base)}.py",
                f"tests/{os.path.basename(base)}_test.py",
                f"tests/test_{os.path.basename(base)}.py",
            ]
            for candidate in candidates:
                if os.path.exists(candidate):
                    test_files.append(candidate)
        return test_files

    async def _run_pytest(self, test_files: list[str]) -> dict[str, Any]:
        if not test_files:
            return {"exit_code": 0, "stdout": "No tests found", "stderr": ""}
        return await self._run_command(
            sys.executable, "-m", "pytest", *test_files, "-q", "--tb=short"
        )

    async def _run_command(self, *cmd: str) -> dict[str, Any]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return {
                "exit_code": proc.returncode or 0,
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
            }
        except Exception as e:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
            }

    def _parse_failures(self, output: str) -> list[str]:
        failed = []
        for line in output.splitlines():
            if "FAILED" in line or "ERROR" in line:
                parts = line.split()
                for part in parts:
                    if "::" in part or "test_" in part:
                        failed.append(part)
                        break
        return failed

    def _make_result(
        self,
        task: TaskSpec,
        passed: bool,
        score: float,
        issues: list[dict[str, Any]],
        feedback: str,
        verdict: Verdict,
        metrics: dict[str, Any],
    ) -> VerificationResult:
        return VerificationResult(
            task_id=task.id,
            level=self.level,
            passed=passed,
            score=score,
            issues=issues,
            feedback=feedback,
            verdict=verdict,
            metrics=metrics,
        )
