"""Layer 3: Project Memory.

Cross-session persistent memory for:
- Tech stack decisions
- Architecture patterns
- API conventions
- Learned patterns from previous rework cycles
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path


@dataclass
class ProjectMemory:
    """Persistent project-level memory.

    Stored in `.pilotcode/project_memory.json`.
    """

    project_path: str
    tech_stack: list[str] = field(default_factory=list)
    architecture_patterns: list[str] = field(default_factory=list)
    api_conventions: list[str] = field(default_factory=list)
    code_style_rules: list[str] = field(default_factory=list)
    learned_patterns: list[dict[str, Any]] = field(default_factory=list)
    custom_rules: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tech_stack": self.tech_stack,
            "architecture_patterns": self.architecture_patterns,
            "api_conventions": self.api_conventions,
            "code_style_rules": self.code_style_rules,
            "learned_patterns": self.learned_patterns,
            "custom_rules": self.custom_rules,
        }

    @classmethod
    def from_dict(cls, project_path: str, data: dict[str, Any]) -> ProjectMemory:
        return cls(
            project_path=project_path,
            tech_stack=data.get("tech_stack", []),
            architecture_patterns=data.get("architecture_patterns", []),
            api_conventions=data.get("api_conventions", []),
            code_style_rules=data.get("code_style_rules", []),
            learned_patterns=data.get("learned_patterns", []),
            custom_rules=data.get("custom_rules", {}),
        )

    def save(self) -> None:
        """Save to disk."""
        memory_dir = Path(self.project_path) / ".pilotcode"
        memory_dir.mkdir(parents=True, exist_ok=True)
        path = memory_dir / "project_memory.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, project_path: str) -> ProjectMemory:
        """Load from disk or create default."""
        path = Path(project_path) / ".pilotcode" / "project_memory.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(project_path, data)
        return cls(project_path=project_path)

    def learn_from_rework(self, pattern: str, context: str, effectiveness: float) -> None:
        """Record a learned pattern from a rework cycle."""
        self.learned_patterns.append(
            {
                "pattern": pattern,
                "context": context,
                "effectiveness": effectiveness,
                "timestamp": __import__("datetime")
                .datetime.now(__import__("datetime").timezone.utc)
                .isoformat(),
            }
        )
        self.save()

    def get_context_for_task(self, task_type: str) -> dict[str, Any]:
        """Get relevant project context for a task type."""
        return {
            "tech_stack": self.tech_stack,
            "relevant_patterns": [
                p
                for p in self.learned_patterns
                if task_type.lower() in p.get("context", "").lower()
            ],
            "conventions": self.api_conventions + self.code_style_rules,
        }


_project_memory_cache: dict[str, ProjectMemory] = {}


def get_project_memory(project_path: str | None = None) -> ProjectMemory:
    """Get project memory for a project path."""
    if project_path is None:
        project_path = os.getcwd()

    if project_path not in _project_memory_cache:
        _project_memory_cache[project_path] = ProjectMemory.load(project_path)

    return _project_memory_cache[project_path]
