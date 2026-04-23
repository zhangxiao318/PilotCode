"""Adaptive Context Manager - MemPO-inspired intelligent context management.

This module integrates all MemPO-style optimizations:
1. Memory value estimation
2. Task-aware compression
3. Compression feedback learning
4. Hierarchical memory architecture

Provides an intelligent, learning context manager that adapts to task complexity
and learns from outcomes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum

from pydantic import Field

from .context_manager import ContextManager, ContextConfig, ContextMessage, MessagePriority
from .memory_value import MemoryValueEstimator, MessageValueScore
from .task_aware_compression import (
    TaskAwareCompressor,
    TaskContext,
    CompressionMode,
    TaskAwareCompressionResult,
)
from .compression_feedback import CompressionFeedbackLoop, CompressionQualityMonitor, TaskOutcome
from .hierarchical_memory import HierarchicalMemory


class TaskComplexity(Enum):
    """Task complexity levels."""

    SIMPLE = "simple"  # Quick tasks, single step
    MEDIUM = "medium"  # Moderate complexity, few steps
    COMPLEX = "complex"  # Complex, many steps
    VERY_COMPLEX = "very_complex"  # Very complex, long-running


class AdaptiveContextConfig(ContextConfig):
    """Configuration for adaptive context manager."""

    # Task complexity thresholds
    simple_task_tokens: int = Field(default=4000)
    medium_task_tokens: int = Field(default=8000)
    complex_task_tokens: int = Field(default=12000)

    # Adaptive compression
    enable_value_estimation: bool = Field(default=True)
    enable_task_aware_compression: bool = Field(default=True)
    enable_feedback_learning: bool = Field(default=True)
    enable_hierarchical_memory: bool = Field(default=True)

    # Feedback storage
    feedback_storage_path: Optional[str] = Field(default=None)
    memory_storage_path: Optional[str] = Field(default=None)

    # Learning parameters
    min_feedback_before_adaptation: int = Field(default=5)
    exploration_rate: float = Field(default=0.1)  # Probability of trying different strategy

    # MemPO-style retention targets
    value_retention_target: float = Field(default=0.75)


@dataclass
class CompressionDecision:
    """Record of a compression decision."""

    timestamp: float
    original_tokens: int
    compressed_tokens: int
    strategy_used: str
    value_retention: float
    trigger_reason: str


@dataclass
class AdaptiveContextStats:
    """Statistics for adaptive context management."""

    total_compressions: int = 0
    total_tokens_saved: int = 0
    avg_value_retention: float = 0.0
    successful_tasks: int = 0
    failed_tasks: int = 0
    compression_history: list[CompressionDecision] = field(default_factory=list)

    def record_compression(self, decision: CompressionDecision) -> None:
        """Record a compression event."""
        self.total_compressions += 1
        self.total_tokens_saved += decision.original_tokens - decision.compressed_tokens
        self.compression_history.append(decision)

        # Keep only recent history
        if len(self.compression_history) > 100:
            self.compression_history = self.compression_history[-100:]

        # Update average
        retentions = [d.value_retention for d in self.compression_history]
        self.avg_value_retention = sum(retentions) / len(retentions)

    def record_task_outcome(self, success: bool) -> None:
        """Record task outcome."""
        if success:
            self.successful_tasks += 1
        else:
            self.failed_tasks += 1


class AdaptiveContextManager(ContextManager):
    """Adaptive context manager with MemPO-style optimizations.

    Features:
    - Task-aware compression that preserves high-value information
    - Learning from compression outcomes
    - Hierarchical memory for long-term context retention
    - Dynamic adaptation to task complexity

    This is the main integration point for all MemPO-style improvements.
    """

    def __init__(self, config: Optional[AdaptiveContextConfig] = None):
        # Initialize base ContextManager
        super().__init__(config or AdaptiveContextConfig())

        self.adaptive_config = config or AdaptiveContextConfig()

        # Initialize subsystems
        self.value_estimator = MemoryValueEstimator()
        self.task_compressor = TaskAwareCompressor()
        self.feedback_loop = CompressionFeedbackLoop(
            storage_path=self.adaptive_config.feedback_storage_path
        )
        self.quality_monitor: Optional[CompressionQualityMonitor] = None
        self.hierarchical_memory: Optional[HierarchicalMemory] = None

        if self.adaptive_config.enable_hierarchical_memory:
            self.hierarchical_memory = HierarchicalMemory(
                storage_path=self.adaptive_config.memory_storage_path
            )

        # State
        self.current_task_id: Optional[str] = None
        self.current_task_description: str = ""
        self.current_task_complexity: TaskComplexity = TaskComplexity.MEDIUM
        self.current_files: list[str] = []
        self.adaptive_stats = AdaptiveContextStats()
        self.last_compression_result: Optional[TaskAwareCompressionResult] = None

        # Start hierarchical memory episode
        if self.hierarchical_memory:
            self.hierarchical_memory.start_episode()

    def set_task_context(
        self,
        description: str,
        task_type: str = "general",
        current_files: Optional[list[str]] = None,
        task_id: Optional[str] = None,
    ) -> None:
        """Set the current task context for intelligent compression."""
        self.current_task_id = task_id or f"task_{int(time.time())}"
        self.current_task_description = description
        self.current_files = current_files or []

        # Estimate task complexity
        self.current_task_complexity = self._estimate_complexity(description, task_type)

        # Adjust token budget based on complexity
        self._adapt_budget_to_complexity()

        # Create quality monitor for this task
        self.quality_monitor = CompressionQualityMonitor(self.feedback_loop)

        # Retrieve relevant historical context
        if self.hierarchical_memory:
            self._inject_relevant_history(description)

    def _estimate_complexity(self, description: str, task_type: str) -> TaskComplexity:
        """Estimate task complexity from description and type."""
        desc_lower = description.lower()

        # Check for complexity indicators
        complex_indicators = [
            "implement",
            "refactor",
            "architect",
            "design",
            "optimize",
            "multiple",
            "complex",
            "integration",
            "migration",
        ]
        simple_indicators = [
            "explain",
            "show",
            "what is",
            "how to",
            "review",
            "check",
        ]

        complex_score = sum(1 for w in complex_indicators if w in desc_lower)
        simple_score = sum(1 for w in simple_indicators if w in desc_lower)

        # Consider task type
        type_complexity = {
            "debug": TaskComplexity.MEDIUM,
            "feature": TaskComplexity.COMPLEX,
            "refactor": TaskComplexity.COMPLEX,
            "review": TaskComplexity.SIMPLE,
            "explain": TaskComplexity.SIMPLE,
            "fix": TaskComplexity.MEDIUM,
        }
        base_complexity = type_complexity.get(task_type, TaskComplexity.MEDIUM)

        # Adjust based on indicators
        if complex_score > 2:
            if base_complexity == TaskComplexity.COMPLEX:
                return TaskComplexity.VERY_COMPLEX
            return TaskComplexity.COMPLEX
        elif simple_score > 1:
            if base_complexity == TaskComplexity.SIMPLE:
                return TaskComplexity.SIMPLE
            return TaskComplexity.MEDIUM

        return base_complexity

    def _adapt_budget_to_complexity(self) -> None:
        """Adapt token budget based on task complexity."""
        budget_map = {
            TaskComplexity.SIMPLE: self.adaptive_config.simple_task_tokens,
            TaskComplexity.MEDIUM: self.adaptive_config.medium_task_tokens,
            TaskComplexity.COMPLEX: self.adaptive_config.complex_task_tokens,
            TaskComplexity.VERY_COMPLEX: self.adaptive_config.complex_task_tokens,
        }

        new_budget = budget_map.get(
            self.current_task_complexity, self.adaptive_config.context_window
        )

        # Update budget - warning_limit and critical_limit are computed from context_window
        self.budget.context_window = new_budget

    def _inject_relevant_history(self, query: str) -> None:
        """Inject relevant historical context into working memory."""
        if not self.hierarchical_memory:
            return

        # Retrieve relevant context
        retrieved = self.hierarchical_memory.retrieve_context(query)

        # Format for prompt
        context_text = self.hierarchical_memory.format_context_for_prompt(
            retrieved, max_tokens=1500
        )

        if context_text:
            # Add as system context message
            context_msg = ContextMessage(
                role="system",
                content=f"[Relevant previous context]\n{context_text}",
                priority=MessagePriority.SYSTEM,
                metadata={"type": "historical_context"},
            )

            # Insert after any existing system message
            if self.messages and self.messages[0].role == "system":
                self.messages.insert(1, context_msg)
            else:
                self.messages.insert(0, context_msg)

            self._update_stats()

    def add_message(
        self,
        role: str,
        content: str,
        priority: Optional[MessagePriority] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ContextMessage:
        """Add a message with adaptive context management."""
        # Call parent method
        message = super().add_message(role, content, priority, metadata)

        # Also add to hierarchical memory
        if self.hierarchical_memory:
            self.hierarchical_memory.add_to_working(message)

        # Check if we should compress
        if self.is_critical and self.adaptive_config.enable_task_aware_compression:
            self.adaptive_compact()

        return message

    def adaptive_compact(self) -> TaskAwareCompressionResult:
        """Perform adaptive compression based on task context.

        This is the core MemPO-style compression that:
        1. Estimates value of each message
        2. Selectively retains high-value messages
        3. Records compression for feedback learning
        """
        if not self.current_task_description:
            # Fall back to standard compression
            self.compact()
            return TaskAwareCompressionResult(
                original_messages=len(self.messages),
                retained_messages=len(self.messages),
                summarized_messages=0,
                removed_messages=0,
                original_tokens=self.stats.total_tokens,
                compressed_tokens=self.stats.total_tokens,
                value_retention_rate=1.0,
            )

        # Create task context
        task_context = TaskContext(
            description=self.current_task_description,
            current_files=self.current_files,
            task_type=self._infer_task_type(self.current_task_description),
            complexity=self.current_task_complexity.value,
        )

        # Get recommended compression mode from feedback
        recommended_mode = self.feedback_loop.get_recommended_mode(self.current_task_description)

        # Get value retention target
        self.feedback_loop.get_value_retention_target(self.current_task_description)

        # Calculate target tokens based on mode
        target_ratio = {
            CompressionMode.LIGHT: 0.8,
            CompressionMode.MODERATE: 0.6,
            CompressionMode.AGGRESSIVE: 0.4,
            CompressionMode.EMERGENCY: 0.2,
        }.get(recommended_mode, 0.6)

        target_tokens = int(self.budget.context_window * target_ratio)

        # Perform task-aware compression
        result = self.task_compressor.compress_with_task_context(
            messages=self.messages,
            task_context=task_context,
            target_tokens=target_tokens,
            preserve_recent=self.config.preserve_recent,
        )

        # Update messages
        retained_ids = {d.message_id for d in result.decisions if d.retained}

        # Always keep recent messages
        preserve_count = self.config.preserve_recent * 2
        recent_ids = (
            {m.id for m in self.messages[-preserve_count:]}
            if len(self.messages) > preserve_count
            else set()
        )

        # Build new message list
        new_messages = []
        for msg in self.messages:
            if (
                msg.id in recent_ids
                or msg.id in retained_ids
                or msg.priority == MessagePriority.SYSTEM
            ):
                new_messages.append(msg)

        self.messages = new_messages
        self._update_stats()

        # Record compression for feedback
        if self.adaptive_config.enable_feedback_learning:
            event_id = self.feedback_loop.record_compression(
                result=result,
                task_description=self.current_task_description,
                task_id=self.current_task_id,
            )

            if self.quality_monitor:
                self.quality_monitor.start_task(event_id)

        # Update statistics
        decision = CompressionDecision(
            timestamp=time.time(),
            original_tokens=result.original_tokens,
            compressed_tokens=result.compressed_tokens,
            strategy_used=result.compression_mode.value,
            value_retention=result.value_retention_rate,
            trigger_reason="critical_threshold",
        )
        self.adaptive_stats.record_compression(decision)

        self.last_compression_result = result

        return result

    def _infer_task_type(self, description: str) -> str:
        """Infer task type from description."""
        desc_lower = description.lower()

        if any(w in desc_lower for w in ["debug", "fix", "error", "bug"]):
            return "debug"
        elif any(w in desc_lower for w in ["implement", "add", "create", "build"]):
            return "feature"
        elif any(w in desc_lower for w in ["refactor", "clean", "restructure"]):
            return "refactor"
        elif any(w in desc_lower for w in ["review", "check", "analyze"]):
            return "review"
        elif any(w in desc_lower for w in ["test", "verify", "validate"]):
            return "test"

        return "general"

    def record_task_outcome(
        self,
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """Record the outcome of the current task.

        This is crucial for MemPO-style learning - we correlate
        compression decisions with task outcomes.
        """
        outcome = TaskOutcome.SUCCESS if success else TaskOutcome.FAILURE

        # Record in feedback loop
        if self.quality_monitor:
            self.quality_monitor.complete_task(outcome, error_message)
        elif self.last_compression_result and self.current_task_id:
            self.feedback_loop.record_outcome(
                event_id_or_task_id=self.current_task_id,
                outcome=outcome,
                error_message=error_message,
            )

        # Update hierarchical memory
        if self.hierarchical_memory:
            if success:
                # Generate episode snapshot
                try:
                    snapshot = self.hierarchical_memory.end_episode()

                    # Positive feedback on episode utility
                    self.hierarchical_memory.feedback_episode_utility(snapshot.episode_id, True)
                except ValueError:
                    pass  # No messages to snapshot
            else:
                # Negative feedback on recent episodes
                if self.hierarchical_memory.episodic.episodes:
                    recent = self.hierarchical_memory.episodic.episodes[-1]
                    self.hierarchical_memory.feedback_episode_utility(recent.episode_id, False)

        # Update statistics
        self.adaptive_stats.record_task_outcome(success)

        # Reset for next task
        self.current_task_id = None
        self.current_task_description = ""
        self.quality_monitor = None
        self.last_compression_result = None

        # Start new episode
        if self.hierarchical_memory:
            self.hierarchical_memory.start_episode()

    def get_message_value_scores(self) -> list[MessageValueScore]:
        """Get value scores for all messages."""
        if not self.current_task_description:
            return []

        return self.value_estimator.batch_estimate(
            self.messages,
            self.current_task_description,
            self.current_files,
        )

    def get_adaptive_stats(self) -> dict[str, Any]:
        """Get adaptive context management statistics."""
        feedback_report = self.feedback_loop.get_compression_report()

        return {
            "adaptive_stats": {
                "total_compressions": self.adaptive_stats.total_compressions,
                "total_tokens_saved": self.adaptive_stats.total_tokens_saved,
                "avg_value_retention": self.adaptive_stats.avg_value_retention,
                "task_success_rate": (
                    self.adaptive_stats.successful_tasks
                    / max(
                        1, self.adaptive_stats.successful_tasks + self.adaptive_stats.failed_tasks
                    )
                ),
            },
            "current_task": {
                "task_id": self.current_task_id,
                "complexity": (
                    self.current_task_complexity.value if self.current_task_complexity else None
                ),
                "description_preview": (
                    self.current_task_description[:100] if self.current_task_description else None
                ),
            },
            "feedback_report": feedback_report,
            "hierarchical_memory": (
                self.hierarchical_memory.get_stats() if self.hierarchical_memory else None
            ),
        }

    def get_messages_with_scores(
        self,
        include_scores: bool = True,
    ) -> list[dict[str, Any]]:
        """Get messages with their value scores."""
        scores_map = {}

        if include_scores and self.current_task_description:
            scores = self.get_message_value_scores()
            scores_map = {s.message_id: s for s in scores}

        result = []
        for msg in self.messages:
            msg_dict = {
                "role": msg.role,
                "content": msg.content,
                "priority": msg.priority.value,
                "tokens": msg.tokens,
            }

            if msg.id in scores_map:
                score = scores_map[msg.id]
                msg_dict["value_score"] = {
                    "total": score.total_score,
                    "info_density": score.info_density,
                    "task_relevance": score.task_relevance,
                    "historical_utility": score.historical_utility,
                }

            result.append(msg_dict)

        return result

    def force_compact(
        self, mode: CompressionMode = CompressionMode.MODERATE
    ) -> TaskAwareCompressionResult:
        """Force compression with specific mode."""
        # Temporarily set budget to trigger compression
        original_max = self.budget.context_window
        self.budget.context_window = int(self.stats.total_tokens * 0.5)

        result = self.adaptive_compact()

        self.budget.context_window = original_max
        return result

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        base = super().to_dict()
        base["adaptive_config"] = {
            "simple_task_tokens": self.adaptive_config.simple_task_tokens,
            "medium_task_tokens": self.adaptive_config.medium_task_tokens,
            "complex_task_tokens": self.adaptive_config.complex_task_tokens,
            "enable_value_estimation": self.adaptive_config.enable_value_estimation,
            "enable_task_aware_compression": self.adaptive_config.enable_task_aware_compression,
            "enable_feedback_learning": self.adaptive_config.enable_feedback_learning,
            "enable_hierarchical_memory": self.adaptive_config.enable_hierarchical_memory,
        }
        base["adaptive_stats"] = {
            "total_compressions": self.adaptive_stats.total_compressions,
            "total_tokens_saved": self.adaptive_stats.total_tokens_saved,
            "avg_value_retention": self.adaptive_stats.avg_value_retention,
        }
        return base


# Global instance management
_default_adaptive_manager: Optional[AdaptiveContextManager] = None


def get_adaptive_context_manager(
    config: Optional[AdaptiveContextConfig] = None,
) -> AdaptiveContextManager:
    """Get or create global adaptive context manager instance."""
    global _default_adaptive_manager
    if _default_adaptive_manager is None:
        _default_adaptive_manager = AdaptiveContextManager(config)
    return _default_adaptive_manager


def reset_adaptive_context_manager() -> None:
    """Clear the global adaptive context manager instance."""
    global _default_adaptive_manager
    _default_adaptive_manager = None


def create_adaptive_context_manager(
    config: Optional[AdaptiveContextConfig] = None,
) -> AdaptiveContextManager:
    """Create a new adaptive context manager (not global)."""
    return AdaptiveContextManager(config)
