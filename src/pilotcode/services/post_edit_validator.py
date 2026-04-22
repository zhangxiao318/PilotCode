"""Post-edit validation: auto-review and test after code changes."""

import os
import subprocess
from pathlib import Path
from typing import Any

from ..utils.model_client import ModelClient, Message


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
        self._test_framework_cache: str | None = None

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
            }
        """
        work_dir = cwd or str(os.getcwd())

        # --- Review ---
        review_result = await self.review_changes(changed_files, work_dir)
        issues_found = self._has_issues(review_result)

        # --- Test ---
        framework = self.detect_test_framework(work_dir)
        if framework:
            test_result = await self.run_tests(framework, work_dir)
            test_env_ready = True
            if "passed" not in test_result.lower() and "error" not in test_result.lower():
                issues_found = issues_found or ("failed" in test_result.lower())
        else:
            test_result = (
                "NO_TEST_ENV: No test framework detected. "
                "Looked for pytest, npm test, cargo test, go test, gradle, maven. "
                "If you'd like to run tests, install a test framework first."
            )
            test_env_ready = False

        return {
            "review_result": review_result,
            "test_result": test_result,
            "test_env_ready": test_env_ready,
            "issues_found": issues_found,
        }

    async def review_changes(self, changed_files: list[str], cwd: str) -> str:
        """Run reviewer LLM on changed files."""
        if not self._model_client:
            return "[Review skipped: no model client configured]"

        # Build diff or file content for review
        review_content = self._build_review_content(changed_files, cwd)

        messages = [
            Message(role="system", content=_REVIEWER_SYSTEM_PROMPT),
            Message(role="user", content=review_content),
        ]

        # Non-streaming call: collect all chunks
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

    def detect_test_framework(self, cwd: str | None = None) -> str | None:
        """Detect available test framework in the project."""
        if self._test_framework_cache is not None:
            return self._test_framework_cache

        work_dir = Path(cwd or os.getcwd())

        for framework_name, markers, command in _TEST_FRAMEWORKS:
            for marker in markers:
                marker_path = work_dir / marker
                if marker_path.exists():
                    self._test_framework_cache = command
                    return command

        self._test_framework_cache = None
        return None

    async def run_tests(self, command: str, cwd: str | None = None) -> str:
        """Run tests and return output."""
        work_dir = cwd or str(os.getcwd())

        try:
            result = subprocess.run(
                command,
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

        # Include git diff if available
        diff = self._get_git_diff(cwd)
        if diff:
            lines.append("Git diff:")
            lines.append("```diff")
            lines.append(diff[:8000])  # Limit diff size
            lines.append("```")
        else:
            # Fallback: read each changed file directly
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
        # If review explicitly says "no issues" or "looks good", no issues
        if "no issues" in lowered or "looks good" in lowered:
            return False
        # If review contains common issue markers, there are issues
        issue_markers = [
            "bug", "error", "issue", "problem", "fix", "should be",
            "missing", "incorrect", "potential", "concern",
        ]
        return any(marker in lowered for marker in issue_markers)
