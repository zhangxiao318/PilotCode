"""Human-readable report generation for P-EVR orchestration."""

from __future__ import annotations

from typing import Any, Callable

from .task_spec import Mission
from .tracker import MissionSnapshot


def format_plan(mission: Mission) -> str:
    """Generate a startup report showing the mission plan.

    Example output:
        📋 Mission: Implement OAuth2
        ├── Phase 1: Setup (2 tasks)
        │   ├── [1] Create user model
        │   └── [2] Add password hashing
        ├── Phase 2: API (3 tasks)
        │   ├── [1] Implement token endpoint
        │   ├── [2] Add refresh token logic
        │   └── [3] Write tests
        └── Phase 3: Integration (1 tasks)
            └── [1] Wire into main app
    """
    lines: list[str] = [f"📋 Mission: {mission.title}"]

    total_tasks = len(mission.all_tasks())
    lines.append(f"   Total: {total_tasks} tasks across {len(mission.phases)} phases")
    lines.append("")

    for pi, phase in enumerate(mission.phases, 1):
        is_last_phase = pi == len(mission.phases)
        phase_connector = "└──" if is_last_phase else "├──"
        lines.append(f"{phase_connector} Phase {pi}: {phase.title} ({len(phase.tasks)} tasks)")

        for ti, task in enumerate(phase.tasks, 1):
            is_last_task = ti == len(phase.tasks)
            if is_last_phase:
                task_connector = "    ├──" if not is_last_task else "    └──"
            else:
                task_connector = "│   ├──" if not is_last_task else "│   └──"

            lines.append(f"{task_connector} [{ti}] {task.title}")

            if task.dependencies:
                if is_last_phase:
                    dep_connector = "    │   " if not is_last_task else "        "
                else:
                    dep_connector = "│   │   " if not is_last_task else "│       "
                lines.append(f"{dep_connector}(depends on: {', '.join(task.dependencies)})")

    return "\n".join(lines)


_STATE_EMOJI: dict[str, str] = {
    "pending": "⏸️",
    "assigned": "📋",
    "in_progress": "🔄",
    "submitted": "📤",
    "under_review": "🔍",
    "verified": "✅",
    "rejected": "❌",
    "needs_rework": "🔄",
    "done": "✅",
    "blocked": "⏸️",
    "cancelled": "🚫",
}


def format_progress(snapshot: MissionSnapshot) -> str:
    """Generate a progress update.

    Example:
        ⏳ Progress: 3/8 tasks completed (38%)
        Status: running
        In progress: 1 | Blocked: 1 | Ready: 2

        ✅ task_1: DONE
        🔄 task_2: IN_PROGRESS
        ⏸️ task_3: BLOCKED
    """
    lines: list[str] = []
    total = snapshot.total_tasks
    completed = snapshot.completed_tasks
    pct = (completed / total * 100) if total > 0 else 0.0

    lines.append(f"⏳ Progress: {completed}/{total} tasks completed ({pct:.0f}%)")
    lines.append(f"   Status: {snapshot.status}")
    lines.append(
        f"   In progress: {snapshot.in_progress_tasks} "
        f"| Blocked: {snapshot.blocked_tasks} "
        f"| Ready: {snapshot.ready_tasks}"
    )
    lines.append("")

    for task_id, state in snapshot.task_states.items():
        emoji = _STATE_EMOJI.get(state, "❓")
        lines.append(f"{emoji} {task_id}: {state.upper()}")

    return "\n".join(lines)


def format_completion(result: dict[str, Any]) -> str:
    """Generate a completion summary.

    Shows all completed tasks, any failures, and aggregate counts.
    """
    lines: list[str] = ["🏁 Mission Complete", ""]

    snapshot = result.get("snapshot", {})
    mission_id = result.get("mission_id", "unknown")
    total = snapshot.get("total_tasks", 0)
    completed = snapshot.get("completed_tasks", 0)
    failed = snapshot.get("failed_tasks", 0)
    verified = snapshot.get("verified_tasks", 0)

    lines.append(f"Mission ID: {mission_id}")
    lines.append(f"Total tasks: {total}")
    lines.append(f"Completed:   {completed}")
    lines.append(f"Verified:    {verified}")
    lines.append(f"Failed:      {failed}")

    task_states = snapshot.get("task_states", {})
    failed_tasks = [tid for tid, st in task_states.items() if st in ("rejected", "cancelled")]
    if failed_tasks:
        lines.append("")
        lines.append("Failed tasks:")
        for tid in failed_tasks:
            lines.append(f"  - {tid}")

    # Include warnings (non-blocking verification issues)
    warnings = result.get("warnings", [])
    if warnings:
        lines.append("")
        lines.append("=" * 40)
        lines.append("⚠️  Warnings (non-blocking)")
        lines.append("=" * 40)
        for w in warnings:
            lines.append(
                f"  [{w.get('task_id', '?')}] L{w.get('level', '?')} {w.get('category', '?')}: {w.get('message', '')}"
            )
        lines.append("")
        lines.append("These warnings do not affect task completion but suggest improvements.")

    # Include task outputs
    task_outputs = result.get("task_outputs", {})
    if task_outputs:
        lines.append("")
        lines.append("=" * 40)
        lines.append("📊 Task Results")
        lines.append("=" * 40)
        for tid, tdata in task_outputs.items():
            title = tdata.get("title", tid)
            output = tdata.get("output", "")
            lines.append("")
            lines.append(f"--- {title} ---")
            # Truncate very long outputs for display
            output_str = str(output) if output else "(no output)"
            if len(output_str) > 2000:
                output_str = output_str[:2000] + "\n... [truncated]"
            lines.append(output_str)

    return "\n".join(lines)


def format_failure(result: dict[str, Any], reason: str = "") -> str:
    """Generate a failure explanation.

    Explains why the mission could not complete and which tasks failed.
    """
    lines: list[str] = ["❌ Mission Failed"]
    if reason:
        lines.append(f"Reason: {reason}")
    lines.append("")

    snapshot = result.get("snapshot", {})
    mission_id = result.get("mission_id", "unknown")
    total = snapshot.get("total_tasks", 0)
    completed = snapshot.get("completed_tasks", 0)
    failed = snapshot.get("failed_tasks", 0)

    lines.append(f"Mission ID: {mission_id}")
    lines.append(f"Completed: {completed}/{total}")
    lines.append(f"Failed:    {failed}")

    task_states = snapshot.get("task_states", {})
    problematic = [
        tid for tid, st in task_states.items() if st in ("rejected", "cancelled", "needs_rework")
    ]
    if problematic:
        lines.append("")
        lines.append("Problematic tasks:")
        for tid in problematic:
            lines.append(f"  - {tid} ({task_states[tid]})")
    else:
        lines.append("No individual task failures recorded.")

    return "\n".join(lines)


_EVENT_FORMATTERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "mission:started": lambda d: (
        f"🚀 Mission started: {d.get('mission_id', '')} " f"({d.get('total_tasks', 0)} tasks)"
    ),
    "mission:planned": lambda d: (f"📋 Mission planned: {d.get('title', d.get('mission_id', ''))}"),
    "mission:completed": lambda d: "🏁 Mission completed",
    "mission:cancelled": lambda d: f"🚫 Mission cancelled: {d.get('mission_id', '')}",
    "mission:blocked": lambda d: (f"⏸️ Mission blocked: {d.get('blocked_count', 0)} tasks"),
    "task:started": lambda d: (f"🔄 Started: {d.get('task_id', '')} - {d.get('title', '')}"),
    "task:submitted": lambda d: (
        f"📤 Submitted: {d.get('task_id', '')} " f"(success={d.get('success', False)})"
    ),
    "task:verified": lambda d: f"✅ Verified: {d.get('task_id', '')}",
    "task:rejected": lambda d: (
        f"❌ Rejected: {d.get('task_id', '')} (L{d.get('level', 0)})" f" - {d.get('feedback', '')}"
    ),
    "task:needs_rework": lambda d: (
        f"🔄 Needs rework: {d.get('task_id', '')} (L{d.get('level', 0)})"
        f" - {d.get('feedback', '')}"
    ),
    "task:state_changed": lambda d: (
        f"📊 {d.get('task_id', '')}: {d.get('from', '')} → {d.get('to', '')}"
    ),
}


def format_task_event(event_type: str, data: dict[str, Any]) -> str:
    """Format a single progress event for real-time display.

    Supports event types such as "mission:started", "task:started",
    "task:verified", etc. Unknown events are rendered generically.
    """
    formatter = _EVENT_FORMATTERS.get(event_type)
    if formatter is not None:
        return formatter(data)
    return f"📡 {event_type}: {data}"
