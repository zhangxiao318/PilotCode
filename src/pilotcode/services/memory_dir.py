"""File-based memory directory (memdir) for long-term persistent memory.

Inspired by Claude Code's memdir design and Hermes' Tier-1 Fast Memory:
- MEMORY.md: project conventions, tool quirks, lessons learned (~2200 chars max)
- USER.md:  user identity, communication style, preferences (~1375 chars max)
- topic .md files: individual memory entries with YAML frontmatter
- Frontmatter fields: description, type (user/feedback/project/reference), tags

Hermes-style enhancements:
- Two tiny markdown files with hard character caps
- Frozen mid-session: writes staged in memory, committed at turn boundary
- Auto-consolidation at 80% capacity: LLM-driven merge/drop back to density
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

MAX_ENTRYPOINT_LINES = 200
MAX_ENTRYPOINT_BYTES = 25_000
MAX_MEMORY_FILES = 200
FRONTMATTER_MAX_LINES = 30

# ---------------------------------------------------------------------------
# Hermes-style Fast Memory limits
# ---------------------------------------------------------------------------
MEMORY_MD_MAX_CHARS = 2200
USER_MD_MAX_CHARS = 1375
CONSOLIDATION_THRESHOLD = 0.80  # Trigger consolidation at 80% capacity


# ---------------------------------------------------------------------------
# Data structures for staged updates
# ---------------------------------------------------------------------------


@dataclass
class FastMemoryUpdate:
    """A pending memory update staged during a turn (frozen until boundary)."""

    action: str  # "add" | "replace" | "remove" | "consolidate"
    target: str  # "MEMORY.md" | "USER.md" | topic filename
    content: str = ""
    key: str | None = None  # For replace/remove: identifier of existing entry
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FastMemoryState:
    """In-memory snapshot of fast memory used during a turn (frozen)."""

    memory_md_content: str = ""
    user_md_content: str = ""
    memory_md_hash: str = ""
    user_md_hash: str = ""

    def compute_hashes(self) -> None:
        self.memory_md_hash = hashlib.sha256(self.memory_md_content.encode()).hexdigest()[:16]
        self.user_md_hash = hashlib.sha256(self.user_md_content.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def get_memory_dir(cwd: str | Path) -> Path:
    """Return project-level memory directory."""
    from ..utils.paths import get_project_memory_dir

    return get_project_memory_dir(cwd)


def ensure_memory_dir(cwd: str | Path) -> Path:
    """Ensure memory directory exists."""
    d = get_memory_dir(cwd)
    d.mkdir(parents=True, exist_ok=True)
    return d


def truncate_entrypoint(raw: str) -> tuple[str, bool]:
    """Truncate MEMORY.md to line and byte caps.

    Returns:
        (truncated_content, was_truncated)
    """
    trimmed = raw.strip()
    lines = trimmed.split("\n")
    if len(lines) <= MAX_ENTRYPOINT_LINES and len(trimmed) <= MAX_ENTRYPOINT_BYTES:
        return trimmed, False

    truncated = "\n".join(lines[:MAX_ENTRYPOINT_LINES])
    if len(truncated) > MAX_ENTRYPOINT_BYTES:
        cut_at = truncated.rfind("\n", 0, MAX_ENTRYPOINT_BYTES)
        truncated = truncated[: cut_at if cut_at > 0 else MAX_ENTRYPOINT_BYTES]

    reason = (
        f"{len(lines)} lines (limit: {MAX_ENTRYPOINT_LINES})"
        if len(lines) > MAX_ENTRYPOINT_LINES
        else f"{len(trimmed)} bytes (limit: {MAX_ENTRYPOINT_BYTES})"
    )
    return (
        truncated + f"\n\n> WARNING: MEMORY.md is {reason} and was truncated. "
        "Only part of it was loaded. Keep index entries to one line under ~200 chars; move detail into topic files.",
        True,
    )


def truncate_fast_memory(raw: str, max_chars: int, label: str) -> tuple[str, bool]:
    """Truncate a fast-memory file to a hard character cap.

    Returns:
        (truncated_content, was_truncated)
    """
    trimmed = raw.strip()
    if len(trimmed) <= max_chars:
        return trimmed, False

    # Try to cut at a line boundary
    cut_at = trimmed.rfind("\n", 0, max_chars)
    truncated = trimmed[: cut_at if cut_at > 0 else max_chars]
    return (
        truncated + f"\n\n> WARNING: {label} exceeded {max_chars} chars and was truncated. "
        f"Consolidation recommended to merge or drop outdated entries.",
        True,
    )


def _is_consolidation_needed(content: str, max_chars: int) -> bool:
    """Check whether content has crossed the consolidation threshold."""
    return len(content.strip()) > max_chars * CONSOLIDATION_THRESHOLD


def build_consolidation_prompt(content: str, label: str, max_chars: int) -> str:
    """Build a prompt asking the LLM to consolidate memory back to density."""
    current_len = len(content.strip())
    target_len = int(max_chars * 0.6)  # Target ~60% after consolidation
    return (
        f"The {label} memory file is at {current_len}/{max_chars} chars "
        f"(threshold: {int(max_chars * CONSOLIDATION_THRESHOLD)}). "
        f"Please consolidate it down to ~{target_len} chars by:\n"
        "- Merging related entries\n"
        "- Removing outdated or redundant information\n"
        "- Rewriting verbose entries more concisely\n\n"
        "Return ONLY the consolidated content, no explanation.\n\n"
        f"Current content:\n```\n{content}\n```"
    )


# ---------------------------------------------------------------------------
# File loading / saving
# ---------------------------------------------------------------------------


def load_memory_index(cwd: str | Path) -> Optional[str]:
    """Load and truncate MEMORY.md content for system prompt injection."""
    d = ensure_memory_dir(cwd)
    entrypoint = d / "MEMORY.md"
    if not entrypoint.exists():
        return None
    try:
        raw = entrypoint.read_text(encoding="utf-8", errors="ignore")
        content, _ = truncate_entrypoint(raw)
        return content
    except Exception:
        return None


def load_fast_memory_file(cwd: str | Path, filename: str, max_chars: int) -> tuple[str, bool]:
    """Load a fast-memory file (MEMORY.md or USER.md) with char cap.

    Returns:
        (content, was_truncated)
    """
    d = ensure_memory_dir(cwd)
    path = d / filename
    if not path.exists():
        return "", False
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
        return truncate_fast_memory(raw, max_chars, filename)
    except Exception:
        return "", False


def save_fast_memory_file(cwd: str | Path, filename: str, content: str) -> bool:
    """Save a fast-memory file atomically."""
    d = ensure_memory_dir(cwd)
    path = d / filename
    try:
        path.write_text(content.strip() + "\n", encoding="utf-8")
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Frontmatter / topic file helpers (unchanged from original)
# ---------------------------------------------------------------------------


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from markdown content.

    Returns:
        (frontmatter_dict, body_without_frontmatter)
    """
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    fm_text = parts[1].strip()
    body = parts[2].strip()
    fm: dict[str, Any] = {}
    for line in fm_text.splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            fm[key.strip()] = val.strip()
    return fm, body


def scan_memory_files(cwd: str | Path) -> list[dict[str, Any]]:
    """Scan memory directory for .md files (excluding MEMORY.md and USER.md), read frontmatter.

    Returns list of dicts with keys: filename, path, mtime, description, type, tags.
    Sorted newest-first, capped at MAX_MEMORY_FILES.
    """
    d = ensure_memory_dir(cwd)
    results: list[dict[str, Any]] = []
    try:
        md_files = sorted(
            [f for f in d.rglob("*.md") if f.name not in ("MEMORY.md", "USER.md")],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:MAX_MEMORY_FILES]
    except Exception:
        return results

    for f in md_files:
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()[:FRONTMATTER_MAX_LINES]
            fm, _ = parse_frontmatter("\n".join(lines))
            results.append(
                {
                    "filename": str(f.relative_to(d)),
                    "path": str(f),
                    "mtime": f.stat().st_mtime,
                    "description": fm.get("description", ""),
                    "type": fm.get("type", ""),
                    "tags": [t.strip() for t in str(fm.get("tags", "")).split(",") if t.strip()],
                }
            )
        except Exception:
            continue
    return results


# ---------------------------------------------------------------------------
# Prompt building (now includes both MEMORY.md and USER.md)
# ---------------------------------------------------------------------------


def build_memory_prompt(cwd: str | Path) -> Optional[str]:
    """Build the memory system prompt section (instructions + MEMORY.md + USER.md)."""
    auto_dir = ensure_memory_dir(cwd)

    # Load both fast-memory files
    memory_content, memory_truncated = load_fast_memory_file(cwd, "MEMORY.md", MEMORY_MD_MAX_CHARS)
    user_content, user_truncated = load_fast_memory_file(cwd, "USER.md", USER_MD_MAX_CHARS)

    lines = [
        "# Memory",
        "",
        f"You have a persistent, file-based memory system at `{auto_dir}`.",
        "Build up this memory over time so future conversations have complete context.",
        "",
        "## How to save memories",
        "Write each memory to its own file (e.g., `user_role.md`, `project_decisions.md`) using YAML frontmatter:",
        "",
        "```yaml",
        "---",
        "description: Short description of this memory",
        "type: user | feedback | project | reference",
        "tags: comma, separated, tags",
        "---",
        "```",
        "",
        "- Then add a pointer in MEMORY.md: `- [Title](file.md) — one-line hook`",
        f"- MEMORY.md is always loaded into context (max {MEMORY_MD_MAX_CHARS} chars, {MAX_ENTRYPOINT_LINES} lines)",
        f"- USER.md stores user identity, style, preferences (max {USER_MD_MAX_CHARS} chars)",
        "- Organize by topic, not chronologically",
        "- Update or remove outdated memories",
        "- Do not write duplicate memories; check existing files first",
        "",
    ]

    # MEMORY.md section
    lines.extend(["## MEMORY.md (project conventions, tool quirks, lessons learned)", ""])
    if memory_content:
        lines.append(memory_content)
        if memory_truncated:
            lines.append(
                "\n> Note: MEMORY.md was truncated. Consider consolidating to fit within the limit."
            )
    else:
        lines.append(
            "Your MEMORY.md is currently empty. When you save new memories, they will appear here."
        )
    lines.append("")

    # USER.md section
    lines.extend(["## USER.md (user identity, communication style, preferences)", ""])
    if user_content:
        lines.append(user_content)
        if user_truncated:
            lines.append(
                "\n> Note: USER.md was truncated. Consider consolidating to fit within the limit."
            )
    else:
        lines.append("Your USER.md is currently empty. User-specific preferences will appear here.")
    lines.append("")

    return "\n".join(lines)


def build_memory_only_prompt(cwd: str | Path) -> Optional[str]:
    """Build prompt with only MEMORY.md (backwards compat for callers expecting old behavior)."""
    auto_dir = ensure_memory_dir(cwd)
    index_content = load_memory_index(cwd)

    lines = [
        "# Memory",
        "",
        f"You have a persistent, file-based memory system at `{auto_dir}`.",
        "Build up this memory over time so future conversations have complete context.",
        "",
        "## How to save memories",
        "Write each memory to its own file (e.g., `user_role.md`, `project_decisions.md`) using YAML frontmatter:",
        "",
        "```yaml",
        "---",
        "description: Short description of this memory",
        "type: user | feedback | project | reference",
        "tags: comma, separated, tags",
        "---",
        "```",
        "",
        "- Then add a pointer in MEMORY.md: `- [Title](file.md) — one-line hook`",
        f"- MEMORY.md is always loaded into context (max {MAX_ENTRYPOINT_LINES} lines)",
        "- Organize by topic, not chronologically",
        "- Update or remove outdated memories",
        "- Do not write duplicate memories; check existing files first",
        "",
    ]

    if index_content:
        lines.extend(["## MEMORY.md", "", index_content])
    else:
        lines.extend(
            [
                "## MEMORY.md",
                "",
                "Your MEMORY.md is currently empty. When you save new memories, they will appear here.",
            ]
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# FastMemoryManager: Hermes-style Tier-1 memory with frozen + consolidation
# ---------------------------------------------------------------------------


class FastMemoryManager:
    """Manages MEMORY.md and USER.md with frozen-mid-session and auto-consolidation.

    Design:
    - During a turn, all updates are STAGED in memory (frozen state).
    - At turn boundary, pending updates are COMMITTED to disk.
    - This preserves the LLM prefix cache because the system prompt hash
      does not change mid-turn.
    - Consolidation is triggered when content exceeds 80% of its cap.
    """

    def __init__(self, cwd: str | Path):
        self.memory_dir = ensure_memory_dir(cwd)
        self._pending_updates: list[FastMemoryUpdate] = []
        self._frozen_state: FastMemoryState = FastMemoryState()
        self._load_frozen_state()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_frozen_state(self) -> None:
        """Load current on-disk state into the frozen snapshot."""
        mem, _ = load_fast_memory_file(self.memory_dir, "MEMORY.md", MEMORY_MD_MAX_CHARS)
        usr, _ = load_fast_memory_file(self.memory_dir, "USER.md", USER_MD_MAX_CHARS)
        self._frozen_state = FastMemoryState(
            memory_md_content=mem,
            user_md_content=usr,
        )
        self._frozen_state.compute_hashes()

    # ------------------------------------------------------------------
    # Frozen staging (mid-turn writes are held in memory only)
    # ------------------------------------------------------------------

    def stage_update(self, update: FastMemoryUpdate) -> None:
        """Stage an update to be applied at the next turn boundary.

        This is the "frozen mid-session" mechanism: the on-disk files
        are NOT modified immediately, so the system prompt prefix cache
        remains valid for the current turn.
        """
        self._pending_updates.append(update)

    def stage_memory_add(self, title: str, filename: str, hook: str) -> None:
        """Convenience: stage adding a pointer to MEMORY.md."""
        line = f"- [{title}]({filename}) — {hook}"
        self.stage_update(FastMemoryUpdate(action="add", target="MEMORY.md", content=line))

    def stage_user_preference(self, key: str, value: str) -> None:
        """Convenience: stage adding a user preference to USER.md."""
        line = f"- **{key}**: {value}"
        self.stage_update(FastMemoryUpdate(action="add", target="USER.md", content=line, key=key))

    def has_pending_updates(self) -> bool:
        """Return True if there are staged updates waiting to be committed."""
        return len(self._pending_updates) > 0

    def get_pending_updates(self) -> list[FastMemoryUpdate]:
        """Return a copy of pending updates."""
        return self._pending_updates.copy()

    # ------------------------------------------------------------------
    # Turn boundary commit (writes to disk + refreshes frozen state)
    # ------------------------------------------------------------------

    def commit_at_turn_boundary(self) -> dict[str, Any]:
        """Apply all staged updates to disk and refresh the frozen snapshot.

        Returns:
            Summary dict with files_modified and consolidation_needed flags.
        """
        result: dict[str, Any] = {
            "files_modified": [],
            "consolidation_needed": {},
            "updates_applied": 0,
        }

        if not self._pending_updates:
            return result

        # Group updates by target file
        by_target: dict[str, list[FastMemoryUpdate]] = {}
        for u in self._pending_updates:
            by_target.setdefault(u.target, []).append(u)

        # Apply to MEMORY.md
        if "MEMORY.md" in by_target:
            ok, needs_consolidation = self._apply_updates_to_file(
                "MEMORY.md", MEMORY_MD_MAX_CHARS, by_target["MEMORY.md"]
            )
            if ok:
                result["files_modified"].append("MEMORY.md")
                result["updates_applied"] += len(by_target["MEMORY.md"])
            if needs_consolidation:
                result["consolidation_needed"]["MEMORY.md"] = True

        # Apply to USER.md
        if "USER.md" in by_target:
            ok, needs_consolidation = self._apply_updates_to_file(
                "USER.md", USER_MD_MAX_CHARS, by_target["USER.md"]
            )
            if ok:
                result["files_modified"].append("USER.md")
                result["updates_applied"] += len(by_target["USER.md"])
            if needs_consolidation:
                result["consolidation_needed"]["USER.md"] = True

        # Apply to topic files (direct write, no frozen semantics needed)
        for target, updates in by_target.items():
            if target in ("MEMORY.md", "USER.md"):
                continue
            # Topic files are written directly (they are not in system prompt)
            for u in updates:
                if u.action == "write":
                    path = self.memory_dir / target
                    path.write_text(u.content, encoding="utf-8")
                    result["files_modified"].append(target)
                    result["updates_applied"] += 1

        # Clear pending queue
        self._pending_updates.clear()

        # Refresh frozen state with new on-disk content
        self._load_frozen_state()

        return result

    def _apply_updates_to_file(
        self, filename: str, max_chars: int, updates: list[FastMemoryUpdate]
    ) -> tuple[bool, bool]:
        """Apply a batch of updates to MEMORY.md or USER.md.

        Returns:
            (success, needs_consolidation)
        """
        content, _ = load_fast_memory_file(self.memory_dir, filename, max_chars)

        if not content.strip():
            # Initialize empty file with a header
            if filename == "MEMORY.md":
                content = "# Memory Index\n"
            else:
                content = "# User Profile\n"

        lines = content.splitlines()

        for u in updates:
            if u.action == "add":
                # Simple dedup: don't add exact duplicate lines
                if u.content not in lines:
                    lines.append(u.content)
            elif u.action == "replace" and u.key:
                # Replace line containing the key
                new_lines = []
                replaced = False
                for line in lines:
                    if u.key in line and not replaced:
                        new_lines.append(u.content)
                        replaced = True
                    else:
                        new_lines.append(line)
                if not replaced:
                    new_lines.append(u.content)
                lines = new_lines
            elif u.action == "remove" and u.key:
                lines = [ln for ln in lines if u.key not in ln]
            elif u.action == "consolidate":
                # LLM-provided consolidated content replaces entire file
                lines = u.content.strip().splitlines()

        new_content = "\n".join(lines)

        # Check consolidation threshold BEFORE writing
        needs_consolidation = _is_consolidation_needed(new_content, max_chars)

        # Truncate if over hard limit
        new_content, _ = truncate_fast_memory(new_content, max_chars, filename)

        # Write
        ok = save_fast_memory_file(self.memory_dir.parent, filename, new_content)
        return ok, needs_consolidation

    # ------------------------------------------------------------------
    # Consolidation
    # ------------------------------------------------------------------

    def check_consolidation(self) -> dict[str, Any]:
        """Check if any fast-memory file needs consolidation.

        Returns:
            Dict like {"MEMORY.md": {"needed": True, "current": 1900, "threshold": 1760}, ...}
        """
        result: dict[str, Any] = {}
        for filename, max_chars in (
            ("MEMORY.md", MEMORY_MD_MAX_CHARS),
            ("USER.md", USER_MD_MAX_CHARS),
        ):
            content, _ = load_fast_memory_file(self.memory_dir, filename, max_chars)
            current = len(content.strip())
            threshold = int(max_chars * CONSOLIDATION_THRESHOLD)
            result[filename] = {
                "needed": current > threshold,
                "current": current,
                "threshold": threshold,
                "max": max_chars,
                "prompt": (
                    build_consolidation_prompt(content, filename, max_chars)
                    if current > threshold
                    else None
                ),
            }
        return result

    def force_consolidate(self, filename: str, consolidated_content: str) -> bool:
        """Apply LLM-consolidated content directly (typically called after nudge)."""
        if filename not in ("MEMORY.md", "USER.md"):
            return False
        max_chars = MEMORY_MD_MAX_CHARS if filename == "MEMORY.md" else USER_MD_MAX_CHARS
        truncated, _ = truncate_fast_memory(consolidated_content, max_chars, filename)
        return save_fast_memory_file(self.memory_dir.parent, filename, truncated)

    # ------------------------------------------------------------------
    # Frozen-state accessors (for prompt cache optimization)
    # ------------------------------------------------------------------

    def get_frozen_state(self) -> FastMemoryState:
        """Return the frozen state used for prefix-cache hashing."""
        return self._frozen_state

    def get_frozen_hash(self) -> str:
        """Return a combined hash of the frozen fast-memory state."""
        combined = f"{self._frozen_state.memory_md_hash}:{self._frozen_state.user_md_hash}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Legacy topic file helpers (unchanged API)
# ---------------------------------------------------------------------------


def write_memory_file(
    cwd: str | Path,
    filename: str,
    frontmatter: dict[str, str],
    body: str,
) -> Path:
    """Write or update a topic memory file."""
    d = ensure_memory_dir(cwd)
    filepath = d / filename
    fm_lines = [f"{k}: {v}" for k, v in frontmatter.items()]
    content = "---\n" + "\n".join(fm_lines) + "\n---\n\n" + body.strip() + "\n"
    filepath.write_text(content, encoding="utf-8")
    return filepath


def update_memory_index(
    cwd: str | Path,
    title: str,
    filename: str,
    hook: str,
) -> None:
    """Add or update an entry in MEMORY.md index.

    NOTE: This writes directly to disk (not staged). For frozen writes,
    use FastMemoryManager.stage_memory_add() + commit_at_turn_boundary().
    """
    d = ensure_memory_dir(cwd)
    entrypoint = d / "MEMORY.md"
    line = f"- [{title}]({filename}) — {hook}"

    if entrypoint.exists():
        content = entrypoint.read_text(encoding="utf-8").strip()
    else:
        content = "# Memory Index\n"

    # Simple dedup: remove existing line pointing to same filename
    lines = content.splitlines()
    lines = [line_item for line_item in lines if f"]({filename})" not in line_item]
    lines.append(line)

    new_content = "\n".join(lines)
    # Apply char cap
    new_content, _ = truncate_fast_memory(new_content, MEMORY_MD_MAX_CHARS, "MEMORY.md")
    entrypoint.write_text(new_content + "\n", encoding="utf-8")
