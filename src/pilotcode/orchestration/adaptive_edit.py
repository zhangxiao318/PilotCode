"""Adaptive edit strategy and validation for weak models.

Translates ModelCapability scores into concrete editing behavior via
AdaptiveOrchestratorConfig. This module provides:
- Post-edit auto-verification (syntax + completeness checks)
- Worker prompt injection based on compensation level
- Continue prompt enrichment with validation results
"""

from __future__ import annotations

import py_compile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pilotcode.model_capability.adaptive_config import AdaptiveOrchestratorConfig
from pilotcode.model_capability.schema import ModelCapability

# ---------------------------------------------------------------------------
# Edit Validator
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Result of post-edit validation."""

    passed: bool
    syntax_ok: bool
    completeness_ok: bool
    old_pattern_remaining: list[tuple[str, int, str]]  # (file, line, snippet)
    errors: list[str]
    nudge_message: str = ""
    knowhow_matches: list[Any] = field(default_factory=list)
    knowhow_auto_fixed: bool = False


class EditValidator:
    """Validates edits after they are made.

    Checks:
    1. Python syntax (py_compile)
    2. Completeness (searches for old pattern still present in changed files)
    3. Known weak-model mistakes (Knowhow library)
    4. Suggests next actions if incomplete
    """

    @staticmethod
    def validate_syntax(file_path: str) -> tuple[bool, str | None]:
        """Check Python syntax. Returns (ok, error_or_none)."""
        if not file_path.endswith(".py"):
            return True, None
        try:
            py_compile.compile(file_path, doraise=True)
            return True, None
        except py_compile.PyCompileError as exc:
            return False, str(exc)

    @staticmethod
    def check_completeness(
        changed_files: list[str],
        expected_pattern: str,
        cwd: str = ".",
    ) -> list[tuple[str, int, str]]:
        """Check if expected_pattern still exists in changed files.

        Returns list of (file_path, line_number, snippet) for each remaining occurrence.
        """
        remaining: list[tuple[str, int, str]] = []
        for fp in changed_files:
            path = Path(fp)
            if not path.is_absolute():
                path = Path(cwd) / path
            if not path.exists():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            for lineno, line in enumerate(content.splitlines(), start=1):
                if expected_pattern in line:
                    snippet = line.strip()[:120]
                    remaining.append((str(path), lineno, snippet))
        return remaining

    @staticmethod
    def validate(
        changed_files: list[str],
        expected_pattern: str | None = None,
        cwd: str = ".",
    ) -> ValidationResult:
        """Run full validation suite."""
        errors: list[str] = []
        syntax_ok = True
        knowhow_matches: list[Any] = []
        knowhow_auto_fixed = False

        for fp in changed_files:
            path = Path(fp)
            if not path.is_absolute():
                path = Path(cwd) / path
            if path.suffix == ".py":
                ok, err = EditValidator.validate_syntax(str(path))
                if not ok:
                    syntax_ok = False
                    errors.append(f"Syntax error in {fp}: {err}")

                # --- Knowhow check: scan for known weak-model mistakes ---
                from pilotcode.services.knowhow import get_knowhow_library

                lib = get_knowhow_library()
                file_matches = lib.check_file(str(path))
                if file_matches:
                    # Try auto-fix
                    source = path.read_text(encoding="utf-8", errors="replace")
                    fixed_source = lib.apply_auto_fixes(source, file_matches)
                    if fixed_source != source:
                        path.write_text(fixed_source, encoding="utf-8")
                        knowhow_auto_fixed = True
                        # Re-check syntax after auto-fix
                        ok2, err2 = EditValidator.validate_syntax(str(path))
                        if not ok2:
                            syntax_ok = False
                            errors.append(f"Syntax error after knowhow auto-fix in {fp}: {err2}")
                        else:
                            # Auto-fix resolved the issue, downgrade to info
                            for m in file_matches:
                                m.severity = "info"
                    knowhow_matches.extend(file_matches)

        old_pattern_remaining: list[tuple[str, int, str]] = []
        if expected_pattern:
            old_pattern_remaining = EditValidator.check_completeness(
                changed_files, expected_pattern, cwd
            )

        completeness_ok = len(old_pattern_remaining) == 0
        passed = (
            syntax_ok
            and completeness_ok
            and not any(m.severity == "error" for m in knowhow_matches)
        )

        nudge_lines: list[str] = []
        if not syntax_ok:
            nudge_lines.append(
                "CRITICAL: Your last edit introduced a syntax error. "
                "The change has been rolled back. Please fix the syntax before retrying."
            )
        elif not completeness_ok:
            nudge_lines.append(
                "INCOMPLETE: The following occurrences of the old pattern still remain:"
            )
            for fp, ln, snippet in old_pattern_remaining[:5]:
                nudge_lines.append(f"  - {fp}:{ln}  {snippet}")
            if len(old_pattern_remaining) > 5:
                nudge_lines.append(f"  ... and {len(old_pattern_remaining) - 5} more occurrences")
            nudge_lines.append(
                "Please apply FileEdit to each remaining location using the exact file content."
            )

        if knowhow_matches:
            nudge_lines.append("")
            nudge_lines.append("[FRAMEWORK KNOWHOW CHECK] Known weak-model patterns detected:")
            for m in knowhow_matches:
                prefix = (
                    "🔧 FIXED"
                    if m.severity == "info" and knowhow_auto_fixed
                    else m.severity.upper()
                )
                nudge_lines.append(
                    f"  [{prefix}] {m.name} at line {m.line_number}: {m.description}"
                )
                if m.auto_fix and not knowhow_auto_fixed:
                    nudge_lines.append(
                        f"    Suggested fix: replace '{m.matched_text}' with '{m.auto_fix}'"
                    )
            if knowhow_auto_fixed:
                nudge_lines.append(
                    "The framework has auto-corrected these issues. Please verify the result."
                )
            else:
                nudge_lines.append("Please fix these issues before proceeding.")

        return ValidationResult(
            passed=passed,
            syntax_ok=syntax_ok,
            completeness_ok=completeness_ok,
            old_pattern_remaining=old_pattern_remaining,
            errors=errors,
            nudge_message="\n".join(nudge_lines),
            knowhow_matches=knowhow_matches,
            knowhow_auto_fixed=knowhow_auto_fixed,
        )


# ---------------------------------------------------------------------------
# Compensation Engine
# ---------------------------------------------------------------------------


class CompensationEngine:
    """Generates prompts and guidance based on adaptive config.

    Bridges AdaptiveOrchestratorConfig (produced by AdaptiveConfigMapper)
    with concrete runtime behavior in MissionAdapter.
    """

    def __init__(self, config: AdaptiveOrchestratorConfig, capability: ModelCapability) -> None:
        self.config = config
        self.capability = capability

    @property
    def is_compensation_active(self) -> bool:
        """True when any compensation mechanism is enabled."""
        return (
            self.config.enable_auto_verify
            or self.config.enable_smart_edit_planner
            or self.config.ask_user_on_critical_decisions
            or self.config.task_granularity.value == "fine"
        )

    def get_worker_prompt_suffix(self) -> str:
        """Return a prompt section injected into the worker system prompt."""
        if not self.is_compensation_active:
            return ""

        parts: list[str] = ["\n[COMPENSATION PROTOCOL — FRAMEWORK-ASSISTED MODE]"]

        if self.config.enable_smart_edit_planner:
            parts.append(
                "1. BEFORE multi-file edits: Call SmartEditPlanner to get a checklist "
                "of every location that needs updating."
            )

        if self.config.max_edits_per_round <= 1:
            parts.append(
                "2. Make exactly ONE atomic edit per tool call. " "Never batch unrelated changes."
            )
        elif self.config.max_edits_per_round <= 3:
            parts.append(
                "2. Prefer atomic edits (one logical change per FileEdit call). "
                "Group only tightly related changes."
            )

        if self.config.enable_auto_verify:
            parts.append(
                "3. The framework will auto-verify your edits. Wait for verification "
                "results before proceeding."
            )

        if self.config.verify_after_each_edit:
            parts.append(
                "4. After EVERY edit, the framework checks for syntax errors and "
                "incomplete changes. Fix any reported issues immediately."
            )

        if self.config.ask_user_on_critical_decisions:
            parts.append(
                "5. On critical decisions (deleting files, changing APIs, breaking changes), "
                "use AskUser to confirm before proceeding."
            )

        if self.config.enforce_test_before_mark_complete:
            parts.append(
                "6. You MUST run tests and confirm they pass before marking a task complete."
            )

        if self.config.task_granularity.value == "fine":
            parts.append(
                "7. Tasks are intentionally granular. Focus on ONE small change at a time. "
                "Do not try to optimize or refactor beyond the stated objective."
            )

        if self.config.json_retry_on_failure and not self.config.require_json_schema:
            parts.append(
                "8. When outputting structured data, prefer plain text over JSON. "
                "If JSON is required, the framework will validate and retry for you."
            )

        return "\n".join(parts)

    def get_planning_prompt_suffix(self) -> str:
        """Additional guidance injected into the mission planner prompt."""
        if self.config.task_granularity.value != "fine":
            return ""

        return (
            "\n[PLANNING COMPENSATION]\n"
            "This model has limited planning capability. Generate VERY granular tasks:\n"
            "- Each task should change at most 1-2 files\n"
            "- Each task should be 30-80 lines of code\n"
            "- Avoid complex dependency chains\n"
            "- Use TEMPLATE-BASED planning when possible\n"
        )

    def get_edit_summary_for_continue_prompt(self, pending_checklist: list[dict] | None) -> str:
        """Generate a concise reminder for the continue prompt."""
        if not pending_checklist:
            return ""
        lines = [f"\n[EDIT CHECKLIST] {len(pending_checklist)} items remaining:"]
        for item in pending_checklist[:5]:
            fp = item.get("file_path", "?")
            ln = item.get("line_number", "?")
            ctx = item.get("context", "")[:60]
            lines.append(f"  - {fp}:{ln} — {ctx}")
        if len(pending_checklist) > 5:
            lines.append(f"  ... and {len(pending_checklist) - 5} more")
        return "\n".join(lines)
