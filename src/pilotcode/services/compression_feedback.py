"""Compression quality feedback loop - MemPO-style learning from outcomes.

This module implements:
1. Compression outcome tracking
2. Quality metrics calculation
3. Strategy adaptation based on feedback
4. Integration with memory value learning
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from enum import Enum
from collections import defaultdict


from .task_aware_compression import TaskAwareCompressionResult, CompressionMode
from .memory_value import MemoryValueEstimator


class TaskOutcome(Enum):
    """Outcome of a task after compression."""

    SUCCESS = "success"  # Task completed successfully
    PARTIAL_SUCCESS = "partial"  # Task partially completed
    FAILURE = "failure"  # Task failed
    ABANDONED = "abandoned"  # Task was abandoned
    TIMEOUT = "timeout"  # Task timed out


class CompressionQuality(Enum):
    """Quality rating of compression."""

    EXCELLENT = 5  # Compressed well, task succeeded
    GOOD = 4  # Compressed reasonably, task succeeded
    FAIR = 3  # Some issues but task completed
    POOR = 2  # Compression caused problems
    BAD = 1  # Compression severely hurt performance


@dataclass
class CompressionEvent:
    """Record of a compression event."""

    event_id: str
    timestamp: float
    task_id: str
    task_description: str

    # Pre-compression state
    original_message_count: int
    original_token_count: int

    # Compression parameters
    compression_mode: CompressionMode
    target_tokens: int

    # Post-compression state
    compressed_message_count: int
    compressed_token_count: int
    retained_message_ids: list[str]
    removed_message_ids: list[str]
    summarized_message_ids: list[str]

    # Value metrics
    value_retention_rate: float

    # Will be filled after task completion
    outcome: Optional[TaskOutcome] = None
    outcome_timestamp: Optional[float] = None
    quality_rating: Optional[CompressionQuality] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "task_id": self.task_id,
            "task_description": self.task_description,
            "original_message_count": self.original_message_count,
            "original_token_count": self.original_token_count,
            "compression_mode": self.compression_mode.value,
            "target_tokens": self.target_tokens,
            "compressed_message_count": self.compressed_message_count,
            "compressed_token_count": self.compressed_token_count,
            "retained_message_ids": self.retained_message_ids,
            "removed_message_ids": self.removed_message_ids,
            "summarized_message_ids": self.summarized_message_ids,
            "value_retention_rate": self.value_retention_rate,
            "outcome": self.outcome.value if self.outcome else None,
            "outcome_timestamp": self.outcome_timestamp,
            "quality_rating": self.quality_rating.value if self.quality_rating else None,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompressionEvent:
        return cls(
            event_id=data["event_id"],
            timestamp=data["timestamp"],
            task_id=data["task_id"],
            task_description=data["task_description"],
            original_message_count=data["original_message_count"],
            original_token_count=data["original_token_count"],
            compression_mode=CompressionMode(data["compression_mode"]),
            target_tokens=data["target_tokens"],
            compressed_message_count=data["compressed_message_count"],
            compressed_token_count=data["compressed_token_count"],
            retained_message_ids=data["retained_message_ids"],
            removed_message_ids=data["removed_message_ids"],
            summarized_message_ids=data["summarized_message_ids"],
            value_retention_rate=data["value_retention_rate"],
            outcome=TaskOutcome(data["outcome"]) if data.get("outcome") else None,
            outcome_timestamp=data.get("outcome_timestamp"),
            quality_rating=(
                CompressionQuality(data["quality_rating"]) if data.get("quality_rating") else None
            ),
            error_message=data.get("error_message"),
        )


@dataclass
class CompressionStatistics:
    """Statistics about compression performance."""

    total_compressions: int = 0
    completed_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0

    # Token efficiency
    total_tokens_saved: int = 0
    average_compression_ratio: float = 0.0

    # Quality metrics
    average_quality_rating: float = 0.0
    success_rate_by_mode: dict[str, tuple[int, int]] = field(
        default_factory=dict
    )  # (success, total)

    # Learning metrics
    value_retention_correlation: float = 0.0  # Correlation between value retention and success

    def record_completion(self, event: CompressionEvent) -> None:
        """Record a task completion."""
        self.completed_tasks += 1

        if event.outcome == TaskOutcome.SUCCESS:
            self.successful_tasks += 1
        elif event.outcome == TaskOutcome.FAILURE:
            self.failed_tasks += 1

        # Update mode-specific stats
        mode = event.compression_mode.value
        if mode not in self.success_rate_by_mode:
            self.success_rate_by_mode[mode] = (0, 0)

        success, total = self.success_rate_by_mode[mode]
        if event.outcome == TaskOutcome.SUCCESS:
            success += 1
        self.success_rate_by_mode[mode] = (success, total + 1)

    def get_mode_success_rate(self, mode: CompressionMode) -> float:
        """Get success rate for a compression mode."""
        success, total = self.success_rate_by_mode.get(mode.value, (0, 0))
        return success / total if total > 0 else 0.5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CompressionFeedbackLoop:
    """MemPO-style feedback loop for compression quality learning.

    Tracks the outcomes of compressed contexts and learns which
    compression strategies work best for different task types.

    Key insight from MemPO: The quality of memory (compression)
    should be judged by its contribution to task success.
    """

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path
        self.events: dict[str, CompressionEvent] = {}  # event_id -> event
        self.pending_events: dict[str, CompressionEvent] = {}  # task_id -> event
        self.statistics = CompressionStatistics()
        self.value_estimator = MemoryValueEstimator()

        # Strategy adaptation state
        self.mode_effectiveness: dict[str, list[float]] = defaultdict(list)
        self.task_type_patterns: dict[str, dict[str, Any]] = defaultdict(dict)

        # Load persisted data if available
        if storage_path:
            self._load()

    def record_compression(
        self,
        result: TaskAwareCompressionResult,
        task_description: str,
        task_id: Optional[str] = None,
    ) -> str:
        """Record that compression occurred before task execution.

        Returns event_id which should be used to record outcome later.
        """
        event_id = str(uuid.uuid4())
        task_id = task_id or event_id

        event = CompressionEvent(
            event_id=event_id,
            timestamp=time.time(),
            task_id=task_id,
            task_description=task_description,
            original_message_count=result.original_messages,
            original_token_count=result.original_tokens,
            compression_mode=result.compression_mode,
            target_tokens=result.compressed_tokens,  # Target was achieved
            compressed_message_count=result.retained_messages
            + (result.original_messages - result.retained_messages - result.removed_messages),
            compressed_token_count=result.compressed_tokens,
            retained_message_ids=[d.message_id for d in result.decisions if d.retained],
            removed_message_ids=[d.message_id for d in result.decisions if not d.retained],
            summarized_message_ids=[
                d.message_id for d in result.decisions if d.compression_action == "summarize"
            ],
            value_retention_rate=result.value_retention_rate,
        )

        self.events[event_id] = event
        self.pending_events[task_id] = event
        self.statistics.total_compressions += 1

        # Calculate tokens saved
        tokens_saved = result.original_tokens - result.compressed_tokens
        self.statistics.total_tokens_saved += tokens_saved

        self._save()
        return event_id

    def record_outcome(
        self,
        event_id_or_task_id: str,
        outcome: TaskOutcome,
        error_message: Optional[str] = None,
        quality_hint: Optional[CompressionQuality] = None,
    ) -> CompressionEvent:
        """Record the outcome of a compressed task.

        This is where the learning happens - we correlate compression
        decisions with task outcomes to improve future compression.
        """
        # Find event by ID or task ID
        event = self.events.get(event_id_or_task_id)
        if not event:
            event = self.pending_events.get(event_id_or_task_id)

        if not event:
            raise ValueError(f"No pending event found for ID: {event_id_or_task_id}")

        # Update event
        event.outcome = outcome
        event.outcome_timestamp = time.time()
        event.error_message = error_message

        # Calculate quality rating
        if quality_hint:
            event.quality_rating = quality_hint
        else:
            event.quality_rating = self._calculate_quality(event)

        # Update statistics
        self.statistics.record_completion(event)

        # Learn from this outcome
        self._learn_from_event(event)

        # Clean up pending
        if event.task_id in self.pending_events:
            del self.pending_events[event.task_id]

        self._save()
        return event

    def _calculate_quality(self, event: CompressionEvent) -> CompressionQuality:
        """Calculate quality rating based on outcome and metrics."""
        if event.outcome == TaskOutcome.SUCCESS:
            if event.value_retention_rate > 0.8:
                return CompressionQuality.EXCELLENT
            elif event.value_retention_rate > 0.6:
                return CompressionQuality.GOOD
            else:
                return CompressionQuality.FAIR
        elif event.outcome == TaskOutcome.PARTIAL_SUCCESS:
            return CompressionQuality.FAIR
        elif event.outcome == TaskOutcome.FAILURE:
            if event.value_retention_rate < 0.4:
                return CompressionQuality.BAD
            else:
                return CompressionQuality.POOR
        else:
            return CompressionQuality.FAIR

    def _learn_from_event(self, event: CompressionEvent) -> None:
        """Learn from a completed compression event.

        This implements the MemPO-style learning: update our understanding
        of which messages are valuable based on task outcomes.
        """
        success = event.outcome == TaskOutcome.SUCCESS

        # Update mode effectiveness
        mode = event.compression_mode.value
        quality_score = event.quality_rating.value if event.quality_rating else 3
        self.mode_effectiveness[mode].append(quality_score)

        # Keep only recent history
        if len(self.mode_effectiveness[mode]) > 100:
            self.mode_effectiveness[mode] = self.mode_effectiveness[mode][-100:]

        # Learn about retained messages
        for msg_id in event.retained_message_ids:
            self.value_estimator.record_outcome(
                message_id=msg_id,
                task_id=event.task_id,
                success=success,
                contribution=1.0 if success else 0.5,
            )

        # Learn about removed messages (negative signal if task failed)
        if not success:
            for msg_id in event.removed_message_ids:
                self.value_estimator.record_outcome(
                    message_id=msg_id,
                    task_id=event.task_id,
                    success=False,
                    contribution=0.5,  # May have contributed to failure
                )

        # Update task type patterns
        task_type = self._infer_task_type(event.task_description)
        self._update_task_patterns(task_type, event)

    def _infer_task_type(self, description: str) -> str:
        """Infer task type from description."""
        desc_lower = description.lower()

        keywords = {
            "debug": ["debug", "fix", "error", "bug", "issue", "broken"],
            "feature": ["implement", "add", "create", "build", "feature"],
            "refactor": ["refactor", "clean", "reorganize", "restructure"],
            "review": ["review", "check", "analyze", "examine"],
            "test": ["test", "verify", "validate", "assert"],
            "docs": ["document", "comment", "readme", "doc"],
        }

        for task_type, words in keywords.items():
            if any(w in desc_lower for w in words):
                return task_type

        return "general"

    def _update_task_patterns(self, task_type: str, event: CompressionEvent) -> None:
        """Update learned patterns for task types."""
        if task_type not in self.task_type_patterns:
            self.task_type_patterns[task_type] = {
                "optimal_mode": event.compression_mode.value,
                "min_value_retention": event.value_retention_rate,
                "success_count": 0,
                "total_count": 0,
            }

        pattern = self.task_type_patterns[task_type]
        pattern["total_count"] += 1

        if event.outcome == TaskOutcome.SUCCESS:
            pattern["success_count"] += 1
            # Update optimal mode if this was successful
            pattern["optimal_mode"] = event.compression_mode.value
            pattern["min_value_retention"] = min(
                pattern["min_value_retention"],
                event.value_retention_rate,
            )

    def get_recommended_mode(self, task_description: str) -> CompressionMode:
        """Get recommended compression mode for a task type."""
        task_type = self._infer_task_type(task_description)
        pattern = self.task_type_patterns.get(task_type)

        if pattern and pattern["total_count"] >= 5:
            # Use learned optimal mode
            try:
                return CompressionMode(pattern["optimal_mode"])
            except ValueError:
                pass

        # Fallback: use mode with best recent success rate
        best_mode = CompressionMode.MODERATE
        best_score = 0.0

        for mode in CompressionMode:
            scores = self.mode_effectiveness.get(mode.value, [])
            if scores:
                avg_score = sum(scores[-20:]) / len(scores[-20:])
                if avg_score > best_score:
                    best_score = avg_score
                    best_mode = mode

        return best_mode

    def get_value_retention_target(self, task_description: str) -> float:
        """Get target value retention rate for a task type."""
        task_type = self._infer_task_type(task_description)
        pattern = self.task_type_patterns.get(task_type)

        if pattern and pattern["total_count"] >= 3:
            # Target slightly above minimum successful retention
            return max(0.5, pattern["min_value_retention"] * 0.9)

        return 0.7  # Default target

    def get_compression_report(self) -> dict[str, Any]:
        """Get comprehensive compression performance report."""
        recent_events = [
            e
            for e in self.events.values()
            if e.outcome_timestamp and e.outcome_timestamp > time.time() - 7 * 24 * 3600
        ]

        return {
            "statistics": self.statistics.to_dict(),
            "mode_effectiveness": {
                mode: sum(scores) / len(scores) if scores else 0
                for mode, scores in self.mode_effectiveness.items()
            },
            "task_type_patterns": self.task_type_patterns,
            "recent_performance": {
                "completions": len(recent_events),
                "success_rate": (
                    sum(1 for e in recent_events if e.outcome == TaskOutcome.SUCCESS)
                    / len(recent_events)
                    if recent_events
                    else 0
                ),
                "average_quality": (
                    sum(e.quality_rating.value for e in recent_events if e.quality_rating)
                    / len(recent_events)
                    if recent_events
                    else 0
                ),
            },
            "pending_tasks": len(self.pending_events),
        }

    def _save(self) -> None:
        """Persist feedback data."""
        if not self.storage_path:
            return

        try:
            data = {
                "events": {k: v.to_dict() for k, v in self.events.items()},
                "statistics": self.statistics.to_dict(),
                "mode_effectiveness": dict(self.mode_effectiveness),
                "task_type_patterns": dict(self.task_type_patterns),
            }
            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass  # Fail silently

    def _load(self) -> None:
        """Load persisted feedback data."""
        try:
            with open(self.storage_path, "r") as f:
                data = json.load(f)

            self.events = {
                k: CompressionEvent.from_dict(v) for k, v in data.get("events", {}).items()
            }

            stats_data = data.get("statistics", {})
            self.statistics = CompressionStatistics(**stats_data)

            self.mode_effectiveness = defaultdict(list, data.get("mode_effectiveness", {}))
            self.task_type_patterns = defaultdict(dict, data.get("task_type_patterns", {}))

        except Exception:
            pass  # Fail silently, start fresh


class CompressionQualityMonitor:
    """Real-time monitor for compression quality during agent execution.

    Allows the agent to provide feedback about compression quality
    based on its actual experience using the compressed context.
    """

    def __init__(self, feedback_loop: CompressionFeedbackLoop):
        self.feedback_loop = feedback_loop
        self.current_event_id: Optional[str] = None
        self.messages_accessed: set[str] = set()
        self.messages_missing: set[str] = set()
        self.compression_helpfulness: float = 0.5  # Neutral start

    def start_task(self, event_id: str) -> None:
        """Start monitoring a task."""
        self.current_event_id = event_id
        self.messages_accessed.clear()
        self.messages_missing.clear()
        self.compression_helpfulness = 0.5

    def record_access(self, message_id: str, found: bool = True) -> None:
        """Record that the agent tried to access a message."""
        if found:
            self.messages_accessed.add(message_id)
        else:
            self.messages_missing.add(message_id)

    def report_helpfulness(self, score: float) -> None:
        """Report how helpful the compressed context was (0-1)."""
        self.compression_helpfulness = score

    def complete_task(
        self,
        outcome: TaskOutcome,
        error_message: Optional[str] = None,
    ) -> CompressionEvent:
        """Complete the task and record outcome."""
        if not self.current_event_id:
            raise ValueError("No active task to complete")

        # Infer quality from helpfulness and access patterns
        quality = self._infer_quality(outcome)

        return self.feedback_loop.record_outcome(
            event_id_or_task_id=self.current_event_id,
            outcome=outcome,
            error_message=error_message,
            quality_hint=quality,
        )

    def _infer_quality(self, outcome: TaskOutcome) -> CompressionQuality:
        """Infer quality from monitoring data."""
        # If many messages were missing, compression was too aggressive
        missing_ratio = len(self.messages_missing) / max(
            1, len(self.messages_accessed) + len(self.messages_missing)
        )

        if outcome == TaskOutcome.SUCCESS:
            if missing_ratio < 0.1 and self.compression_helpfulness > 0.7:
                return CompressionQuality.EXCELLENT
            elif missing_ratio < 0.2:
                return CompressionQuality.GOOD
            else:
                return CompressionQuality.FAIR
        elif outcome == TaskOutcome.FAILURE:
            if missing_ratio > 0.3:
                return CompressionQuality.BAD
            else:
                return CompressionQuality.POOR

        return CompressionQuality.FAIR


# Global feedback loop instance
_default_feedback_loop: Optional[CompressionFeedbackLoop] = None


def get_compression_feedback_loop(storage_path: Optional[str] = None) -> CompressionFeedbackLoop:
    """Get global compression feedback loop."""
    global _default_feedback_loop
    if _default_feedback_loop is None:
        _default_feedback_loop = CompressionFeedbackLoop(storage_path)
    return _default_feedback_loop


def reset_compression_feedback_loop() -> None:
    """Reset global feedback loop."""
    global _default_feedback_loop
    _default_feedback_loop = None
