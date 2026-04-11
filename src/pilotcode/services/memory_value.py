"""Memory value estimation - MemPO-style information value scoring.

This module implements:
1. Information density calculation for messages
2. Task relevance scoring
3. Historical utility tracking
4. Combined memory value estimation (MemPO-style advantage estimation)
"""

from __future__ import annotations

import re
import math
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from collections import defaultdict
from enum import Enum


from .context_manager import ContextMessage


class MemoryValueComponent(float, Enum):
    """Components of memory value estimation."""

    INFO_DENSITY = 0.4  # Information density weight
    TASK_RELEVANCE = 0.4  # Task relevance weight
    HISTORICAL_UTILITY = 0.2  # Historical utility weight


@dataclass
class FeedbackRecord:
    """A feedback record for memory utility learning."""

    message_id: str
    task_id: str
    success: bool
    contribution_score: float  # How much this message contributed to success
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MessageValueScore:
    """Complete value score for a message."""

    message_id: str
    total_score: float
    info_density: float
    task_relevance: float
    historical_utility: float
    recency_boost: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "total_score": self.total_score,
            "info_density": self.info_density,
            "task_relevance": self.task_relevance,
            "historical_utility": self.historical_utility,
            "recency_boost": self.recency_boost,
            "timestamp": self.timestamp,
        }


class InformationDensityCalculator:
    """Calculate information density of message content."""

    # High-value keywords in code/technical contexts
    TECH_KEYWORDS = {
        "error",
        "exception",
        "fix",
        "bug",
        "solution",
        "resolved",
        "implemented",
        "created",
        "modified",
        "refactored",
        "optimized",
        "function",
        "class",
        "method",
        "api",
        "endpoint",
        "database",
        "config",
        "setting",
        "parameter",
        "argument",
        "return",
        "import",
        "export",
        "module",
        "package",
        "dependency",
        "test",
        "assert",
        "verify",
        "validate",
        "check",
        "async",
        "await",
        "promise",
        "callback",
        "event",
    }

    # File path patterns (high information value)
    FILE_PATTERN = re.compile(r"[\w\-./\\]+\.(py|js|ts|java|go|rs|cpp|c|h|json|yaml|yml|md|txt)")

    def calculate(self, content: str) -> float:
        """Calculate information density score (0-1).

        Higher score means more information per character.
        """
        if not content:
            return 0.0

        scores = []

        # 1. Keyword density
        keyword_score = self._keyword_density(content)
        scores.append(keyword_score)

        # 2. File reference density
        file_score = self._file_reference_density(content)
        scores.append(file_score)

        # 3. Structural information (code blocks, lists)
        structure_score = self._structural_density(content)
        scores.append(structure_score)

        # 4. Content uniqueness (lower redundancy)
        uniqueness_score = self._uniqueness_score(content)
        scores.append(uniqueness_score)

        # Weighted average
        weights = [0.3, 0.3, 0.2, 0.2]
        final_score = sum(s * w for s, w in zip(scores, weights))

        return min(1.0, max(0.0, final_score))

    def _keyword_density(self, content: str) -> float:
        """Calculate technical keyword density."""
        content_lower = content.lower()
        words = set(re.findall(r"\b\w+\b", content_lower))

        if not words:
            return 0.0

        tech_matches = words & self.TECH_KEYWORDS
        # Normalize: expect 5-15% tech keywords for high density
        density = len(tech_matches) / len(words)
        return min(1.0, density * 10)  # Scale up

    def _file_reference_density(self, content: str) -> float:
        """Calculate file path reference density."""
        file_refs = self.FILE_PATTERN.findall(content)
        if not file_refs:
            return 0.0

        # More unique file refs = higher density
        unique_refs = len(set(file_refs))
        total_lines = content.count("\n") + 1

        if total_lines == 0:
            return 0.0

        density = unique_refs / total_lines
        return min(1.0, density * 5)  # Scale factor

    def _structural_density(self, content: str) -> float:
        """Calculate structural information density."""
        scores = []

        # Code blocks
        code_blocks = content.count("```")
        scores.append(min(1.0, code_blocks / 2))

        # Bullet points / lists
        list_items = len(re.findall(r"^[\s]*[-*+][\s]", content, re.MULTILINE))
        scores.append(min(1.0, list_items / 5))

        # Numbered steps
        numbered_items = len(re.findall(r"^[\s]*\d+\.", content, re.MULTILINE))
        scores.append(min(1.0, numbered_items / 3))

        # Key-value pairs (config-like)
        kv_pairs = len(re.findall(r"\w+[\s]*[=:][\s]*\w+", content))
        scores.append(min(1.0, kv_pairs / 5))

        return sum(scores) / len(scores) if scores else 0.0

    def _uniqueness_score(self, content: str) -> float:
        """Calculate content uniqueness (lower repetition = higher score)."""
        lines = [line.strip() for line in content.split("\n") if line.strip()]
        if not lines:
            return 0.0

        unique_lines = len(set(lines))
        total_lines = len(lines)

        # Penalize highly repetitive content
        uniqueness_ratio = unique_lines / total_lines
        return uniqueness_ratio


class TaskRelevanceCalculator:
    """Calculate relevance of a message to current task."""

    def __init__(self):
        self._embedding_cache: dict[str, list[float]] = {}

    def calculate(
        self,
        message: ContextMessage,
        task_description: str,
        current_files: Optional[list[str]] = None,
    ) -> float:
        """Calculate task relevance score (0-1).

        Uses semantic similarity and keyword overlap.
        """
        if not task_description:
            return 0.5  # Neutral if no task context

        scores = []
        content = message.content or ""
        content_lower = content.lower()
        task_lower = task_description.lower()

        # 1. Keyword overlap
        keyword_score = self._keyword_overlap(content_lower, task_lower)
        scores.append(keyword_score)

        # 2. File context relevance
        if current_files:
            file_score = self._file_context_relevance(content, current_files)
            scores.append(file_score)

        # 3. Message type relevance
        type_score = self._message_type_relevance(message)
        scores.append(type_score)

        # 4. Intent alignment (action words)
        intent_score = self._intent_alignment(content_lower, task_lower)
        scores.append(intent_score)

        # Weighted combination
        weights = [0.35, 0.25 if current_files else 0, 0.2, 0.2]
        if not current_files:
            weights = [0.4, 0.0, 0.3, 0.3]

        total_weight = sum(weights)
        normalized_weights = [w / total_weight for w in weights]

        final_score = sum(s * w for s, w in zip(scores, normalized_weights))
        return min(1.0, max(0.0, final_score))

    def _keyword_overlap(self, content: str, task: str) -> float:
        """Calculate keyword overlap between content and task."""
        # Extract keywords (nouns/verbs, ignore stopwords)
        stopwords = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "can",
            "need",
            "dare",
            "ought",
            "used",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "and",
            "but",
            "or",
            "yet",
            "so",
            "if",
            "because",
            "although",
            "though",
            "while",
            "where",
            "when",
            "that",
            "which",
            "who",
            "whom",
            "whose",
            "what",
            "this",
            "these",
            "those",
            "i",
            "you",
            "he",
            "she",
            "it",
            "we",
            "they",
            "me",
            "him",
            "her",
            "us",
            "them",
        }

        content_words = set(re.findall(r"\b\w+\b", content)) - stopwords
        task_words = set(re.findall(r"\b\w+\b", task)) - stopwords

        if not task_words:
            return 0.5

        overlap = content_words & task_words
        # Jaccard similarity
        union = content_words | task_words
        if not union:
            return 0.0

        return len(overlap) / len(union)

    def _file_context_relevance(self, content: str, current_files: list[str]) -> float:
        """Calculate relevance based on file references."""
        score = 0.0
        content_lower = content.lower()

        for filepath in current_files:
            # Check for filename or path mention
            filename = filepath.split("/")[-1].lower()
            dirname = filepath.split("/")[-2].lower() if "/" in filepath else ""

            if filename in content_lower:
                score += 0.5
            if dirname and dirname in content_lower:
                score += 0.3
            if filepath.lower() in content_lower:
                score += 0.2

        return min(1.0, score)

    def _message_type_relevance(self, message: ContextMessage) -> float:
        """Base relevance by message type/role."""
        role_scores = {
            "system": 0.9,  # System messages are always important
            "user": 0.8,  # User requests are important
            "assistant": 0.6,  # Assistant responses vary
            "tool": 0.5,  # Tool results depend on context
        }
        return role_scores.get(message.role, 0.5)

    def _intent_alignment(self, content: str, task: str) -> float:
        """Calculate alignment of action intents."""
        # Action verbs indicating task progress
        action_verbs = {
            "create",
            "add",
            "implement",
            "build",
            "make",
            "fix",
            "repair",
            "solve",
            "resolve",
            "correct",
            "update",
            "modify",
            "change",
            "edit",
            "refactor",
            "test",
            "verify",
            "check",
            "validate",
            "ensure",
            "optimize",
            "improve",
            "enhance",
            "upgrade",
            "boost",
            "delete",
            "remove",
            "clean",
            "clear",
            "purge",
            "find",
            "search",
            "locate",
            "identify",
            "detect",
            "explain",
            "describe",
            "clarify",
            "document",
            "detail",
        }

        content_actions = set(re.findall(r"\b\w+\b", content)) & action_verbs
        task_actions = set(re.findall(r"\b\w+\b", task)) & action_verbs

        if not task_actions:
            return 0.5

        if not content_actions:
            return 0.3

        overlap = content_actions & task_actions
        return len(overlap) / len(task_actions) if task_actions else 0.5


class HistoricalUtilityTracker:
    """Track and learn historical utility of messages."""

    def __init__(self):
        self.feedback_history: list[FeedbackRecord] = []
        self.message_utility: dict[str, float] = defaultdict(float)
        self.message_usage_count: dict[str, int] = defaultdict(int)
        self.context_patterns: dict[str, list[bool]] = defaultdict(list)

    def record_feedback(self, record: FeedbackRecord) -> None:
        """Record feedback about message utility."""
        self.feedback_history.append(record)

        # Update running average for this message
        msg_id = record.message_id
        current = self.message_utility[msg_id]
        count = self.message_usage_count[msg_id]

        # Exponential moving average
        if count == 0:
            self.message_utility[msg_id] = record.contribution_score
        else:
            alpha = 0.3  # Learning rate
            self.message_utility[msg_id] = (1 - alpha) * current + alpha * record.contribution_score

        self.message_usage_count[msg_id] += 1

    def get_utility(self, message_id: str) -> float:
        """Get learned utility score for a message."""
        return self.message_utility.get(message_id, 0.5)  # Default neutral

    def extract_message_signature(self, message: ContextMessage) -> str:
        """Extract a signature for pattern matching similar messages."""
        # Use first 100 chars + role as signature
        content_preview = (message.content or "")[:100].lower()
        # Normalize: remove specific identifiers
        content_preview = re.sub(r"\d+", "N", content_preview)
        content_preview = re.sub(r'["\'][^"\']*["\']', '"..."', content_preview)
        return f"{message.role}:{content_preview}"

    def get_pattern_utility(self, message: ContextMessage) -> float:
        """Get utility based on similar messages' history."""
        signature = self.extract_message_signature(message)

        if signature not in self.context_patterns:
            return 0.5

        pattern_history = self.context_patterns[signature]
        if not pattern_history:
            return 0.5

        # Return success rate of similar messages
        return sum(pattern_history) / len(pattern_history)

    def decay_old_utilities(self, decay_factor: float = 0.95) -> None:
        """Decay old utility scores to prioritize recent learning."""
        for msg_id in self.message_utility:
            self.message_utility[msg_id] *= decay_factor

        # Also clean up old feedback
        cutoff_time = time.time() - 30 * 24 * 3600  # 30 days
        self.feedback_history = [f for f in self.feedback_history if f.timestamp > cutoff_time]


class MemoryValueEstimator:
    """MemPO-style memory value estimator.

    Combines multiple components to estimate the total value of keeping
    a message in context:
    - Information density: How much useful info per token
    - Task relevance: How relevant to current task
    - Historical utility: Past success rate of similar messages

    This is analogous to MemPO's "Advantages of Informative Memory".
    """

    def __init__(self):
        self.density_calculator = InformationDensityCalculator()
        self.relevance_calculator = TaskRelevanceCalculator()
        self.utility_tracker = HistoricalUtilityTracker()

        # Weight configuration (MemPO-style combination)
        self.weights = {
            "info_density": MemoryValueComponent.INFO_DENSITY,
            "task_relevance": MemoryValueComponent.TASK_RELEVANCE,
            "historical_utility": MemoryValueComponent.HISTORICAL_UTILITY,
        }

    def estimate_value(
        self,
        message: ContextMessage,
        task_context: str,
        current_files: Optional[list[str]] = None,
        recency_decay: bool = True,
    ) -> MessageValueScore:
        """Estimate the total value of a message.

        Args:
            message: The message to evaluate
            task_context: Current task description
            current_files: Currently relevant files
            recency_decay: Whether to apply recency boost

        Returns:
            Complete value score with components
        """
        # Calculate individual components
        info_density = self.density_calculator.calculate(message.content or "")

        task_relevance = self.relevance_calculator.calculate(message, task_context, current_files)

        historical_utility = self.utility_tracker.get_utility(message.id)
        # Also consider pattern-based utility for unseen messages
        pattern_utility = self.utility_tracker.get_pattern_utility(message)
        historical_utility = 0.7 * historical_utility + 0.3 * pattern_utility

        # Recency boost (MemPO: recent interactions more relevant)
        recency_boost = 0.0
        if recency_decay:
            age_seconds = time.time() - message.timestamp
            # Exponential decay, half-life of 10 minutes
            recency_boost = math.exp(-age_seconds / 600) * 0.1

        # Combine scores (MemPO-style weighted sum)
        total_score = (
            self.weights["info_density"] * info_density
            + self.weights["task_relevance"] * task_relevance
            + self.weights["historical_utility"] * historical_utility
            + recency_boost
        )

        return MessageValueScore(
            message_id=message.id,
            total_score=min(1.0, total_score),
            info_density=info_density,
            task_relevance=task_relevance,
            historical_utility=historical_utility,
            recency_boost=recency_boost,
        )

    def batch_estimate(
        self,
        messages: list[ContextMessage],
        task_context: str,
        current_files: Optional[list[str]] = None,
    ) -> list[MessageValueScore]:
        """Estimate values for multiple messages."""
        return [self.estimate_value(m, task_context, current_files) for m in messages]

    def record_outcome(
        self,
        message_id: str,
        task_id: str,
        success: bool,
        contribution: float = 1.0,
    ) -> None:
        """Record the outcome for learning."""
        record = FeedbackRecord(
            message_id=message_id,
            task_id=task_id,
            success=success,
            contribution_score=contribution if success else -contribution,
        )
        self.utility_tracker.record_feedback(record)

    def get_top_k_messages(
        self,
        messages: list[ContextMessage],
        task_context: str,
        k: int,
        current_files: Optional[list[str]] = None,
    ) -> list[tuple[ContextMessage, MessageValueScore]]:
        """Get top k most valuable messages."""
        scored = [(m, self.estimate_value(m, task_context, current_files)) for m in messages]
        scored.sort(key=lambda x: x[1].total_score, reverse=True)
        return scored[:k]


# Global estimator instance
_default_estimator: Optional[MemoryValueEstimator] = None


def get_memory_value_estimator() -> MemoryValueEstimator:
    """Get global memory value estimator."""
    global _default_estimator
    if _default_estimator is None:
        _default_estimator = MemoryValueEstimator()
    return _default_estimator


def reset_memory_value_estimator() -> None:
    """Reset global estimator (useful for testing)."""
    global _default_estimator
    _default_estimator = None
