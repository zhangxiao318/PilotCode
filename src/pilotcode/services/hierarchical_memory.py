"""Hierarchical memory architecture - MemPO-style structured memory.

This module implements a three-level memory hierarchy:
1. Working Memory: Current conversation context
2. Episodic Memory: Summarized past sessions/episodes
3. Semantic Memory: Extracted knowledge and patterns

Inspired by MemPO's approach of making memory a trainable policy variable.
"""

from __future__ import annotations

import json
import hashlib
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from datetime import datetime
from collections import defaultdict
from enum import Enum

from pydantic import BaseModel

from .context_manager import ContextMessage
from .memory_value import MemoryValueEstimator


class MemoryLevel(Enum):
    """Levels of the memory hierarchy."""
    
    WORKING = "working"      # Active conversation context
    EPISODIC = "episodic"    # Summarized past episodes
    SEMANTIC = "semantic"    # Extracted knowledge


@dataclass
class KnowledgeFragment:
    """A piece of extracted knowledge."""
    
    key: str
    value: str
    source_episodes: list[str] = field(default_factory=list)
    confidence: float = 1.0
    created_at: float = field(default_factory=time.time)
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    
    def access(self) -> None:
        """Record access to this knowledge."""
        self.access_count += 1
        self.last_accessed = time.time()
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "source_episodes": self.source_episodes,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KnowledgeFragment:
        return cls(
            key=data["key"],
            value=data["value"],
            source_episodes=data.get("source_episodes", []),
            confidence=data.get("confidence", 1.0),
            created_at=data.get("created_at", time.time()),
            access_count=data.get("access_count", 0),
            last_accessed=data.get("last_accessed", time.time()),
        )


@dataclass
class EpisodeSummary:
    """Summary of a conversation episode/session.
    
    Analogous to MemPO's generated memory - a compressed representation
    of what happened in a past session.
    """
    
    episode_id: str
    started_at: float
    ended_at: float
    
    # Key information extracted
    primary_request: str = ""
    key_technical_concepts: list[str] = field(default_factory=list)
    files_examined: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    errors_encountered: list[str] = field(default_factory=list)
    decisions_made: list[str] = field(default_factory=list)
    solutions_implemented: list[str] = field(default_factory=list)
    
    # MemPO-style predicted utility
    predicted_utility: float = 0.5
    actual_usage_count: int = 0
    
    # Raw message reference (if needed)
    original_message_count: int = 0
    original_message_ids: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "primary_request": self.primary_request,
            "key_technical_concepts": self.key_technical_concepts,
            "files_examined": self.files_examined,
            "files_modified": self.files_modified,
            "errors_encountered": self.errors_encountered,
            "decisions_made": self.decisions_made,
            "solutions_implemented": self.solutions_implemented,
            "predicted_utility": self.predicted_utility,
            "actual_usage_count": self.actual_usage_count,
            "original_message_count": self.original_message_count,
            "original_message_ids": self.original_message_ids,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EpisodeSummary:
        return cls(
            episode_id=data["episode_id"],
            started_at=data["started_at"],
            ended_at=data["ended_at"],
            primary_request=data.get("primary_request", ""),
            key_technical_concepts=data.get("key_technical_concepts", []),
            files_examined=data.get("files_examined", []),
            files_modified=data.get("files_modified", []),
            errors_encountered=data.get("errors_encountered", []),
            decisions_made=data.get("decisions_made", []),
            solutions_implemented=data.get("solutions_implemented", []),
            predicted_utility=data.get("predicted_utility", 0.5),
            actual_usage_count=data.get("actual_usage_count", 0),
            original_message_count=data.get("original_message_count", 0),
            original_message_ids=data.get("original_message_ids", []),
        )
    
    def to_context_string(self, max_length: int = 1000) -> str:
        """Convert to a string suitable for inclusion in context."""
        parts = [f"=== Previous Session ({datetime.fromtimestamp(self.started_at).strftime('%Y-%m-%d')}) ==="]
        
        if self.primary_request:
            parts.append(f"Request: {self.primary_request[:200]}")
        
        if self.solutions_implemented:
            parts.append(f"Actions: {', '.join(self.solutions_implemented[:5])}")
        
        if self.files_modified:
            parts.append(f"Files modified: {', '.join(self.files_modified[:5])}")
        
        if self.key_technical_concepts:
            parts.append(f"Key concepts: {', '.join(self.key_technical_concepts[:5])}")
        
        result = "\n".join(parts)
        return result[:max_length] + "..." if len(result) > max_length else result


@dataclass
class WorkingMemory:
    """Working memory - active conversation context.
    
    This is the immediate context window that the model sees.
    """
    
    messages: list[ContextMessage] = field(default_factory=list)
    max_tokens: int = 8000
    
    def add(self, message: ContextMessage) -> None:
        """Add a message to working memory."""
        self.messages.append(message)
    
    def get_recent(self, n: int = 10) -> list[ContextMessage]:
        """Get n most recent messages."""
        return self.messages[-n:] if len(self.messages) >= n else self.messages
    
    def estimate_tokens(self) -> int:
        """Estimate token count."""
        return sum(len(m.content or "") // 4 for m in self.messages)
    
    def clear(self) -> None:
        """Clear working memory."""
        self.messages.clear()


@dataclass
class EpisodicMemory:
    """Episodic memory - summarized past episodes.
    
    Stores compressed summaries of past conversation sessions.
    Analogous to MemPO's memory generation.
    """
    
    episodes: list[EpisodeSummary] = field(default_factory=list)
    max_episodes: int = 50
    
    def add_episode(self, episode: EpisodeSummary) -> None:
        """Add a new episode summary."""
        self.episodes.append(episode)
        
        # Prune if over limit
        if len(self.episodes) > self.max_episodes:
            # Remove lowest utility episodes
            self.episodes.sort(key=lambda e: e.predicted_utility, reverse=True)
            self.episodes = self.episodes[:self.max_episodes]
    
    def retrieve_relevant(
        self,
        query: str,
        top_k: int = 3,
    ) -> list[EpisodeSummary]:
        """Retrieve episodes relevant to a query.
        
        Simple keyword-based retrieval. In production, could use embeddings.
        """
        query_words = set(query.lower().split())
        
        scored = []
        for episode in self.episodes:
            score = 0.0
            
            # Check various fields for matches
            text_to_check = " ".join([
                episode.primary_request,
                " ".join(episode.key_technical_concepts),
                " ".join(episode.files_examined),
                " ".join(episode.files_modified),
                " ".join(episode.solutions_implemented),
            ]).lower()
            
            episode_words = set(text_to_check.split())
            overlap = len(query_words & episode_words)
            score += overlap * 0.5
            
            # Boost by predicted utility
            score += episode.predicted_utility * 0.3
            
            # Boost by actual usage
            score += min(0.2, episode.actual_usage_count * 0.05)
            
            scored.append((score, episode))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:top_k]]
    
    def record_usage(self, episode_id: str) -> None:
        """Record that an episode was used."""
        for episode in self.episodes:
            if episode.episode_id == episode_id:
                episode.actual_usage_count += 1
                break
    
    def update_utility(self, episode_id: str, success: bool) -> None:
        """Update predicted utility based on outcome."""
        for episode in self.episodes:
            if episode.episode_id == episode_id:
                # MemPO-style update: adjust based on feedback
                alpha = 0.2
                target = 1.0 if success else 0.0
                episode.predicted_utility = (
                    (1 - alpha) * episode.predicted_utility + alpha * target
                )
                break


@dataclass
class SemanticMemory:
    """Semantic memory - extracted knowledge and patterns.
    
    Stores structured knowledge extracted from conversations.
    This is the highest level of the memory hierarchy.
    """
    
    knowledge: dict[str, KnowledgeFragment] = field(default_factory=dict)
    patterns: dict[str, Any] = field(default_factory=dict)
    
    def add_knowledge(
        self,
        key: str,
        value: str,
        source_episode: Optional[str] = None,
        confidence: float = 1.0,
    ) -> None:
        """Add a piece of knowledge."""
        if key in self.knowledge:
            # Update existing
            existing = self.knowledge[key]
            existing.value = value
            existing.confidence = max(existing.confidence, confidence)
            if source_episode and source_episode not in existing.source_episodes:
                existing.source_episodes.append(source_episode)
        else:
            # Create new
            fragment = KnowledgeFragment(
                key=key,
                value=value,
                source_episodes=[source_episode] if source_episode else [],
                confidence=confidence,
            )
            self.knowledge[key] = fragment
    
    def get_knowledge(self, key: str) -> Optional[str]:
        """Retrieve knowledge by key."""
        fragment = self.knowledge.get(key)
        if fragment:
            fragment.access()
            return fragment.value
        return None
    
    def query_knowledge(self, query: str) -> list[tuple[str, str, float]]:
        """Query knowledge by partial key match."""
        query_lower = query.lower()
        results = []
        
        for key, fragment in self.knowledge.items():
            if query_lower in key.lower():
                results.append((key, fragment.value, fragment.confidence))
        
        # Sort by confidence
        results.sort(key=lambda x: x[2], reverse=True)
        return results
    
    def consolidate(self) -> None:
        """Consolidate memory - remove low-confidence, rarely accessed knowledge."""
        # Remove low confidence knowledge
        to_remove = []
        for key, fragment in self.knowledge.items():
            if fragment.confidence < 0.3:
                to_remove.append(key)
            elif fragment.access_count < 2 and time.time() - fragment.created_at > 7 * 24 * 3600:
                # Not accessed in a week
                to_remove.append(key)
        
        for key in to_remove:
            del self.knowledge[key]


class MemorySnapshotGenerator:
    """Generate memory snapshots from conversation history.
    
    This is the core of MemPO-style memory generation: converting
    raw conversation history into structured, useful memory.
    """
    
    def __init__(self):
        self.value_estimator = MemoryValueEstimator()
    
    def generate_snapshot(
        self,
        messages: list[ContextMessage],
        episode_id: Optional[str] = None,
    ) -> EpisodeSummary:
        """Generate an episode summary from conversation history."""
        episode_id = episode_id or hashlib.md5(
            str(time.time()).encode()
        ).hexdigest()[:12]
        
        summary = EpisodeSummary(
            episode_id=episode_id,
            started_at=min(m.timestamp for m in messages) if messages else time.time(),
            ended_at=max(m.timestamp for m in messages) if messages else time.time(),
            original_message_count=len(messages),
            original_message_ids=[m.id for m in messages],
        )
        
        # Extract information from messages
        for msg in messages:
            self._extract_from_message(msg, summary)
        
        # Calculate predicted utility (MemPO-style)
        summary.predicted_utility = self._estimate_utility(messages, summary)
        
        return summary
    
    def _extract_from_message(self, msg: ContextMessage, summary: EpisodeSummary) -> None:
        """Extract information from a single message."""
        content = msg.content or ""
        content_lower = content.lower()
        
        # Extract user requests
        if msg.role == "user":
            if not summary.primary_request:
                summary.primary_request = content[:500]
            
            # Extract technical concepts
            concepts = self._extract_technical_concepts(content)
            summary.key_technical_concepts.extend(concepts)
        
        # Extract file operations
        elif msg.role == "tool" or "file" in content_lower:
            files = self._extract_file_paths(content)
            
            if "read" in content_lower or "examin" in content_lower:
                summary.files_examined.extend(files)
            elif any(w in content_lower for w in ["write", "edit", "modif", "creat"]):
                summary.files_modified.extend(files)
        
        # Extract errors
        if "error" in content_lower or "exception" in content_lower or "fail" in content_lower:
            error_preview = self._extract_error_preview(content)
            if error_preview:
                summary.errors_encountered.append(error_preview)
        
        # Extract decisions and solutions
        if msg.role == "assistant":
            decisions = self._extract_decisions(content)
            summary.decisions_made.extend(decisions)
            
            solutions = self._extract_solutions(content)
            summary.solutions_implemented.extend(solutions)
    
    def _extract_technical_concepts(self, content: str) -> list[str]:
        """Extract technical concepts from content."""
        import re
        
        # Look for code-like patterns
        concepts = []
        
        # Function/class definitions
        func_pattern = re.findall(r'def\s+(\w+)|class\s+(\w+)', content)
        for match in func_pattern:
            concepts.extend([m for m in match if m])
        
        # Import statements
        import_pattern = re.findall(r'(?:from|import)\s+([\w.]+)', content)
        concepts.extend(import_pattern)
        
        # Common technical terms
        tech_terms = [
            "api", "endpoint", "database", "cache", "queue", "async",
            "middleware", "decorator", "router", "controller", "model",
            "migration", "schema", "query", "middleware", "auth",
        ]
        content_lower = content.lower()
        for term in tech_terms:
            if term in content_lower and term not in concepts:
                concepts.append(term)
        
        return list(set(concepts))[:10]  # Limit to 10 unique concepts
    
    def _extract_file_paths(self, content: str) -> list[str]:
        """Extract file paths from content."""
        import re
        
        # Match common file path patterns
        patterns = [
            r'[\w\-./]+\.(py|js|ts|java|go|rs|cpp|c|h|json|yaml|yml|md|txt)',
            r'src/[\w\-./]+',
            r'tests?/[\w\-./]+',
        ]
        
        files = []
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            files.extend(matches)
        
        return list(set(files))[:10]
    
    def _extract_error_preview(self, content: str) -> str:
        """Extract error preview from content."""
        lines = content.split('\n')
        for line in lines:
            if any(w in line.lower() for w in ['error', 'exception', 'traceback']):
                return line[:200]
        return content[:200] if len(content) > 50 else ""
    
    def _extract_decisions(self, content: str) -> list[str]:
        """Extract decision statements from content."""
        decisions = []
        lines = content.split('\n')
        
        for line in lines:
            line_lower = line.lower()
            if any(w in line_lower for w in ['decide', 'decision', 'choose', 'select', 'opt for']):
                decisions.append(line.strip()[:200])
            elif any(w in line_lower for w in ['will use', 'going to', 'plan to', 'approach is']):
                decisions.append(line.strip()[:200])
        
        return decisions[:5]
    
    def _extract_solutions(self, content: str) -> list[str]:
        """Extract solution statements from content."""
        solutions = []
        lines = content.split('\n')
        
        for line in lines:
            line_lower = line.lower()
            if any(w in line_lower for w in ['implemented', 'created', 'added', 'fixed', 'resolved']):
                solutions.append(line.strip()[:200])
            elif any(w in line_lower for w in ['solution is', 'solution:', 'fixed by', 'solved by']):
                solutions.append(line.strip()[:200])
        
        return solutions[:5]
    
    def _estimate_utility(
        self,
        messages: list[ContextMessage],
        summary: EpisodeSummary,
    ) -> float:
        """Estimate the future utility of this episode (MemPO-style).
        
        Higher utility for episodes that:
        - Have clear solutions
        - Involve file modifications
        - Have technical substance
        """
        score = 0.3  # Base score
        
        # Bonus for solutions
        if summary.solutions_implemented:
            score += min(0.3, len(summary.solutions_implemented) * 0.1)
        
        # Bonus for file modifications
        if summary.files_modified:
            score += min(0.2, len(summary.files_modified) * 0.05)
        
        # Bonus for technical concepts
        if summary.key_technical_concepts:
            score += min(0.1, len(summary.key_technical_concepts) * 0.02)
        
        # Penalty for errors
        if summary.errors_encountered:
            score -= min(0.2, len(summary.errors_encountered) * 0.05)
        
        # Bonus for message count (more substance)
        if len(messages) > 10:
            score += 0.1
        
        return max(0.0, min(1.0, score))


class HierarchicalMemory:
    """Complete hierarchical memory system.
    
    Integrates working, episodic, and semantic memory levels
    with MemPO-style memory generation and retrieval.
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        self.working = WorkingMemory()
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()
        self.storage_path = storage_path
        
        self.snapshot_generator = MemorySnapshotGenerator()
        self.current_episode_start: Optional[float] = None
        
        # Load persisted data
        if storage_path:
            self._load()
    
    def start_episode(self) -> None:
        """Start a new episode."""
        self.current_episode_start = time.time()
        self.working.clear()
    
    def add_to_working(self, message: ContextMessage) -> None:
        """Add message to working memory."""
        self.working.add(message)
    
    def end_episode(self) -> EpisodeSummary:
        """End current episode and generate snapshot."""
        if not self.working.messages:
            raise ValueError("No messages to snapshot")
        
        # Generate snapshot
        snapshot = self.snapshot_generator.generate_snapshot(
            self.working.messages
        )
        
        # Add to episodic memory
        self.episodic.add_episode(snapshot)
        
        # Extract and add semantic knowledge
        self._extract_semantic_knowledge(snapshot)
        
        # Clear working memory
        self.working.clear()
        self.current_episode_start = None
        
        self._save()
        return snapshot
    
    def _extract_semantic_knowledge(self, snapshot: EpisodeSummary) -> None:
        """Extract semantic knowledge from an episode."""
        # Extract file patterns
        for file in snapshot.files_modified:
            key = f"file:{file}"
            self.semantic.add_knowledge(
                key=key,
                value=f"Modified in episode {snapshot.episode_id}",
                source_episode=snapshot.episode_id,
            )
        
        # Extract solutions as knowledge
        for solution in snapshot.solutions_implemented:
            # Create a key from solution preview
            key = f"solution:{solution[:50]}"
            self.semantic.add_knowledge(
                key=key,
                value=solution,
                source_episode=snapshot.episode_id,
                confidence=snapshot.predicted_utility,
            )
        
        # Extract concepts
        for concept in snapshot.key_technical_concepts:
            key = f"concept:{concept}"
            self.semantic.add_knowledge(
                key=key,
                value=f"Related to: {snapshot.primary_request[:100]}",
                source_episode=snapshot.episode_id,
            )
    
    def retrieve_context(
        self,
        query: str,
        include_episodes: int = 2,
        include_knowledge: int = 5,
    ) -> dict[str, Any]:
        """Retrieve relevant context from all memory levels."""
        context = {
            "working_memory": self.working.get_recent(10),
            "episodic_memories": [],
            "semantic_knowledge": [],
        }
        
        # Retrieve from episodic memory
        episodes = self.episodic.retrieve_relevant(query, include_episodes)
        context["episodic_memories"] = episodes
        
        # Record usage
        for ep in episodes:
            self.episodic.record_usage(ep.episode_id)
        
        # Retrieve from semantic memory
        knowledge = self.semantic.query_knowledge(query)
        context["semantic_knowledge"] = knowledge[:include_knowledge]
        
        return context
    
    def format_context_for_prompt(
        self,
        retrieved: dict[str, Any],
        max_tokens: int = 2000,
    ) -> str:
        """Format retrieved context for inclusion in prompt."""
        parts = []
        estimated_tokens = 0
        
        # Add episodic memories
        for episode in retrieved.get("episodic_memories", []):
            text = episode.to_context_string(500)
            est_tokens = len(text) // 4
            
            if estimated_tokens + est_tokens > max_tokens:
                break
            
            parts.append(text)
            estimated_tokens += est_tokens
        
        # Add semantic knowledge
        knowledge = retrieved.get("semantic_knowledge", [])
        if knowledge:
            parts.append("\n=== Relevant Knowledge ===")
            for key, value, confidence in knowledge:
                text = f"- {key}: {value[:200]}"
                est_tokens = len(text) // 4
                
                if estimated_tokens + est_tokens > max_tokens:
                    break
                
                parts.append(text)
                estimated_tokens += est_tokens
        
        return "\n\n".join(parts)
    
    def feedback_episode_utility(self, episode_id: str, success: bool) -> None:
        """Provide feedback about episode utility."""
        self.episodic.update_utility(episode_id, success)
        
        # Also update semantic knowledge confidence
        for key, fragment in self.semantic.knowledge.items():
            if episode_id in fragment.source_episodes:
                alpha = 0.2
                target = 1.0 if success else 0.3
                fragment.confidence = (1 - alpha) * fragment.confidence + alpha * target
        
        self._save()
    
    def get_stats(self) -> dict[str, Any]:
        """Get memory statistics."""
        return {
            "working_memory": {
                "message_count": len(self.working.messages),
                "estimated_tokens": self.working.estimate_tokens(),
            },
            "episodic_memory": {
                "episode_count": len(self.episodic.episodes),
                "avg_utility": sum(
                    e.predicted_utility for e in self.episodic.episodes
                ) / len(self.episodic.episodes) if self.episodic.episodes else 0,
            },
            "semantic_memory": {
                "knowledge_count": len(self.semantic.knowledge),
                "avg_confidence": sum(
                    f.confidence for f in self.semantic.knowledge.values()
                ) / len(self.semantic.knowledge) if self.semantic.knowledge else 0,
            },
        }
    
    def _save(self) -> None:
        """Persist memory state."""
        if not self.storage_path:
            return
        
        try:
            data = {
                "episodic": [e.to_dict() for e in self.episodic.episodes],
                "semantic": {
                    k: v.to_dict() for k, v in self.semantic.knowledge.items()
                },
                "patterns": self.semantic.patterns,
            }
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
    
    def _load(self) -> None:
        """Load persisted memory state."""
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            self.episodic.episodes = [
                EpisodeSummary.from_dict(e) for e in data.get("episodic", [])
            ]
            
            self.semantic.knowledge = {
                k: KnowledgeFragment.from_dict(v)
                for k, v in data.get("semantic", {}).items()
            }
            
            self.semantic.patterns = data.get("patterns", {})
            
        except Exception:
            pass


# Global instance
_default_hierarchical_memory: Optional[HierarchicalMemory] = None


def get_hierarchical_memory(storage_path: Optional[str] = None) -> HierarchicalMemory:
    """Get global hierarchical memory instance."""
    global _default_hierarchical_memory
    if _default_hierarchical_memory is None:
        _default_hierarchical_memory = HierarchicalMemory(storage_path)
    return _default_hierarchical_memory


def reset_hierarchical_memory() -> None:
    """Reset global hierarchical memory."""
    global _default_hierarchical_memory
    _default_hierarchical_memory = None
