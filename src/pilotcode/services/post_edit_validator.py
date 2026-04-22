"""Post-edit validation: auto-review and test after code changes."""

import os
import subprocess
from pathlib import Path
from typing import Any

from ..utils.model_client import ModelClient, Message
from ..utils.env_diagnosis import looks_like_environment_error, diagnose_and_fix_environment


# Test framework detection patterns
_TEST_FRAMEWORKS: list[tuple[str, list[str], str]] = [
    ("pytest", ["pytest.ini", "pyproject.toml", "setup.cfg", "setup.py", "tox.ini"], "python -m pytest -xvs"),
    ("pytest", ["tests", "test"], "python -m pytest -xvs"),
    ("npm", ["package.json"], "npm test"),
    ("cargo", ["Cargo.toml"], "cargo test"),
    ("go", ["go.mod"], "go test ./..."),
    ("gradle", ["build.gradle", "build.gradle.kts"], "./gradlew test"),
    ("maven", ["pom.xml"], "mvn test"),
]

# Reviewer system prompt — derived from the reviewer AgentDefinition
_REVIEWER_SYSTEM_PROMPT = """You are an expert code reviewer. Review the code changes provided and identify:
- Potential bugs or logic errors
- Code style and convention issues
- Missing error handling or edge cases
- Security concerns
- Performance issues

Be constructive and specific. For each issue, provide:
1. The file and location
2. What the issue is
3. How to fix it

If no issues are found, state clearly that the changes look good.
Use <complete> when the review is complete."""


class PostEditValidator:
    """Validates code changes after editing by running review and tests."""

    def __init__(self, model_client: ModelClient | None = None):
        self._model_client = model_client
        self._test_framework_cache: tuple[str | None, str | None] = (None, None)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def review_and_test(
        self, changed_files: list[str], cwd: str | None = None
    ) -> dict[str, Any]:
        """Run review and tests on changed files.

        Returns:
            {
                "review_result": str,
                "test_result": str,
                "test_env_ready": bool,
                "issues_found": bool,
                "redesign_prompt": str | None,  # P0: explicit redesign instructions if tests fail
            }
        """
        work_dir = cwd or str(os.getcwd())

        # --- Review ---
        review_result = await self.review_changes(changed_files, work_dir)
        issues_found = self._has_issues(review_result)

        # --- Detect test framework & targets (P2) ---
        framework_cmd, test_targets = self.detect_test_targets(work_dir)

        if framework_cmd:
            # P2: run only relevant tests if targets found
            test_result = await self.run_tests(framework_cmd, test_targets, work_dir)
            test_env_ready = True

            # P1: auto-fix environment errors and retry
            if looks_like_environment_error(test_result):
                fixed = await self._try_fix_env(test_result, work_dir)
                if fixed:
                    test_result = await self.run_tests(framework_cmd, test_targets, work_dir)

            # P0: determine if tests failed (not just env issues)
            tests_failed = self._tests_actually_failed(test_result)
            if tests_failed:
                issues_found = True
                redesign_prompt = self._build_redesign_prompt(
                    changed_files, review_result, test_result, work_dir
                )
            else:
                redesign_prompt = None
        else:
            test_result = (
                "NO_TEST_ENV: No test framework detected. "
                "Looked for pytest, npm test, cargo test, go test, gradle, maven. "
                "If you'd like to run tests, install a test framework first."
            )
            test_env_ready = False
            redesign_prompt = None

        return {
            "review_result": review_result,
            "test_result": test_result,
            "test_env_ready": test_env_ready,
            "issues_found": issues_found,
            "redesign_prompt": redesign_prompt,
        }

    async def review_changes(self, changed_files: list[str], cwd: str) -> str:
        """Run reviewer LLM on changed files."""
        if not self._model_client:
            return "[Review skipped: no model client configured]"

        review_content = self._build_review_content(changed_files, cwd)

        messages = [
            Message(role="system", content=_REVIEWER_SYSTEM_PROMPT),
            Message(role="user", content=review_content),
        ]

        accumulated = ""
        try:
            async for chunk in self._model_client.chat_completion(
                messages=messages,
                temperature=0.3,
                stream=True,
            ):
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content")
                if content:
                    accumulated += content
        except Exception as e:
            return f"[Review failed: {e}]"

        return accumulated or "[Review completed with no output]"

    def detect_test_targets(self, cwd: str | None = None) -> tuple[str | None, list[str] | None]:
        """Detect test framework and extract relevant test targets from git diff (P2).

        Returns:
            (framework_command, test_targets_or_None)
            If test_targets is None, run full test suite.
        """
        if self._test_framework_cache[0] is not None:
            return self._test_framework_cache

        work_dir = Path(cwd or os.getcwd())
        framework_cmd = None

        for _framework_name, markers, command in _TEST_FRAMEWORKS:
            for marker in markers:
                marker_path = work_dir / marker
                if marker_path.exists():
                    framework_cmd = command
                    break
            if framework_cmd:
                break

        if not framework_cmd:
            self._test_framework_cache = (None, None)
            return None, None

        # P2: extract test targets from git diff
        test_targets = self._extract_test_targets_from_diff(work_dir)

        self._test_framework_cache = (framework_cmd, test_targets)
        return framework_cmd, test_targets

    async def run_tests(self, command: str, targets: list[str] | None, cwd: str | None = None) -> str:
        """Run tests and return output."""
        work_dir = cwd or str(os.getcwd())

        if targets:
            if command.startswith("python -m pytest"):
                cmd = f"{command} {' '.join(targets)}"
            elif command.startswith("npm"):
                cmd = command  # npm test doesn't take file args easily
            elif command.startswith("cargo"):
                cmd = f"cargo test {' '.join(targets)}"
            else:
                cmd = f"{command} {' '.join(targets)}"
        else:
            cmd = command

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr
            if result.returncode != 0:
                output += f"\n[Exit code: {result.returncode}]"
            return output
        except subprocess.TimeoutExpired:
            return "[Tests timed out after 120 seconds]"
        except Exception as e:
            return f"[Test execution failed: {e}]"

    # ------------------------------------------------------------------
    # P1: Environment auto-fix
    # ------------------------------------------------------------------

    async def _try_fix_env(self, test_output: str, work_dir: str) -> bool:
        """Attempt to auto-fix environment errors. Returns True if fixed."""
        try:
            fixed = await diagnose_and_fix_environment(
                test_output,
                work_dir,
                auto_allow=True,
                interactive=False,
            )
            return fixed
        except Exception:
            return False

    # ------------------------------------------------------------------
    # P2: Smart test target extraction
    # ------------------------------------------------------------------

    def _extract_test_targets_from_diff(self, work_dir: Path) -> list[str] | None:
        """Extract relevant test files from git diff.

        Strategy:
        1. Look at changed files in diff
        2. For each changed source file, guess corresponding test file
        3. If guessing fails, look for test files that import the changed module
        """
        diff = self._get_git_diff(str(work_dir))
        if not diff:
            return None

        # Extract changed files from diff
        changed = set()
        for line in diff.split("\n"):
            if line.startswith("diff --git a/"):
                parts = line.split()
                if len(parts) >= 4:
                    # parts[2] is 'a/path', parts[3] is 'b/path'
                    filepath = parts[3][2:] if parts[3].startswith("b/") else parts[3]
                    changed.add(filepath)

        if not changed:
            return None

        targets = []
        for filepath in changed:
            # Skip non-code files
            if not filepath.endswith(".py"):
                continue

            # Strategy 1: direct test file mapping
            # e.g., src/module.py -> tests/test_module.py or src/test_module.py
            parts = filepath.split("/")
            basename = parts[-1][:-3]  # strip .py

            candidates = []
            # tests/test_basename.py
            candidates.append(f"tests/test_{basename}.py")
            # test_basename.py in same dir
            candidates.append("/".join(parts[:-1] + [f"test_{basename}.py"]))
            # tests/ dir with same relative path
            if parts[0] != "tests":
                candidates.append("tests/" + "/".join(parts[:-1] + [f"test_{basename}.py"]))

            for cand in candidates:
                if (work_dir / cand).exists():
                    targets.append(cand)
                    break

        # Strategy 2: if no direct mapping, check if any test files import changed modules
        if not targets:
            targets = self._find_tests_by_import(changed, work_dir)

        return targets if targets else None

    def _find_tests_by_import(self, changed_modules: set[str], work_dir: Path) -> list[str] | None:
        """Find test files that import changed modules."""
        import re

        targets = []
        test_dirs = ["tests", "test"]

        for test_dir_name in test_dirs:
            test_dir = work_dir / test_dir_name
            if not test_dir.exists():
                continue

            for test_file in test_dir.rglob("test_*.py"):
                try:
                    content = test_file.read_text(encoding="utf-8", errors="ignore")
                    for module in changed_modules:
                        module_name = module.replace("/", ".").replace(".py", "")
                        # Match import statements
                        pattern = r"(?:from|import)\s+" + re.escape(module_name.split(".")[0])
                        if re.search(pattern, content):
                            rel = str(test_file.relative_to(work_dir))
                            if rel not in targets:
                                targets.append(rel)
                            break
                except Exception:
                    continue

        return targets if targets else None

    # ------------------------------------------------------------------
    # P0: Redesign on test failure
    # ------------------------------------------------------------------

    def _tests_actually_failed(self, test_output: str) -> bool:
        """Check if tests actually failed (not just env errors)."""
        lowered = test_output.lower()
        # If it's purely an env issue, don't count as test failure
        if looks_like_environment_error(test_output):
            return False
        # Real test failures
        return "failed" in lowered or "error" in lowered or "exit code:" in lowered

    def _build_redesign_prompt(
        self,
        changed_files: list[str],
        review_result: str,
        test_result: str,
        work_dir: str,
    ) -> str:
        """Build explicit redesign instructions when tests fail (P0)."""
        test_errors = self._extract_test_errors(test_result)

        lines = [
            "🚨 TESTS FAILED — Your changes must be revised.",
            "",
            "=== Test Errors ===",
            test_errors,
            "",
        ]

        if review_result and "[Review" not in review_result:
            lines.extend([
                "=== Review Feedback ===",
                review_result[:2000],
                "",
            ])

        lines.extend([
            "=== Redesign Instructions ===",
            "1. Re-read the failing test and ALL code it exercises.",
            "2. Use Grep to find every call site of the function you changed.",
            "3. Identify the TRUE root cause. Your previous assumption may be wrong.",
            "4. Consider whether your fix introduced a regression or missed a call site.",
            "5. Produce a COMPLETELY REVISED fix.",
            "6. Run the tests again to confirm they pass before declaring completion.",
            "",
            "DO NOT simply tweak the previous patch. Reconsider from scratch.",
        ])

        return "\n".join(lines)

    def _extract_test_errors(self, test_output: str, max_chars: int = 4000) -> str:
        """Extract the most informative parts of test output for LLM feedback."""
        lines = test_output.split("\n")
        error_lines = []
        for line in lines:
            if any(k in line for k in ("FAIL:", "ERROR:", "Traceback", "AssertionError", "TypeError", "ValueError", "NameError")):
                error_lines.append(line)
        tail = "\n".join(lines[-100:])
        combined = "\n".join(error_lines) + "\n\n--- Tail of output ---\n" + tail
        if len(combined) > max_chars:
            combined = combined[:max_chars] + "\n[truncated]"
        return combined

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_review_content(self, changed_files: list[str], cwd: str) -> str:
        """Build review prompt content from changed files."""
        lines = [
            "Please review the following code changes.",
            "",
            "Changed files:",
        ]
        for f in changed_files:
            lines.append(f"  - {f}")
        lines.append("")

        diff = self._get_git_diff(cwd)
        if diff:
            lines.append("Git diff:")
            lines.append("```diff")
            lines.append(diff[:8000])
            lines.append("```")
        else:
            for f in changed_files:
                path = Path(cwd) / f
                if path.exists():
                    try:
                        content = path.read_text(encoding="utf-8")
                        lines.append(f"--- {f} ---")
                        lines.append(content[:4000])
                        lines.append("")
                    except Exception:
                        pass

        return "\n".join(lines)

    def _get_git_diff(self, cwd: str) -> str:
        """Get git diff for review context."""
        try:
            result = subprocess.run(
                ["git", "diff"],
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            if result.returncode == 0:
                return result.stdout
        except Exception:
            pass
        return ""

    def _has_issues(self, review_text: str) -> bool:
        """Heuristic: determine if review found issues."""
        lowered = review_text.lower()
        if "no issues" in lowered or "looks good" in lowered:
            return False
        issue_markers = [
            "bug", "error", "issue", "problem", "fix", "should be",
            "missing", "incorrect", "potential", "concern",
        ]
        return any(marker in lowered for marker in issue_markers)
