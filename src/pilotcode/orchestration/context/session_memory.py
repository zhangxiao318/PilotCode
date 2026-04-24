"""Layer 2: Session Memory.

Mission-level memory for:
- Current mission's complete DAG state
- Each node's artifacts and verification results
- Session-level decisions and context
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime, timezone
from pathlib import Path

from ..task_spec import Mission
from ..state_machine import TaskState


@dataclass
class TaskArtifact:
    """An artifact produced by a task."""

    task_id: str
    version: int
    files: list[str] = field(default_factory=list)
    verification_results: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""


@dataclass
class MissionState:
    """Serializable state of a mission."""

    mission_id: str
    title: str
    status: str = "pending"
    task_states: dict[str, str] = field(default_factory=dict)
    artifacts: dict[str, list[TaskArtifact]] = field(default_factory=dict)
    state_history: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "title": self.title,
            "status": self.status,
            "task_states": self.task_states,
            "artifacts": {
                k: [{"task_id": a.task_id, "version": a.version, "files": a.files} for a in v]
                for k, v in self.artifacts.items()
            },
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class SessionMemory:
    """Session-level memory manager.

    Stores mission state during execution and archives completed sessions.
    """

    def __init__(self, archive_dir: str | None = None):
        self._missions: dict[str, MissionState] = {}
        self._active_missions: set[str] = set()
        self.archive_dir = archive_dir or self._default_archive_dir()

    def _default_archive_dir(self) -> str:
        from pathlib import Path

        return str(Path.home() / ".pilotcode" / "sessions")

    def start_session(self, mission: Mission) -> MissionState:
        """Start tracking a new mission."""
        now = datetime.now(timezone.utc).isoformat()
        state = MissionState(
            mission_id=mission.mission_id,
            title=mission.title,
            status="running",
            created_at=now,
            updated_at=now,
        )
        self._missions[mission.mission_id] = state
        self._active_missions.add(mission.mission_id)
        return state

    def update_task_state(
        self, mission_id: str, task_id: str, state: TaskState, reason: str = ""
    ) -> None:
        """Update a task's state in session memory."""
        ms = self._missions.get(mission_id)
        if not ms:
            return

        old_state = ms.task_states.get(task_id, "pending")
        ms.task_states[task_id] = state.value
        ms.state_history.append(
            {
                "task_id": task_id,
                "from": old_state,
                "to": state.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "reason": reason,
            }
        )
        ms.updated_at = datetime.now(timezone.utc).isoformat()

    def record_artifact(
        self, mission_id: str, task_id: str, files: list[str], version: int = 1
    ) -> None:
        """Record an artifact for a task."""
        ms = self._missions.get(mission_id)
        if not ms:
            return

        artifact = TaskArtifact(
            task_id=task_id,
            version=version,
            files=files,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        if task_id not in ms.artifacts:
            ms.artifacts[task_id] = []
        ms.artifacts[task_id].append(artifact)
        ms.updated_at = datetime.now(timezone.utc).isoformat()

    def get_artifact_history(self, mission_id: str, task_id: str) -> list[TaskArtifact]:
        """Get version history for a task's artifacts."""
        ms = self._missions.get(mission_id)
        return ms.artifacts.get(task_id, []) if ms else []

    def get_latest_artifact(self, mission_id: str, task_id: str) -> TaskArtifact | None:
        """Get the latest artifact for a task."""
        history = self.get_artifact_history(mission_id, task_id)
        return history[-1] if history else None

    def archive_session(self, mission_id: str) -> str | None:
        """Archive a completed session to disk.

        Returns the archive path.
        """
        ms = self._missions.get(mission_id)
        if not ms:
            return None

        ms.status = "completed"
        self._active_missions.discard(mission_id)

        # Archive directory structure:
        # ~/.pilotcode/sessions/YYYYMMDD_HHMMSS_mission_id/
        #   mission.json
        #   artifacts/v1/...
        #   artifacts/v2/...
        #   execution_trace.json

        now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        archive_path = Path(self.archive_dir) / f"{now}_{mission_id}"
        archive_path.mkdir(parents=True, exist_ok=True)

        # Save mission state
        with open(archive_path / "mission.json", "w", encoding="utf-8") as f:
            json.dump(ms.to_dict(), f, indent=2, ensure_ascii=False)

        # Save execution trace
        with open(archive_path / "execution_trace.json", "w", encoding="utf-8") as f:
            json.dump(ms.state_history, f, indent=2, ensure_ascii=False)

        # Copy artifacts
        for task_id, artifacts in ms.artifacts.items():
            for artifact in artifacts:
                dest_dir = archive_path / "artifacts" / task_id / f"v{artifact.version}"
                dest_dir.mkdir(parents=True, exist_ok=True)
                for src_file in artifact.files:
                    if Path(src_file).exists():
                        shutil.copy2(src_file, dest_dir / Path(src_file).name)

        return str(archive_path)

    def load_archived_session(self, archive_path: str) -> MissionState | None:
        """Load an archived session."""
        path = Path(archive_path) / "mission.json"
        if not path.exists():
            return None

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return MissionState(
            mission_id=data["mission_id"],
            title=data["title"],
            status=data.get("status", "completed"),
            task_states=data.get("task_states", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    def list_archived_sessions(self) -> list[str]:
        """List all archived session paths."""
        archive_dir = Path(self.archive_dir)
        if not archive_dir.exists():
            return []
        return sorted([str(p) for p in archive_dir.iterdir() if p.is_dir()])

    def get_active_missions(self) -> list[str]:
        """List currently active mission IDs."""
        return list(self._active_missions)

    def get_mission_state(self, mission_id: str) -> MissionState | None:
        """Get the current state of a mission."""
        return self._missions.get(mission_id)
