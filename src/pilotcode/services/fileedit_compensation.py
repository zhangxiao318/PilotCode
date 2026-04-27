"""Shared FileEdit failure compensation tracker for all UI modes.

Bridges the gap between FileEdit's auto-degradation (fuzzy/line-level/block-level)
and framework-level guidance injection.  When the model's old_string is imprecise,
FileEdit may silently succeed via degradation without the model realising it was
close to failure.  This tracker detects both outright failures and degradation
usage, and injects guidance into the conversation to help the model improve its
next edit.

Lightweight persistence: stats are stored in AppState so they survive across
user queries within the same session.  When the failure rate crosses a threshold
the model is marked as persistently weak and every new query receives a常驻
FileEdit best-practice reminder in the system prompt.
"""

from __future__ import annotations


class FileEditCompensationTracker:
    """Tracks FileEdit outcomes across a single user query and injects hints.

    Usage:
        tracker = FileEditCompensationTracker(app_state=app_state)

        # Start of new user query
        tracker.reset()

        # After each tool execution
        hint = tracker.record_result(tool_name, exec_result.success, result_text)
        if hint:
            query_engine.messages.append(AssistantMessage(content=hint))
    """

    # Degradation markers that appear in successful FileEdit results when the
    # model's old_string was imprecise.
    _DEGRADATION_MARKERS: tuple[str, ...] = (
        "[FUZZY MATCH]",
        "[AUTO-DEGRADATION",
    )

    # Thresholds for persistent weak-model detection (lightweight version)
    _MIN_SAMPLES_FOR_PERSISTENT: int = 10
    _PERSISTENT_FAILURE_RATE: float = 0.30

    def __init__(self, app_state=None, shared_stats: dict | None = None) -> None:
        self._app_state = app_state
        self._shared_stats = shared_stats  # Optional server-level shared stats (e.g. WebSocket)

        # Per-query counters
        self.failure_streak: int = 0
        self.compensation_active: bool = False
        self._persistent_hint_injected_this_query: bool = False

        # Persistent (session-level) counters loaded from AppState
        self._load_persistent_stats()

    def _load_persistent_stats(self) -> None:
        """Load lifetime stats from shared ref or AppState."""
        # Prefer shared_stats (server-level, cross-session) over app_state
        if self._shared_stats is not None:
            stats = self._shared_stats
        elif self._app_state is not None:
            stats = getattr(self._app_state, "fileedit_stats", {}) or {}
        else:
            stats = {}

        self.lifetime_edits: int = stats.get("lifetime_edits", 0)
        self.lifetime_failures: int = stats.get("lifetime_failures", 0)
        self.lifetime_degradations: int = stats.get("lifetime_degradations", 0)
        self.persistent_weak: bool = stats.get("persistent_weak", False)

    def _save_persistent_stats(self) -> None:
        """Save lifetime stats back to AppState and optional shared ref."""
        stats = {
            "lifetime_edits": self.lifetime_edits,
            "lifetime_failures": self.lifetime_failures,
            "lifetime_degradations": self.lifetime_degradations,
            "persistent_weak": self.persistent_weak,
        }
        if self._app_state is not None:
            self._app_state.fileedit_stats = stats
        if self._shared_stats is not None:
            self._shared_stats.clear()
            self._shared_stats.update(stats)
        print(f"[FileEditStats] edits={self.lifetime_edits} failures={self.lifetime_failures} "
              f"degradations={self.lifetime_degradations} weak={self.persistent_weak}")

    @property
    def lifetime_failure_rate(self) -> float:
        """Return the session-level failure/degradation rate."""
        if self.lifetime_edits == 0:
            return 0.0
        return (self.lifetime_failures + self.lifetime_degradations) / self.lifetime_edits

    def reset(self) -> None:
        """Reset per-query counters at the start of a new user query.

        Persistent stats are NOT reset — they accumulate across queries.
        """
        self.failure_streak = 0
        self.compensation_active = False
        self._persistent_hint_injected_this_query = False

    def record_result(
        self,
        tool_name: str,
        success: bool,
        result_text: str,
    ) -> str | None:
        """Record a tool result and return a compensation hint if needed.

        Args:
            tool_name: Name of the tool that was executed.
            success: Whether the tool execution succeeded.
            result_text: The text returned to the model (may contain diff, error, etc.).

        Returns:
            A compensation hint string to inject into the conversation, or None.
        """
        if tool_name in ("FileEdit", "edit"):
            return self._handle_file_edit_result(success, result_text)

        # Successful write via alternative path resets the streak
        if tool_name in ("FileWrite", "ApplyPatch", "NotebookEdit") and success:
            self.failure_streak = 0
            self.compensation_active = False

        return None

    def _handle_file_edit_result(self, success: bool, result_text: str) -> str | None:
        """Handle FileEdit-specific result tracking."""
        is_outright_failure = not success or "String not found" in result_text
        used_degradation = any(m in result_text for m in self._DEGRADATION_MARKERS)

        # Update persistent counters first
        self.lifetime_edits += 1
        if is_outright_failure:
            self.lifetime_failures += 1
        elif used_degradation:
            self.lifetime_degradations += 1

        # Check if we should mark this model as persistently weak
        if (
            not self.persistent_weak
            and self.lifetime_edits >= self._MIN_SAMPLES_FOR_PERSISTENT
            and self.lifetime_failure_rate >= self._PERSISTENT_FAILURE_RATE
        ):
            self.persistent_weak = True

        self._save_persistent_stats()

        # --- Per-query real-time compensation ---
        if is_outright_failure or used_degradation:
            self.failure_streak += 1
            if self.failure_streak >= 2 and not self.compensation_active:
                self.compensation_active = True
                return self._build_realtime_hint()
        else:
            # Clean success — reset per-query state
            self.failure_streak = 0
            self.compensation_active = False

        # --- Persistent weak-model compensation ---
        # If the model is known to be weak, inject the hint once per query
        if self.persistent_weak and not self._persistent_hint_injected_this_query:
            self._persistent_hint_injected_this_query = True
            return self._build_persistent_hint()

        return None

    @staticmethod
    def _build_realtime_hint() -> str:
        """Hint injected when the model fails twice within a single query."""
        return (
            "[FRAMEWORK HINT] You have had multiple FileEdit failures or near-misses in a row.\n"
            "To improve success rate, follow this protocol:\n"
            "1. STOP trying FileEdit immediately on the same file.\n"
            "2. Use SmartEditPlanner to create a precise edit checklist for the pattern you want to change.\n"
            "3. Re-read the target file with FileRead to get the EXACT current text.\n"
            "4. Pay attention to indentation (spaces vs tabs) — copy the exact whitespace.\n"
            "5. Make exactly ONE small change per FileEdit call.\n"
            "6. If the file is small (< 30 lines), consider using FileWrite instead.\n"
            "7. After editing, verify syntax with the appropriate tool (e.g. py_compile for .py, gcc -fsyntax-only for .c, etc.)."
        )

    @staticmethod
    def _build_persistent_hint() -> str:
        """常驻 hint for models that have demonstrated weak FileEdit precision."""
        return (
            "[FRAMEWORK HINT — PERSISTENT] This session has observed multiple FileEdit "
            "difficulties. To maximise success:\n"
            "1. ALWAYS re-read the target file with FileRead before each edit.\n"
            "2. Copy the EXACT text including all spaces/tabs/newlines.\n"
            "3. Make exactly ONE atomic change per FileEdit call.\n"
            "4. If FileEdit fails once, switch to SmartEditPlanner or FileWrite for small files.\n"
            "5. After editing, verify syntax when possible (e.g. py_compile for Python, compiler check for C/C++, linter for JS/TS)."
        )
