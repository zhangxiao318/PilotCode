"""Periodic Nudge — autonomous memory curation (Hermes-style).

Every N seconds (default 300s), the system reviews recent events and asks:
- Are there new user preferences worth recording?
- Any user corrections or clarifications?
- New project conventions or decisions?
- Lessons learned from errors or successes?

If nothing is worth recording, it returns silently.
Otherwise it stages memory updates via FastMemoryManager.

Design:
- Non-blocking: runs on asyncio background task
- Event-driven: collects events during the turn loop
- LLM-powered: uses a lightweight model to judge what deserves memory
- Configurable interval and thresholds
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

from .memory_dir import FastMemoryManager, FastMemoryUpdate


@dataclass
class NudgeEvent:
    """A single event captured during a turn for nudge review."""

    event_type: str  # "user_message" | "tool_call" | "error" | "correction" | "decision"
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class NudgeConfig:
    """Configuration for periodic nudge."""

    interval_seconds: float = 300.0  # 5 minutes
    max_events_per_nudge: int = 50
    min_events_before_nudge: int = 3
    enabled: bool = True
    # Memory targets
    enable_memory_md: bool = True
    enable_user_md: bool = True


class PeriodicNudge:
    """Periodic autonomous memory curation.

    Usage:
        nudge = PeriodicNudge(fast_memory_manager, llm_client)
        nudge.start()  # background task
        ...
        nudge.push_event(NudgeEvent("tool_call", "FileWrite src/foo.py"))
        ...
        nudge.stop()
    """

    def __init__(
        self,
        fast_memory: FastMemoryManager,
        llm_client: Any,
        config: NudgeConfig | None = None,
    ):
        self.fast_memory = fast_memory
        self.llm_client = llm_client
        self.config = config or NudgeConfig()
        self._events: list[NudgeEvent] = []
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._last_nudge_time: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background nudge task."""
        if not self.config.enabled or self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        """Stop the background nudge task."""
        if self._task is None:
            return
        self._stop_event.set()
        self._task.cancel()
        self._task = None

    async def _loop(self) -> None:
        """Main background loop."""
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.config.interval_seconds,
                )
            except asyncio.TimeoutError:
                await self._nudge()
            except asyncio.CancelledError:
                break

    # ------------------------------------------------------------------
    # Event collection
    # ------------------------------------------------------------------

    def push_event(self, event: NudgeEvent) -> None:
        """Push an event for potential memory extraction."""
        self._events.append(event)
        # Trim old events
        if len(self._events) > self.config.max_events_per_nudge * 2:
            self._events = self._events[-self.config.max_events_per_nudge :]

    def push_user_message(self, content: str) -> None:
        self.push_event(NudgeEvent("user_message", content))

    def push_tool_call(self, tool_name: str, params: dict[str, Any]) -> None:
        summary = f"{tool_name}({json.dumps(params, ensure_ascii=False)[:200]})"
        self.push_event(NudgeEvent("tool_call", summary, metadata={"tool": tool_name}))

    def push_error(self, error_text: str) -> None:
        self.push_event(NudgeEvent("error", error_text[:500]))

    def push_correction(self, original: str, corrected: str) -> None:
        self.push_event(
            NudgeEvent(
                "correction",
                f"Original: {original[:200]}\nCorrected: {corrected[:200]}",
            )
        )

    # ------------------------------------------------------------------
    # Nudge logic
    # ------------------------------------------------------------------

    async def _nudge(self) -> dict[str, Any]:
        """Execute one nudge cycle.

        Returns:
            Result dict with actions_taken, updates_staged, etc.
        """
        result: dict[str, Any] = {
            "ran_at": time.time(),
            "events_reviewed": 0,
            "actions_taken": 0,
            "updates_staged": 0,
            "consolidation_triggered": [],
        }

        # Capture and clear events atomically
        events = self._events.copy()
        self._events.clear()

        if len(events) < self.config.min_events_before_nudge:
            return result

        result["events_reviewed"] = len(events)

        # Build prompt
        prompt = self._build_nudge_prompt(events)

        try:
            response = await self.llm_client.complete(prompt)
        except Exception:
            return result

        if not response or response.strip().upper() == "NONE":
            return result

        # Parse structured updates
        updates = self._parse_nudge_response(response)

        for up in updates:
            if up.target in ("MEMORY.md", "USER.md"):
                self.fast_memory.stage_update(up)
                result["updates_staged"] += 1
            result["actions_taken"] += 1

        # Also check if consolidation is needed
        consolidation = self.fast_memory.check_consolidation()
        for fname, info in consolidation.items():
            if info.get("needed"):
                result["consolidation_triggered"].append(fname)

        self._last_nudge_time = time.time()
        return result

    def _build_nudge_prompt(self, events: list[NudgeEvent]) -> str:
        """Build the LLM prompt for nudge judgment."""
        lines: list[str] = []
        lines.append(
            "You are a memory curator. Review the recent events and decide "
            "if any new information should be recorded in the agent's memory."
        )
        lines.append("")
        lines.append("Consider:")
        lines.append("- New user preferences worth noting?")
        lines.append("- User corrections or clarifications?")
        lines.append("- Project conventions, decisions, or lessons learned?")
        lines.append("- Recurring errors or their fixes?")
        lines.append("")
        lines.append("Recent events:")

        for ev in events:
            ts = time.strftime("%H:%M:%S", time.localtime(ev.timestamp))
            content = ev.content.replace("\n", " ")
            lines.append(f"  [{ts}] {ev.event_type}: {content[:300]}")

        lines.append("")
        lines.append("If NOTHING is worth recording, reply with exactly: NONE")
        lines.append("")
        lines.append("Otherwise, reply with structured updates, one per line, in this format:")
        lines.append("  action: add|replace|remove")
        lines.append("  target: MEMORY.md|USER.md")
        lines.append("  key: <optional identifier for replace/remove>")
        lines.append("  content: <the memory text>")
        lines.append("  ---")
        lines.append("")
        lines.append("Example:")
        lines.append("  action: add")
        lines.append("  target: USER.md")
        lines.append("  key: language_preference")
        lines.append("  content: User prefers Chinese responses.")
        lines.append("  ---")
        lines.append("  action: add")
        lines.append("  target: MEMORY.md")
        lines.append("  key: ")
        lines.append("  content: Use pytest for all tests in this project.")
        lines.append("  ---")

        return "\n".join(lines)

    def _parse_nudge_response(self, response: str) -> list[FastMemoryUpdate]:
        """Parse the LLM response into FastMemoryUpdate objects."""
        updates: list[FastMemoryUpdate] = []

        # Split by --- separator
        blocks = response.split("---")
        for block in blocks:
            block = block.strip()
            if not block:
                continue

            action = ""
            target = ""
            key = None
            content = ""

            for line in block.splitlines():
                line = line.strip()
                if line.lower().startswith("action:"):
                    action = line.split(":", 1)[1].strip()
                elif line.lower().startswith("target:"):
                    target = line.split(":", 1)[1].strip()
                elif line.lower().startswith("key:"):
                    key = line.split(":", 1)[1].strip() or None
                elif line.lower().startswith("content:"):
                    content = line.split(":", 1)[1].strip()
                elif content:
                    # Multi-line content
                    content += "\n" + line

            if action and target and content:
                updates.append(
                    FastMemoryUpdate(
                        action=action,
                        target=target,
                        content=content,
                        key=key,
                    )
                )

        return updates

    def get_stats(self) -> dict[str, Any]:
        """Return nudge statistics."""
        return {
            "enabled": self.config.enabled,
            "interval_seconds": self.config.interval_seconds,
            "pending_events": len(self._events),
            "last_nudge_time": self._last_nudge_time,
            "running": self._task is not None and not self._task.done(),
        }
