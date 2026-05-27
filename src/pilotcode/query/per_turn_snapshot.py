"""Per-turn file snapshot tracker.

Tracks file modifications across conversation turns by monitoring
file edit/write tool calls and computing lightweight diffs.

Unlike the full workspace SnapshotManager (which copies entire workspaces
for rollback), this tracker only hashes files touched during the session
for efficient turn-by-turn change summaries.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FileSnapshot:
    """Lightweight snapshot of a single file."""

    path: str
    content_hash: str
    mtime: float


@dataclass
class TurnSnapshot:
    """Snapshot of all tracked files at a specific turn."""

    turn_index: int
    timestamp: float
    files: dict[str, FileSnapshot] = field(default_factory=dict)


@dataclass
class TurnDiff:
    """Diff between two turn snapshots."""

    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.modified)

    def to_summary(self, max_files: int = 10) -> str:
        """Generate human-readable summary for system prompt injection."""
        if not self.has_changes:
            return ""
        parts: list[str] = []
        if self.added:
            label = "created" if len(self.added) == 1 else "created"
            files = ", ".join(self.added[:max_files])
            parts.append(f"+ {label}: {files}")
        if self.modified:
            label = "modified" if len(self.modified) == 1 else "modified"
            files = ", ".join(self.modified[:max_files])
            parts.append(f"~ {label}: {files}")
        if self.removed:
            label = "deleted" if len(self.removed) == 1 else "deleted"
            files = ", ".join(self.removed[:max_files])
            parts.append(f"- {label}: {files}")
        extra = sum(
            max(0, len(getattr(self, attr)) - max_files)
            for attr in ("added", "modified", "removed")
        )
        if extra:
            parts.append(f"(+{extra} more)")
        return " | ".join(parts)


class PerTurnSnapshotTracker:
    """Tracks file changes across conversation turns.

    Usage:
        tracker = PerTurnSnapshotTracker("/workspace")
        tracker.track_file("src/main.py")  # During tool execution
        diff = tracker.end_turn()          # At turn boundary
        if diff and diff.has_changes:
            print(diff.to_summary())
    """

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root)
        self._turns: list[TurnSnapshot] = []
        self._current_turn_tracked_files: set[str] = set()
        self._turn_counter: int = 0

    def track_file(self, file_path: str) -> None:
        """Mark a file as being tracked for the current turn.

        Called from tool execution paths (FileEdit, FileWrite, ApplyPatch)
        to register that this file may have changed.
        """
        if file_path:
            self._current_turn_tracked_files.add(file_path)

    def end_turn(self) -> TurnDiff | None:
        """End current turn, capture snapshot, and return diff from previous turn.

        Should be called at the start of each new user/model turn after
        all tool results from the previous turn have been processed.
        """
        snapshot = self._capture_snapshot()
        diff = None
        if self._turns:
            diff = self._diff(self._turns[-1], snapshot)
        self._turns.append(snapshot)
        self._current_turn_tracked_files.clear()
        self._turn_counter += 1
        return diff

    def _capture_snapshot(self) -> TurnSnapshot:
        """Capture current state of all tracked files."""
        files: dict[str, FileSnapshot] = {}
        for path_str in self._current_turn_tracked_files:
            path = Path(path_str)
            if not path.is_absolute():
                path = self.workspace_root / path
            if path.exists() and path.is_file():
                try:
                    content = path.read_bytes()
                    h = hashlib.sha256(content).hexdigest()[:16]
                    mtime = path.stat().st_mtime
                    rel_path = str(path.relative_to(self.workspace_root))
                    files[rel_path] = FileSnapshot(rel_path, h, mtime)
                except (IOError, OSError):
                    pass
        return TurnSnapshot(
            turn_index=self._turn_counter,
            timestamp=time.time(),
            files=files,
        )

    def _diff(self, prev: TurnSnapshot, curr: TurnSnapshot) -> TurnDiff:
        """Compute diff between two snapshots."""
        added: list[str] = []
        removed: list[str] = []
        modified: list[str] = []

        for path, snap in curr.files.items():
            if path not in prev.files:
                added.append(path)
            elif prev.files[path].content_hash != snap.content_hash:
                modified.append(path)

        for path in prev.files:
            if path not in curr.files:
                removed.append(path)

        return TurnDiff(added=added, removed=removed, modified=modified)

    def get_last_diff(self) -> TurnDiff | None:
        """Get the most recent diff without advancing the turn."""
        if len(self._turns) < 2:
            return None
        return self._diff(self._turns[-2], self._turns[-1])

    def get_turn_history(self) -> list[TurnSnapshot]:
        """Return all captured turn snapshots (for debugging/analysis)."""
        return list(self._turns)

    def reset(self) -> None:
        """Clear all tracked history."""
        self._turns.clear()
        self._current_turn_tracked_files.clear()
        self._turn_counter = 0
