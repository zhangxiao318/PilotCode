"""Plan file management — persistent plan files on disk.

Reference: Claude Code src/utils/plans.ts

Each plan is stored as a markdown file in .pilotcode/plans/.
The plan file is written during planning and read on exit,
allowing plan state to survive session restarts and subagent forks.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

_WORD_ADJECTIVES = [
    "bold",
    "calm",
    "clear",
    "cool",
    "crisp",
    "deep",
    "dry",
    "eager",
    "early",
    "easy",
    "fair",
    "fast",
    "fine",
    "free",
    "full",
    "glad",
    "good",
    "great",
    "green",
    "happy",
    "hard",
    "high",
    "hot",
    "keen",
    "kind",
    "late",
    "lean",
    "light",
    "loud",
    "low",
    "lucky",
    "main",
    "mild",
    "near",
    "neat",
    "new",
    "nice",
    "noble",
    "odd",
    "old",
    "open",
    "pale",
    "pink",
    "plain",
    "pure",
    "quick",
    "quiet",
    "rare",
    "raw",
    "red",
    "rich",
    "rough",
    "rude",
    "safe",
    "shy",
    "slim",
    "slow",
    "sly",
    "small",
    "soft",
    "solid",
    "sore",
    "sour",
    "still",
    "sure",
    "sweet",
    "swift",
    "tall",
    "tame",
    "tart",
    "thin",
    "tiny",
    "tough",
    "true",
    "vast",
    "vivid",
    "warm",
    "weak",
    "wet",
    "wild",
    "wise",
    "young",
]

_WORD_NOUNS = [
    "apple",
    "arch",
    "beach",
    "bird",
    "block",
    "bloom",
    "breeze",
    "bridge",
    "brook",
    "cabin",
    "camel",
    "cave",
    "cloud",
    "coast",
    "coral",
    "crane",
    "creek",
    "crest",
    "crowd",
    "crown",
    "cycle",
    "dawn",
    "deer",
    "dune",
    "dust",
    "eagle",
    "echo",
    "edge",
    "elm",
    "ember",
    "fawn",
    "fern",
    "field",
    "flame",
    "flint",
    "flood",
    "flower",
    "foam",
    "fog",
    "ford",
    "forge",
    "frog",
    "frost",
    "garden",
    "gem",
    "glacier",
    "glade",
    "grain",
    "grass",
    "grave",
    "grove",
    "gulf",
    "gust",
    "harbor",
    "haze",
    "heart",
    "herb",
    "hill",
    "hive",
    "horn",
    "horse",
    "hull",
    "ice",
    "icing",
    "ivy",
    "jade",
    "jazz",
    "jet",
    "jewel",
    "kayak",
    "kite",
    "lake",
    "lamb",
    "lamp",
    "lane",
    "lark",
    "lava",
    "leaf",
    "lily",
    "lodge",
    "loom",
    "lunar",
    "meadow",
    "mint",
    "mist",
    "moon",
    "moss",
    "moth",
    "mound",
    "muse",
    "oak",
    "oasis",
    "orbit",
    "ore",
    "owl",
    "palm",
    "path",
    "pearl",
    "pine",
    "pixel",
    "plain",
    "plaza",
    "pond",
    "port",
    "pulse",
    "pylon",
    "query",
    "raft",
    "rain",
    "reef",
    "ridge",
    "rift",
    "river",
    "robin",
    "rock",
    "rook",
    "rope",
    "rose",
    "route",
    "ruby",
    "ruin",
    "sage",
    "sail",
    "sand",
    "scale",
    "scene",
    "scope",
    "seed",
    "shade",
    "shelf",
    "shell",
    "shore",
    "silk",
    "skull",
    "slate",
    "slope",
    "smoke",
    "snail",
    "snow",
    "soil",
    "solar",
    "spark",
    "spine",
    "spire",
    "spray",
    "squad",
    "stack",
    "star",
    "stem",
    "stone",
    "stove",
    "straw",
    "stream",
    "summit",
    "sun",
    "surf",
    "swamp",
    "sweep",
    "swift",
    "swing",
    "table",
    "tale",
    "task",
    "thorn",
    "tide",
    "tiger",
    "tile",
    "timer",
    "tower",
    "track",
    "trail",
    "tray",
    "tree",
    "trial",
    "trout",
    "truck",
    "trunk",
    "tulip",
    "tuna",
    "tunnel",
    "tusk",
    "twig",
    "valley",
    "vault",
    "verse",
    "vine",
    "vista",
    "vocal",
    "wake",
    "wave",
    "web",
    "whale",
    "wheat",
    "wheel",
    "willow",
    "wind",
    "wine",
    "wing",
    "winter",
    "wisp",
    "wolf",
    "womb",
    "wood",
    "wool",
    "word",
    "worm",
    "wreck",
    "yard",
    "yarn",
    "year",
    "yield",
    "zebra",
    "zone",
]


def _generate_slug() -> str:
    """Generate a human-friendly plan slug like "quick-fox"."""
    adj = random.choice(_WORD_ADJECTIVES)
    noun = random.choice(_WORD_NOUNS)
    return f"{adj}-{noun}"


def get_plans_dir() -> Path:
    """Get the plans directory, creating it if necessary."""
    plans_dir = Path.cwd() / ".pilotcode" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    return plans_dir


def get_plan_file_path(agent_id: str | None = None) -> Path:
    """Get the plan file path for the current session or agent.

    Args:
        agent_id: If provided, creates an agent-specific plan file.

    Returns:
        Path to the plan file.
    """
    plans_dir = get_plans_dir()
    slug = _get_or_create_slug(agent_id)

    if agent_id:
        filename = f"{slug}-agent-{agent_id}.md"
    else:
        filename = f"{slug}.md"

    return plans_dir / filename


_SLUG_CACHE: dict[str, str] = {}


def _get_or_create_slug(agent_id: str | None = None) -> str:
    """Get or create a plan slug, cached in memory for the session."""
    key = agent_id or "__main__"
    if key not in _SLUG_CACHE:
        slug_file = get_plans_dir() / f".slug-{key}"
        if slug_file.exists():
            _SLUG_CACHE[key] = slug_file.read_text(encoding="utf-8").strip()
        else:
            slug = _generate_slug()
            _SLUG_CACHE[key] = slug
            slug_file.write_text(slug, encoding="utf-8")
    return _SLUG_CACHE[key]


def write_plan(plan_data: dict[str, Any], agent_id: str | None = None) -> Path:
    """Write a plan to disk as markdown.

    Args:
        plan_data: The plan data (title, phases, tasks, etc.)
        agent_id: Optional agent ID for agent-specific plans.

    Returns:
        Path to the written plan file.
    """
    file_path = get_plan_file_path(agent_id)
    markdown = _plan_to_markdown(plan_data)
    file_path.write_text(markdown, encoding="utf-8")
    return file_path


def read_plan(agent_id: str | None = None) -> str | None:
    """Read plan from disk.

    Args:
        agent_id: Optional agent ID.

    Returns:
        Plan content as string, or None if no plan exists.
    """
    file_path = get_plan_file_path(agent_id)
    if file_path.exists():
        return file_path.read_text(encoding="utf-8")
    return None


def copy_plan_for_fork(agent_id: str, parent_agent_id: str | None = None) -> Path | None:
    """Copy a plan for a forked agent session.

    Args:
        agent_id: The new agent's ID.
        parent_agent_id: The parent agent's ID.

    Returns:
        Path to the copied plan file, or None.
    """
    parent_plan = read_plan(parent_agent_id)
    if parent_plan is None:
        return None

    file_path = get_plan_file_path(agent_id)
    file_path.write_text(parent_plan, encoding="utf-8")
    return file_path


def _plan_to_markdown(plan_data: dict[str, Any]) -> str:
    """Convert a plan dict to markdown.

    Args:
        plan_data: The plan data.

    Returns:
        Markdown string.
    """
    lines: list[str] = []
    title = plan_data.get("title", "Implementation Plan")
    lines.append(f"# {title}")
    lines.append("")

    mission = plan_data.get("mission", plan_data)
    title = mission.get("title", title)
    lines.append(f"## {title}")
    lines.append("")

    phases = mission.get("phases", [])
    for phase in phases:
        phase_title = phase.get("title", "Phase")
        lines.append(f"### {phase_title}")
        if phase.get("description"):
            lines.append(f"{phase['description']}")
        lines.append("")

        tasks = phase.get("tasks", [])
        for task in tasks:
            task_id = task.get("id", "")
            task_title = task.get("title", "")
            lines.append(f"- **[**{task_id}**]** {task_title}")
            if task.get("objective"):
                lines.append(f"  - Objective: {task['objective']}")
            if task.get("dependencies"):
                deps = ", ".join(task["dependencies"])
                lines.append(f"  - Depends on: {deps}")
            if task.get("complexity"):
                lines.append(f"  - Complexity: {task['complexity']}")
        lines.append("")

    lines.append("---")
    lines.append(f"_Generated: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}_")
    return "\n".join(lines)


def _parse_plan_json(json_str: str) -> dict[str, Any] | None:
    """Extract plan JSON from a string that might contain markdown.

    Args:
        json_str: String that may contain JSON.

    Returns:
        Parsed plan dict, or None.
    """
    # Try direct parse first
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Try extracting from ```json ... ``` blocks
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", json_str, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding { ... } directly
    m = re.search(r"\{.*\}", json_str, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    return None


def recover_plan_from_messages(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Recover plan data from message history.

    Scans for ExitPlanMode tool calls or plan_content attachments.

    Args:
        messages: List of message dicts.

    Returns:
        Recovered plan data, or None.
    """
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            plan = _parse_plan_json(content)
            if plan:
                return plan
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "plan_content":
                    plan = _parse_plan_json(block.get("text", ""))
                    if plan:
                        return plan
                elif isinstance(block, dict) and block.get("type") == "tool_use":
                    name = block.get("name", "")
                    if name in ("ExitPlanMode", "PlanMode"):
                        inp = block.get("input", {})
                        if "plan" in inp:
                            plan = _parse_plan_json(inp["plan"])
                            if plan:
                                return plan
    return None
