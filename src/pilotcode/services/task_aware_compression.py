"""Task-aware context compression - MemPO-style selective retention.

This module implements:
1. Task-aware message selection
2. Value-based compression (keep high-value, not just recent)
3. Semantic clustering to preserve diverse information
4. Integration with memory value estimation
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum

from .context_manager import ContextMessage, CompactStrategy
from .memory_value import MemoryValueEstimator, MessageValueScore
from .intelligent_compact import IntelligentContextCompactor, CompactionResult


class CompressionMode(Enum):
    """Compression mode based on context pressure."""
    
    LIGHT = "light"      # Keep 80% of messages
    MODERATE = "moderate"  # Keep 60% of messages
    AGGRESSIVE = "aggressive"  # Keep 40% of messages
    EMERGENCY = "emergency"   # Keep 20% of messages


@dataclass
class TaskContext:
    """Current task context for compression decisions."""
    
    description: str = ""
    current_files: list[str] = field(default_factory=list)
    task_type: str = ""  # "debug", "feature", "refactor", "review", etc.
    complexity: str = "medium"  # "simple", "medium", "complex"
    goal_keywords: list[str] = field(default_factory=list)
    
    def to_summary(self) -> str:
        """Generate summary string for matching."""
        parts = [self.description]
        if self.goal_keywords:
            parts.append("Keywords: " + ", ".join(self.goal_keywords))
        return " ".join(parts)


@dataclass
class RetentionDecision:
    """Decision about whether to retain a message."""
    
    message_id: str
    retained: bool
    value_score: float
    reason: str  # Why this decision was made
    compression_action: str  # "keep", "summarize", "remove"


@dataclass
class TaskAwareCompressionResult:
    """Result of task-aware compression."""
    
    original_messages: int
    retained_messages: int
    summarized_messages: int
    removed_messages: int
    original_tokens: int
    compressed_tokens: int
    value_retention_rate: float  # Ratio of total value retained
    decisions: list[RetentionDecision] = field(default_factory=list)
    task_context: TaskContext = field(default_factory=TaskContext)
    compression_mode: CompressionMode = CompressionMode.MODERATE
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "original_messages": self.original_messages,
            "retained_messages": self.retained_messages,
            "summarized_messages": self.summarized_messages,
            "removed_messages": self.removed_messages,
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
            "value_retention_rate": self.value_retention_rate,
            "compression_mode": self.compression_mode.value,
            "retention_rate": self.retained_messages / max(1, self.original_messages),
            "token_reduction": 1 - (self.compressed_tokens / max(1, self.original_tokens)),
        }


class SemanticClustering:
    """Cluster messages by semantic similarity for diversity preservation."""
    
    def __init__(self):
        self.similarity_threshold = 0.7
    
    def cluster_messages(
        self,
        messages: list[ContextMessage]
    ) -> list[list[ContextMessage]]:
        """Group similar messages into clusters."""
        clusters: list[list[ContextMessage]] = []
        
        for msg in messages:
            assigned = False
            for cluster in clusters:
                if self._is_similar(msg, cluster[0]):
                    cluster.append(msg)
                    assigned = True
                    break
            
            if not assigned:
                clusters.append([msg])
        
        return clusters
    
    def _is_similar(self, msg1: ContextMessage, msg2: ContextMessage) -> bool:
        """Check if two messages are semantically similar."""
        # Simple implementation using keyword overlap
        # In production, could use embeddings
        content1 = (msg1.content or "").lower()
        content2 = (msg2.content or "").lower()
        
        # Extract keywords
        words1 = set(self._extract_keywords(content1))
        words2 = set(self._extract_keywords(content2))
        
        if not words1 or not words2:
            return False
        
        # Jaccard similarity
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        if union == 0:
            return False
        
        return (intersection / union) > self.similarity_threshold
    
    def _extract_keywords(self, content: str) -> list[str]:
        """Extract keywords from content."""
        import re
        
        # Remove common stopwords
        stopwords = {"the", "a", "an", "is", "are", "was", "were", 
                     "be", "been", "being", "have", "has", "had",
                     "to", "of", "in", "for", "on", "with", "at",
                     "and", "but", "or", "it", "this", "that"}
        
        words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', content)
        return [w for w in words if len(w) > 2 and w.lower() not in stopwords]
    
    def select_diverse_samples(
        self,
        clusters: list[list[ContextMessage]],
        scores: dict[str, float],
        total_budget: int,
    ) -> list[ContextMessage]:
        """Select diverse samples from clusters to maximize coverage."""
        selected = []
        remaining_budget = total_budget
        
        # Sort clusters by max score in each
        sorted_clusters = sorted(
            clusters,
            key=lambda c: max(scores.get(m.id, 0) for m in c),
            reverse=True
        )
        
        # Round-robin selection from clusters for diversity
        while remaining_budget > 0 and sorted_clusters:
            new_clusters = []
            for cluster in sorted_clusters:
                # Pick highest scored unselected message from cluster
                unselected = [m for m in cluster if m not in selected]
                if unselected:
                    best = max(unselected, key=lambda m: scores.get(m.id, 0))
                    selected.append(best)
                    remaining_budget -= 1
                    if remaining_budget <= 0:
                        break
                    new_clusters.append(cluster)
            
            sorted_clusters = new_clusters
        
        return selected


class TaskAwareCompressor(IntelligentContextCompactor):
    """Task-aware context compressor using MemPO-style value estimation.
    
    Unlike traditional compressors that use FIFO/LRU, this compressor:
    1. Estimates the value of each message for the current task
    2. Selectively retains high-value messages
    3. Ensures semantic diversity in retained messages
    4. Summarizes medium-value messages instead of dropping them
    """
    
    def __init__(self):
        super().__init__()
        self.value_estimator = MemoryValueEstimator()
        self.clustering = SemanticClustering()
        
        # Mode thresholds (token-based)
        self.mode_thresholds = {
            CompressionMode.LIGHT: 0.7,      # At 70% capacity
            CompressionMode.MODERATE: 0.85,  # At 85% capacity
            CompressionMode.AGGRESSIVE: 0.95, # At 95% capacity
            CompressionMode.EMERGENCY: 1.0,   # At 100% capacity
        }
        
        # Retention ratios per mode
        self.retention_ratios = {
            CompressionMode.LIGHT: 0.8,
            CompressionMode.MODERATE: 0.6,
            CompressionMode.AGGRESSIVE: 0.4,
            CompressionMode.EMERGENCY: 0.2,
        }
    
    def compress_with_task_context(
        self,
        messages: list[ContextMessage],
        task_context: TaskContext,
        target_tokens: int,
        preserve_recent: int = 4,
    ) -> TaskAwareCompressionResult:
        """Compress messages based on task context and value estimation.
        
        This is the main entry point for MemPO-style compression.
        
        Args:
            messages: Messages to compress
            task_context: Current task context
            target_tokens: Target token count
            preserve_recent: Number of recent message pairs to always keep
            
        Returns:
            Compression result with decisions
        """
        if not messages:
            return TaskAwareCompressionResult(
                original_messages=0,
                retained_messages=0,
                summarized_messages=0,
                removed_messages=0,
                original_tokens=0,
                compressed_tokens=0,
                value_retention_rate=1.0,
                task_context=task_context,
            )
        
        # Calculate current tokens
        original_tokens = sum(
            self.estimate_tokens(m.content or "") for m in messages
        )
        
        if original_tokens <= target_tokens:
            # No compression needed
            return TaskAwareCompressionResult(
                original_messages=len(messages),
                retained_messages=len(messages),
                summarized_messages=0,
                removed_messages=0,
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                value_retention_rate=1.0,
                task_context=task_context,
            )
        
        # Determine compression mode
        usage_ratio = original_tokens / target_tokens if target_tokens > 0 else 1.0
        mode = self._determine_mode(usage_ratio)
        
        # Always preserve recent messages
        preserve_count = min(preserve_recent * 2, len(messages))
        recent_messages = messages[-preserve_count:] if preserve_count > 0 else []
        old_messages = messages[:-preserve_count] if preserve_count > 0 else messages
        
        # Estimate value for old messages
        value_scores = self.value_estimator.batch_estimate(
            old_messages,
            task_context.to_summary(),
            task_context.current_files,
        )
        
        score_map = {s.message_id: s.total_score for s in value_scores}
        
        # Calculate target retention
        retention_ratio = self.retention_ratios[mode]
        target_retention = max(1, int(len(old_messages) * retention_ratio))
        
        # Cluster messages for diversity
        clusters = self.clustering.cluster_messages(old_messages)
        
        # Select diverse, high-value messages
        selected_old = self.clustering.select_diverse_samples(
            clusters, score_map, target_retention
        )
        
        # Make decisions for each message
        decisions = self._make_decisions(
            old_messages, selected_old, score_map, task_context
        )
        
        # Build result message list
        retained = list(recent_messages)  # Always keep recent
        summarized = []
        removed_ids = {d.message_id for d in decisions if d.compression_action == "remove"}
        
        for msg in old_messages:
            if msg.id in removed_ids:
                continue
            
            score = score_map.get(msg.id, 0)
            
            if msg in selected_old:
                # Check if we should summarize or keep full
                if score > 0.7 or len(msg.content or "") < 500:
                    retained.append(msg)
                else:
                    # Summarize medium-value, long messages
                    summarized_msg = self._summarize_message(msg)
                    if summarized_msg:
                        summarized.append(summarized_msg)
                        retained.append(summarized_msg)
            
        # Sort retained messages by original order
        original_order = {m.id: i for i, m in enumerate(messages)}
        retained.sort(key=lambda m: original_order.get(m.id, 0))
        
        # Calculate metrics
        compressed_tokens = sum(
            self.estimate_tokens(m.content or "") for m in retained
        )
        
        total_original_value = sum(score_map.values())
        retained_value = sum(
            score_map.get(m.id, 0) for m in retained if m.id in score_map
        )
        value_retention_rate = (
            retained_value / total_original_value if total_original_value > 0 else 1.0
        )
        
        return TaskAwareCompressionResult(
            original_messages=len(messages),
            retained_messages=len([m for m in retained if m not in recent_messages]),
            summarized_messages=len(summarized),
            removed_messages=len(removed_ids),
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            value_retention_rate=value_retention_rate,
            decisions=decisions,
            task_context=task_context,
            compression_mode=mode,
        )
    
    def _determine_mode(self, usage_ratio: float) -> CompressionMode:
        """Determine compression mode based on usage ratio."""
        if usage_ratio >= 1.5:
            return CompressionMode.EMERGENCY
        elif usage_ratio >= 1.2:
            return CompressionMode.AGGRESSIVE
        elif usage_ratio >= 1.1:
            return CompressionMode.MODERATE
        else:
            return CompressionMode.LIGHT
    
    def _make_decisions(
        self,
        all_messages: list[ContextMessage],
        selected: list[ContextMessage],
        scores: dict[str, float],
        task_context: TaskContext,
    ) -> list[RetentionDecision]:
        """Make retention decisions for each message."""
        decisions = []
        selected_ids = {m.id for m in selected}
        
        for msg in all_messages:
            score = scores.get(msg.id, 0)
            
            if msg.id in selected_ids:
                if score > 0.7:
                    action = "keep"
                    reason = f"High value score ({score:.2f}) for task"
                else:
                    action = "summarize"
                    reason = f"Medium value ({score:.2f}), will summarize"
                retained = True
            else:
                action = "remove"
                reason = f"Low value ({score:.2f}) or redundant"
                retained = False
            
            decisions.append(RetentionDecision(
                message_id=msg.id,
                retained=retained,
                value_score=score,
                reason=reason,
                compression_action=action,
            ))
        
        return decisions
    
    def _summarize_message(
        self,
        message: ContextMessage,
    ) -> Optional[ContextMessage]:
        """Create a summarized version of a message."""
        content = message.content or ""
        
        if len(content) < 200:
            return None  # Too short to summarize
        
        # Create summary based on message type
        if message.role == "tool":
            summary = f"[Tool result: {content[:100]}... ({len(content)} chars)]"
        elif message.role == "assistant":
            # Extract key actions/decisions
            lines = content.split('\n')
            key_lines = [l for l in lines if any(
                kw in l.lower() for kw in ["created", "modified", "fixed", "added", "implemented"]
            )]
            if key_lines:
                summary = "[Summary: " + "; ".join(key_lines[:3]) + "]"
            else:
                summary = f"[Response: {content[:150]}...]"
        else:
            summary = f"[{message.role}: {content[:150]}...]"
        
        # Create new message with summary
        summarized = ContextMessage(
            role=message.role,
            content=summary,
            timestamp=message.timestamp,
            priority=message.priority,
            tokens=len(summary) // 4,
            id=message.id + "_sum",
            metadata={**message.metadata, "summarized": True, "original_length": len(content)},
            access_count=message.access_count,
            last_access=message.last_access,
            summarized=True,
            original_content=content,
        )
        
        return summarized
    
    def compress_by_task_type(
        self,
        messages: list[ContextMessage],
        task_type: str,
        task_description: str,
        current_files: list[str],
        target_tokens: int,
    ) -> TaskAwareCompressionResult:
        """Convenience method that infers task context from type."""
        # Infer complexity from task type
        complexity_map = {
            "debug": "medium",
            "fix": "medium",
            "feature": "complex",
            "implement": "complex",
            "refactor": "complex",
            "review": "simple",
            "explain": "simple",
            "test": "medium",
        }
        
        # Extract keywords from task description
        import re
        keywords = re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\b', task_description)
        # Filter to likely meaningful terms
        keywords = [k for k in keywords if len(k) > 3][:10]
        
        task_context = TaskContext(
            description=task_description,
            current_files=current_files,
            task_type=task_type,
            complexity=complexity_map.get(task_type, "medium"),
            goal_keywords=keywords,
        )
        
        return self.compress_with_task_context(
            messages, task_context, target_tokens
        )


# Global instance
default_compressor: Optional[TaskAwareCompressor] = None


def get_task_aware_compressor() -> TaskAwareCompressor:
    """Get global task-aware compressor."""
    global default_compressor
    if default_compressor is None:
        default_compressor = TaskAwareCompressor()
    return default_compressor


def reset_task_aware_compressor() -> None:
    """Reset global compressor."""
    global default_compressor
    default_compressor = None
