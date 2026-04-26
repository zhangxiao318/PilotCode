"""Project-level working memory for cross-task state sharing.

Provides persistent, structured memory that survives across worker executions,
so that Task B can build on the knowledge discovered by Task A.
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class FileSnapshot:
    """Snapshot of a file that has been read by a worker."""

    path: str
    content_hash: str
    line_count: int
    summary: str = ""  # Brief description of what this file contains
    mtime: float = 0.0
    read_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "content_hash": self.content_hash,
            "line_count": self.line_count,
            "summary": self.summary,
            "mtime": self.mtime,
            "read_at": self.read_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FileSnapshot:
        return cls(
            path=data["path"],
            content_hash=data["content_hash"],
            line_count=data["line_count"],
            summary=data.get("summary", ""),
            mtime=data.get("mtime", 0.0),
            read_at=data.get("read_at", ""),
        )


@dataclass
class FailedAttempt:
    """Record of a failed approach so we don't retry the same mistake."""

    task_id: str
    attempt_number: int
    approach_summary: str
    error_message: str
    root_cause: str = ""  # Analysis of why it failed
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "attempt_number": self.attempt_number,
            "approach_summary": self.approach_summary,
            "error_message": self.error_message,
            "root_cause": self.root_cause,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FailedAttempt:
        return cls(
            task_id=data["task_id"],
            attempt_number=data["attempt_number"],
            approach_summary=data["approach_summary"],
            error_message=data["error_message"],
            root_cause=data.get("root_cause", ""),
            timestamp=data.get("timestamp", ""),
        )


@dataclass
class ProjectMemory:
    """Persistent working memory shared across all workers in a mission.

    This is the antidote to the "every worker is blind" problem:
    instead of each Task getting a fresh Store + QueryEngine,
    they all read from and write to a shared ProjectMemory.
    """

    project_path: str = ""

    # Index of files that have been explored
    file_index: dict[str, FileSnapshot] = field(default_factory=dict)

    # Discovered code conventions and patterns
    conventions: dict[str, str] = field(default_factory=dict)
    # e.g. {"naming": "snake_case", "framework": "FastAPI", "test_style": "pytest"}

    # Module dependency graph (inferred from imports)
    module_graph: dict[str, list[str]] = field(default_factory=dict)

    # Failed attempts to avoid repeating
    failed_attempts: list[FailedAttempt] = field(default_factory=list)

    # Key architectural decisions discovered
    architecture_notes: list[str] = field(default_factory=list)

    # Changed files across all tasks (cumulative)
    changed_files: list[str] = field(default_factory=list)

    # Persistent project context (merged from context/project_memory.py)
    tech_stack: list[str] = field(default_factory=list)
    architecture_patterns: list[str] = field(default_factory=list)
    api_conventions: list[str] = field(default_factory=list)
    code_style_rules: list[str] = field(default_factory=list)
    learned_patterns: list[dict[str, Any]] = field(default_factory=list)
    custom_rules: dict[str, Any] = field(default_factory=dict)

    # Updated timestamp
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # ------------------------------------------------------------------
    # File tracking
    # ------------------------------------------------------------------

    def record_file_read(self, path: str, content: str, summary: str = "") -> None:
        """Record that a file has been read."""
        self.file_index[path] = FileSnapshot(
            path=path,
            content_hash=hashlib.sha256(content.encode()).hexdigest()[:16],
            line_count=len(content.splitlines()),
            summary=summary,
            read_at=datetime.now(timezone.utc).isoformat(),
        )
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def get_file_summary(self, path: str) -> str:
        """Get summary of a previously read file."""
        snap = self.file_index.get(path)
        return snap.summary if snap else ""

    def has_read_file(self, path: str) -> bool:
        """Check if a file has been read before."""
        return path in self.file_index

    # ------------------------------------------------------------------
    # Convention tracking
    # ------------------------------------------------------------------

    def record_convention(self, key: str, value: str) -> None:
        """Record a discovered code convention."""
        self.conventions[key] = value
        self.updated_at = datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Failure tracking
    # ------------------------------------------------------------------

    def record_failure(
        self, task_id: str, attempt: int, approach: str, error: str, root_cause: str = ""
    ) -> None:
        """Record a failed attempt."""
        self.failed_attempts.append(
            FailedAttempt(
                task_id=task_id,
                attempt_number=attempt,
                approach_summary=approach,
                error_message=error,
                root_cause=root_cause,
            )
        )
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def get_failures_for_task(self, task_id: str) -> list[FailedAttempt]:
        """Get all failed attempts for a specific task."""
        return [f for f in self.failed_attempts if f.task_id == task_id]

    def get_unique_failures(self) -> list[str]:
        """Get list of unique root causes across all failures."""
        seen = set()
        results = []
        for f in self.failed_attempts:
            if f.root_cause and f.root_cause not in seen:
                seen.add(f.root_cause)
                results.append(f.root_cause)
        return results

    # ------------------------------------------------------------------
    # Architecture notes
    # ------------------------------------------------------------------

    def add_architecture_note(self, note: str) -> None:
        """Add a discovered architectural note."""
        if note not in self.architecture_notes:
            self.architecture_notes.append(note)
            self.updated_at = datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Learned patterns (from context/project_memory.py)
    # ------------------------------------------------------------------

    def learn_from_rework(self, pattern: str, context: str, effectiveness: float) -> None:
        """Record a learned pattern from a rework cycle."""
        self.learned_patterns.append(
            {
                "pattern": pattern,
                "context": context,
                "effectiveness": effectiveness,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def get_context_for_task(self, task_type: str) -> dict[str, Any]:
        """Get relevant project context for a task type."""
        return {
            "tech_stack": self.tech_stack,
            "relevant_patterns": [
                p
                for p in self.learned_patterns
                if task_type.lower() in p.get("context", "").lower()
            ],
            "conventions": list(self.conventions.items())
            + self.api_conventions
            + self.code_style_rules,
        }

    # ------------------------------------------------------------------
    # Changed files
    # ------------------------------------------------------------------

    def record_changes(self, paths: list[str]) -> None:
        """Record file changes."""
        for p in paths:
            if p not in self.changed_files:
                self.changed_files.append(p)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_path": self.project_path,
            "file_index": {k: v.to_dict() for k, v in self.file_index.items()},
            "conventions": self.conventions,
            "module_graph": self.module_graph,
            "failed_attempts": [f.to_dict() for f in self.failed_attempts],
            "architecture_notes": self.architecture_notes,
            "changed_files": self.changed_files,
            "tech_stack": self.tech_stack,
            "architecture_patterns": self.architecture_patterns,
            "api_conventions": self.api_conventions,
            "code_style_rules": self.code_style_rules,
            "learned_patterns": self.learned_patterns,
            "custom_rules": self.custom_rules,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectMemory:
        return cls(
            project_path=data.get("project_path", ""),
            file_index={
                k: FileSnapshot.from_dict(v) for k, v in data.get("file_index", {}).items()
            },
            conventions=data.get("conventions", {}),
            module_graph=data.get("module_graph", {}),
            failed_attempts=[FailedAttempt.from_dict(f) for f in data.get("failed_attempts", [])],
            architecture_notes=data.get("architecture_notes", []),
            changed_files=data.get("changed_files", []),
            tech_stack=data.get("tech_stack", []),
            architecture_patterns=data.get("architecture_patterns", []),
            api_conventions=data.get("api_conventions", []),
            code_style_rules=data.get("code_style_rules", []),
            learned_patterns=data.get("learned_patterns", []),
            custom_rules=data.get("custom_rules", {}),
            updated_at=data.get("updated_at", ""),
        )

    def save(self, path: str | None = None) -> None:
        """Save to JSON file.

        If path is not provided, uses ``.pilotcode/project_memory.json``
        under :attr:`project_path`.
        """
        if path is None:
            if not self.project_path:
                raise ValueError("Cannot save: project_path is not set and no path provided")
            path = str(Path(self.project_path) / ".pilotcode" / "project_memory.json")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str | None = None) -> ProjectMemory:
        """Load from JSON file or project directory.

        If *path* points to a directory, it is treated as a project path
        and the file ``.pilotcode/project_memory.json`` underneath it is
        loaded.  If the file does not exist, a fresh instance is returned.

        If *path* is a file path, it is read directly.

        If *path* is not provided, uses ``.pilotcode/project_memory.json``
        under the current working directory.
        """
        if path is None:
            path = str(Path.cwd())

        p = Path(path)
        if p.is_dir():
            project_path = str(p)
            file_path = p / ".pilotcode" / "project_memory.json"
            if not file_path.exists():
                return cls(project_path=project_path)
            path = str(file_path)
        else:
            project_path = str(p.parent.parent) if ".pilotcode" in str(p) else str(p.parent)

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["project_path"] = data.get("project_path", project_path)
        return cls.from_dict(data)

    # ------------------------------------------------------------------
    # Prompt injection
    # ------------------------------------------------------------------

    def to_prompt_section(self, max_files: int = 20, max_notes: int = 10) -> str:
        """Format memory as a prompt section for injection into worker prompts."""
        lines = ["[PROJECT MEMORY]"]

        if self.conventions:
            lines.append("Code Conventions:")
            for k, v in self.conventions.items():
                lines.append(f"  - {k}: {v}")

        if self.architecture_notes:
            lines.append("Architecture:")
            for note in self.architecture_notes[:max_notes]:
                lines.append(f"  - {note}")

        if self.file_index:
            lines.append("Known Files:")
            for snap in list(self.file_index.values())[:max_files]:
                summary = f" ({snap.summary})" if snap.summary else ""
                lines.append(f"  - {snap.path}{summary}")

        if self.changed_files:
            lines.append(f"Changed So Far: {', '.join(self.changed_files[-10:])}")

        recent_failures = self.failed_attempts[-3:]
        if recent_failures:
            lines.append("Recent Failures (DO NOT repeat these approaches):")
            for f in recent_failures:
                lines.append(f"  - [{f.task_id}] {f.approach_summary}: {f.error_message}")

        if len(lines) == 1:
            lines.append("  (No prior project knowledge accumulated yet.)")

        return "\n".join(lines)
