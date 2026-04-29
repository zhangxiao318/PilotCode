"""Quest command for autonomous development.

Quest Mode allows PilotCode to autonomously execute multi-phase development
tasks: requirement parsing → mission execution → verification & summary.

Usage:
  /quest "<description>"          Start a new quest
  /quest status [#id]             Show quest progress
  /quest pause [#id]              Pause running quest
  /quest resume [#id]             Resume paused quest
  /quest cancel [#id]             Cancel quest
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from rich.console import Console
from rich.markdown import Markdown

from .base import CommandHandler, register_command, CommandContext
from ..utils.model_client import get_model_client, Message


@dataclass
class QuestPhase:
    """A phase within a quest."""

    name: str
    status: str = "pending"  # pending | running | done | failed
    result: str = ""
    missions: list[dict] = field(default_factory=list)


@dataclass
class QuestState:
    """State of a single quest."""

    id: int
    description: str
    status: str = "pending"  # pending | running | paused | completed | failed
    phases: list[QuestPhase] = field(default_factory=list)
    current_phase: int = 0
    token_used: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    error: str = ""
    result_summary: str = ""


# Global quest store (in-memory; not persisted across restarts)
_quests: dict[int, QuestState] = {}
_next_quest_id: int = 1
_quest_lock = asyncio.Lock()


async def quest_command(args: list[str], context: CommandContext) -> str:
    """Handle /quest command."""
    global _next_quest_id

    if not args:
        if not _quests:
            return (
                "No active quests.\n"
                "  /quest \"<description>\"     → Start autonomous development quest\n"
                "  /quest status [#id]          → Show quest progress\n"
                "  /quest pause [#id]           → Pause running quest\n"
                "  /quest resume [#id]          → Resume paused quest\n"
                "  /quest cancel [#id]          → Cancel quest"
            )
        lines = ["Active Quests:", ""]
        for q in sorted(_quests.values(), key=lambda x: x.id):
            icon = {
                "running": "▶",
                "paused": "⏸",
                "completed": "✅",
                "failed": "❌",
                "pending": "○",
            }.get(q.status, "?")
            desc = q.description[:40] + "..." if len(q.description) > 40 else q.description
            elapsed = ""
            if q.completed_at:
                elapsed = f" ({(q.completed_at - q.created_at).total_seconds():.0f}s)"
            lines.append(f"  {icon} #{q.id}: {desc} [{q.status}]{elapsed}")
        return "\n".join(lines)

    action = args[0]

    if action == "status":
        qid = _resolve_qid(args)
        if qid is None or qid not in _quests:
            return "No quest found."
        return _format_quest_status(_quests[qid])

    if action in ("pause", "resume", "cancel"):
        qid = _resolve_qid(args)
        if qid is None or qid not in _quests:
            return "No quest found."
        q = _quests[qid]
        if action == "pause":
            if q.status != "running":
                return f"Quest #{qid} is not running (status: {q.status})."
            q.status = "paused"
            return f"Quest #{qid} paused. Resume with /quest resume #{qid}"
        elif action == "resume":
            if q.status != "paused":
                return f"Quest #{qid} is not paused (status: {q.status})."
            asyncio.create_task(_run_quest(q, context))
            return f"Quest #{qid} resuming..."
        else:  # cancel
            del _quests[qid]
            return f"Quest #{qid} cancelled."

    # Default: start new quest
    description = " ".join(args)
    async with _quest_lock:
        quest = QuestState(id=_next_quest_id, description=description)
        _quests[quest.id] = quest
        _next_quest_id += 1

    asyncio.create_task(_run_quest(quest, context))
    return (
        f"🚀 Quest #{quest.id} started: {description}\n"
        f"Use /quest status #{quest.id} to track progress."
    )


def _resolve_qid(args: list[str]) -> int | None:
    """Resolve quest ID from command args."""
    if len(args) > 1:
        try:
            return int(args[1].lstrip("#"))
        except ValueError:
            return None
    if _quests:
        # Prefer running/paused quests, then fall back to most recent
        candidates = [q for q in _quests.values() if q.status in ("running", "paused")]
        if candidates:
            return max(candidates, key=lambda q: q.id).id
        return max(_quests.keys())
    return None


def _format_quest_status(q: QuestState) -> str:
    """Format quest status for display."""
    lines = [
        f"Quest #{q.id}: {q.description}",
        f"Status: {q.status} | Started: {q.created_at.strftime('%H:%M:%S')}",
    ]
    if q.completed_at:
        duration = (q.completed_at - q.created_at).total_seconds()
        lines.append(f"Duration: {duration:.1f}s")
    if q.token_used > 0:
        lines.append(f"Tokens: ~{q.token_used:,}")
    if q.error:
        lines.append(f"Error: {q.error}")
    lines.append("")

    for i, ph in enumerate(q.phases, 1):
        icon = {
            "done": "✅",
            "running": "▶",
            "failed": "❌",
            "pending": "○",
        }.get(ph.status, "?")
        lines.append(f"  {icon} Phase {i}: {ph.name}")
        if ph.result:
            lines.append(f"      └─ {ph.result}")
        for mi, m in enumerate(ph.missions[:5], 1):
            success = m.get("success") if isinstance(m, dict) else False
            title = ""
            if isinstance(m, dict):
                if "mission" in m and isinstance(m["mission"], dict):
                    title = m["mission"].get("title", "")
                elif "title" in m:
                    title = m["title"]
            icon_m = "✓" if success else "✗"
            lines.append(f"        {icon_m} Mission {mi}: {title or 'unnamed'}")
        if len(ph.missions) > 5:
            lines.append(f"        ... and {len(ph.missions) - 5} more")
    lines.append("")

    if q.result_summary:
        lines.append("Result:")
        lines.append(q.result_summary)

    return "\n".join(lines)


async def _run_quest(quest: QuestState, context: CommandContext) -> None:
    """Execute quest phases. Resumable from any phase."""
    console = Console()

    try:
        quest.status = "running"

        # ── Phase 1: Requirement parsing ───────────────────────────────
        if not quest.phases or quest.phases[0].status == "pending":
            if not quest.phases:
                quest.phases.append(QuestPhase(name="需求解析", status="running"))
            else:
                quest.phases[0].status = "running"

            console.print(f"\n[cyan dim][Quest #{quest.id}][/cyan dim] Phase 1/3: 需求解析...")
            missions = await _parse_requirement(quest.description, context)
            quest.phases[0].status = "done"
            quest.phases[0].result = f"拆解为 {len(missions)} 个 missions"
            quest.phases[0].missions = missions
            quest.current_phase = 1

        if quest.status == "paused":
            console.print(f"[yellow dim][Quest #{quest.id}] Paused.[/yellow dim]")
            return

        # ── Phase 2: Mission execution ─────────────────────────────────
        if len(quest.phases) < 2 or quest.phases[1].status in ("pending", "running"):
            if len(quest.phases) < 2:
                quest.phases.append(QuestPhase(name="Mission 执行", status="running"))
            else:
                quest.phases[1].status = "running"

            missions = quest.phases[0].missions if quest.phases else []
            if not missions:
                missions = [
                    {
                        "title": quest.description,
                        "description": quest.description,
                        "type": "code",
                        "estimated_complexity": "moderate",
                    }
                ]

            console.print(
                f"[cyan dim][Quest #{quest.id}][/cyan dim] Phase 2/3: 执行 {len(missions)} 个 missions..."
            )

            existing_results = (
                quest.phases[1].missions if len(quest.phases) > 1 and quest.phases[1].missions else []
            )
            start_idx = len(existing_results)

            for i, mission in enumerate(missions[start_idx:], start_idx + 1):
                if quest.status == "paused":
                    console.print(
                        f"[yellow dim][Quest #{quest.id}] Paused after mission {i - 1}/{len(missions)}.[/yellow dim]"
                    )
                    return

                title = mission.get("title", "unnamed")
                console.print(f"[dim]  ├─ Mission {i}/{len(missions)}: {title}[/dim]")

                try:
                    result = await _execute_mission(mission, context, quest)
                    quest.phases[1].missions.append(
                        {
                            "mission": mission,
                            "result": result,
                            "success": result.get("success", False),
                        }
                    )

                    if result.get("success"):
                        console.print(f"[green dim]  │  └─ ✓ Completed[/green dim]")
                    else:
                        error = result.get("error", "unknown")
                        error_str = str(error)[:60] + "..." if len(str(error)) > 60 else str(error)
                        console.print(f"[red dim]  │  └─ ✗ Failed: {error_str}[/red dim]")
                except Exception as e:
                    quest.phases[1].missions.append(
                        {
                            "mission": mission,
                            "result": {"error": str(e)},
                            "success": False,
                        }
                    )
                    console.print(f"[red dim]  │  └─ ✗ Error: {e}[/red dim]")

            success_count = sum(1 for m in quest.phases[1].missions if m.get("success"))
            quest.phases[1].status = "done"
            quest.phases[1].result = f"{success_count}/{len(missions)} missions succeeded"
            quest.current_phase = 2

        if quest.status == "paused":
            console.print(f"[yellow dim][Quest #{quest.id}] Paused.[/yellow dim]")
            return

        # ── Phase 3: Verification & summary ────────────────────────────
        if len(quest.phases) < 3 or quest.phases[2].status == "pending":
            if len(quest.phases) < 3:
                quest.phases.append(QuestPhase(name="验证汇总", status="running"))
            else:
                quest.phases[2].status = "running"

            console.print(f"[cyan dim][Quest #{quest.id}][/cyan dim] Phase 3/3: 验证与汇总...")

            missions_data = quest.phases[0].missions if quest.phases else []
            results_data = (
                [m["result"] for m in quest.phases[1].missions]
                if len(quest.phases) > 1
                else []
            )

            summary = _generate_summary(quest.description, missions_data, results_data)
            quest.phases[2].status = "done"
            quest.phases[2].result = "验证完成"
            quest.result_summary = summary

        quest.status = "completed"
        quest.completed_at = datetime.now()
        console.print(f"\n[green bold]✅ Quest #{quest.id} completed![/green bold]")
        if quest.result_summary:
            console.print(Markdown(quest.result_summary))

    except Exception as e:
        quest.status = "failed"
        quest.error = str(e)
        console.print(f"\n[red bold]❌ Quest #{quest.id} failed: {e}[/red bold]")


async def _parse_requirement(description: str, context: CommandContext) -> list[dict]:
    """Use LLM to parse vague requirement into structured missions."""
    client = get_model_client()

    system_prompt = (
        "You are a task decomposition engine. Break down a user's development request "
        "into a list of concrete, executable missions.\n\n"
        "Each mission must have:\n"
        "- title: short description (max 10 words)\n"
        "- description: detailed task description (what to do, files to touch, expected outcome)\n"
        "- type: one of [code, test, refactor, explore, config, doc]\n"
        "- estimated_complexity: one of [simple, moderate, complex]\n\n"
        "Output ONLY a valid JSON array. No markdown code fences, no explanation, just raw JSON."
    )

    user_prompt = (
        f"Break down this development request into executable missions.\n\n"
        f"Request: {description}\n"
        f"Working directory: {context.cwd}\n\n"
        f"Output format (JSON array):\n"
        f'[{{"title": "...", "description": "...", "type": "code", "estimated_complexity": "moderate"}}]'
    )

    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_prompt),
    ]

    response_text = ""
    async for chunk in client.chat_completion(
        messages=messages, tools=None, temperature=0.2, stream=False
    ):
        # Handle both streaming and non-streaming response shapes
        choice = chunk.get("choices", [{}])[0]
        delta = choice.get("delta", {})
        content = delta.get("content", "")
        if not content:
            message = choice.get("message", {})
            content = message.get("content", "")
        if content:
            response_text += content

    text = response_text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        missions = json.loads(text)
        if not isinstance(missions, list):
            missions = [missions] if isinstance(missions, dict) else []
        valid = [m for m in missions if isinstance(m, dict) and "title" in m]
        return valid if valid else _fallback_missions(description)
    except (json.JSONDecodeError, Exception):
        return _fallback_missions(description)


def _fallback_missions(description: str) -> list[dict]:
    """Fallback single mission when LLM parsing fails."""
    return [
        {
            "title": description[:30],
            "description": description,
            "type": "code",
            "estimated_complexity": "moderate",
        }
    ]


async def _execute_mission(
    mission: dict, context: CommandContext, quest: QuestState
) -> dict[str, Any]:
    """Execute a single mission using MissionAdapter."""
    from ..orchestration.adapter import MissionAdapter

    adapter = MissionAdapter(cwd=context.cwd)

    title = mission.get("title", "")
    desc = mission.get("description", "")
    user_request = f"{title}\n\n{desc}" if desc else title

    result = await adapter.run(
        user_request=user_request,
        progress_callback=None,
        explore_first=True,
        cwd=context.cwd,
    )

    # Rough token estimation
    metrics = result.get("metrics", {})
    quest.token_used += metrics.get("total_tasks", 0) * 500

    return result


def _generate_summary(
    description: str, missions: list[dict], results: list[dict]
) -> str:
    """Generate human-readable summary of quest results."""
    success_count = sum(1 for r in results if r.get("success"))
    total = len(results)

    lines = [
        f"## Quest Summary",
        "",
        f"**Request**: {description}",
        f"**Result**: {success_count}/{total} missions succeeded",
        "",
        "### Mission Results",
        "",
    ]

    for i, (mission, result) in enumerate(zip(missions, results), 1):
        status_icon = "✅" if result.get("success") else "❌"
        title = mission.get("title", f"Mission {i}")
        lines.append(f"{status_icon} **{title}**")
        if result.get("error"):
            err = str(result["error"])[:100]
            if len(str(result["error"])) > 100:
                err += "..."
            lines.append(f"   Error: {err}")
        warnings = result.get("warnings", [])
        if warnings:
            lines.append(f"   ⚠️ {len(warnings)} warning(s)")
        lines.append("")

    if success_count == total and total > 0:
        lines.append("🎉 All missions completed successfully!")
    elif success_count == 0 and total > 0:
        lines.append("⚠️ All missions failed. Please review the errors above.")
    elif total > 0:
        lines.append(f"⚠️ {total - success_count} mission(s) failed. Partial completion.")
    else:
        lines.append("ℹ️ No missions were executed.")

    return "\n".join(lines)


register_command(
    CommandHandler(
        name="quest",
        description="Autonomous development quest mode",
        handler=quest_command,
    )
)
