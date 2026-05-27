"""Semantic Memory Provider — pluggable interface for Tier-3 semantic memory.

Design (Hermes-style):
- Tier 3 is an optional, pluggable enhancement layer.
- Switching providers does NOT affect Tier 1 (fast memory) or Tier 2 (FTS5 history).
- Three lifecycle hooks:
  1. PREFETCH before turn  → retrieve relevant semantic context
  2. SYNC after response    → ingest new information from the turn
  3. EXTRACT at session end → extract long-term knowledge

Implementations:
- LocalEmbeddingProvider: wraps the existing embedding_service.py (default)
- NoOpProvider: disables Tier 3 entirely
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryFragment:
    """A fragment of semantic memory retrieved for context injection."""

    id: str
    content: str
    source: str = ""  # e.g. "episodic", "knowledge_base", "code_index"
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnResult:
    """Summary of a single turn for SYNC ingestion."""

    turn_id: str
    user_message: str = ""
    assistant_message: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class SessionSummary:
    """Summary of an entire session for EXTRACT."""

    session_id: str
    primary_request: str = ""
    key_concepts: list[str] = field(default_factory=list)
    files_examined: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class SemanticMemoryProvider(ABC):
    """Abstract interface for Tier-3 semantic memory providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""
        ...

    @abstractmethod
    async def prefetch(self, query: str, context: dict[str, Any]) -> list[MemoryFragment]:
        """PREFETCH: called before each turn to retrieve relevant semantic context.

        Args:
            query: The user's current query or task description.
            context: Additional context (e.g. current files, session id).

        Returns:
            List of MemoryFragment sorted by relevance (best first).
        """
        ...

    @abstractmethod
    async def sync(self, turn_result: TurnResult) -> None:
        """SYNC: called after a turn completes to ingest new information.

        Args:
            turn_result: Summary of the turn that just finished.
        """
        ...

    @abstractmethod
    async def extract(self, session_summary: SessionSummary) -> list[MemoryFragment]:
        """EXTRACT: called at session end to extract long-term knowledge.

        Args:
            session_summary: Summary of the entire session.

        Returns:
            New knowledge fragments to be persisted.
        """
        ...

    @abstractmethod
    async def search(self, query: str, top_k: int = 5) -> list[MemoryFragment]:
        """Ad-hoc semantic search (for tools / manual queries).

        Args:
            query: Search query.
            top_k: Max results.

        Returns:
            Relevant memory fragments.
        """
        ...


class NoOpProvider(SemanticMemoryProvider):
    """No-op provider: disables Tier-3 semantic memory entirely."""

    @property
    def name(self) -> str:
        return "noop"

    async def prefetch(self, query: str, context: dict[str, Any]) -> list[MemoryFragment]:
        return []

    async def sync(self, turn_result: TurnResult) -> None:
        pass

    async def extract(self, session_summary: SessionSummary) -> list[MemoryFragment]:
        return []

    async def search(self, query: str, top_k: int = 5) -> list[MemoryFragment]:
        return []


class LocalEmbeddingProvider(SemanticMemoryProvider):
    """Default provider using the local embedding_service.py vector store.

    Wraps the existing EmbeddingService and VectorStore to provide
    the SemanticMemoryProvider interface without external dependencies.
    """

    def __init__(self, embedding_service: Any | None = None):
        self._embedding_service = embedding_service
        self._search_results: list[MemoryFragment] = []

    @property
    def name(self) -> str:
        return "local_embedding"

    def _get_service(self):
        if self._embedding_service is None:
            from .embedding_service import get_embedding_service

            self._embedding_service = get_embedding_service()
        return self._embedding_service

    async def prefetch(self, query: str, context: dict[str, Any]) -> list[MemoryFragment]:
        """Search vector store for memories relevant to the current query."""
        service = self._get_service()
        try:
            results = await service.search_memories(query, top_k=5)
            fragments: list[MemoryFragment] = []
            for r in results:
                meta = r.vector.metadata if hasattr(r.vector, "metadata") else {}
                fragments.append(
                    MemoryFragment(
                        id=getattr(r.vector, "id", ""),
                        content=getattr(r.vector, "text", "")[:500],
                        source=meta.get("memory_type", "semantic"),
                        score=r.score,
                        metadata=meta,
                    )
                )
            return fragments
        except Exception:
            return []

    async def sync(self, turn_result: TurnResult) -> None:
        """Embed the turn result as a new memory vector."""
        service = self._get_service()
        if not turn_result.assistant_message:
            return

        # Build a compact summary
        parts: list[str] = []
        if turn_result.user_message:
            parts.append(f"Q: {turn_result.user_message[:200]}")
        if turn_result.assistant_message:
            parts.append(f"A: {turn_result.assistant_message[:400]}")
        if turn_result.files_modified:
            parts.append(f"Files: {', '.join(turn_result.files_modified[:10])}")

        content = "\n".join(parts)
        if not content:
            return

        try:
            tags = []
            if turn_result.errors:
                tags.append("error")
            if turn_result.files_modified:
                tags.append("file_change")
            await service.embed_memory(
                content=content,
                memory_type="turn_summary",
                tags=tags,
            )
        except Exception:
            pass

    async def extract(self, session_summary: SessionSummary) -> list[MemoryFragment]:
        """Embed session-level knowledge."""
        service = self._get_service()
        fragments: list[MemoryFragment] = []

        # Extract concepts
        for concept in session_summary.key_concepts[:20]:
            try:
                vec = await service.embed_memory(
                    content=f"Concept: {concept}",
                    memory_type="concept",
                    tags=["session_extract"],
                )
                fragments.append(
                    MemoryFragment(
                        id=getattr(vec, "id", ""),
                        content=f"Concept: {concept}",
                        source="concept",
                        metadata={"session_id": session_summary.session_id},
                    )
                )
            except Exception:
                continue

        # Extract decisions
        for decision in session_summary.decisions[:10]:
            try:
                vec = await service.embed_memory(
                    content=f"Decision: {decision}",
                    memory_type="decision",
                    tags=["session_extract"],
                )
                fragments.append(
                    MemoryFragment(
                        id=getattr(vec, "id", ""),
                        content=f"Decision: {decision}",
                        source="decision",
                        metadata={"session_id": session_summary.session_id},
                    )
                )
            except Exception:
                continue

        return fragments

    async def search(self, query: str, top_k: int = 5) -> list[MemoryFragment]:
        """Direct semantic search."""
        return await self.prefetch(query, {})


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_PROVIDERS: dict[str, type[SemanticMemoryProvider]] = {
    "noop": NoOpProvider,
    "local": LocalEmbeddingProvider,
}


def register_semantic_provider(name: str, cls: type[SemanticMemoryProvider]) -> None:
    """Register a new semantic memory provider."""
    _PROVIDERS[name] = cls


def get_semantic_provider(name: str = "local", **kwargs: Any) -> SemanticMemoryProvider:
    """Get a semantic memory provider by name.

    Args:
        name: Provider name ("local", "noop", or custom registered name).
        **kwargs: Passed to provider constructor.

    Returns:
        SemanticMemoryProvider instance.
    """
    cls = _PROVIDERS.get(name, LocalEmbeddingProvider)
    return cls(**kwargs)
