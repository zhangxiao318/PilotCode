"""Embedding Service - Vector embeddings for semantic search.

This module provides:
1. Text embedding generation using LLM APIs
2. Vector storage and retrieval
3. Semantic similarity search
4. Code chunking and embedding
5. Memory embedding for context retrieval

Features:
- Multiple embedding providers (OpenAI, local models)
- Efficient vector storage with FAISS-like indexing
- Cosine similarity search
- Batch embedding for performance
- Persistent vector store
"""

from __future__ import annotations

import hashlib
import json
import gzip
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from collections import OrderedDict
from platformdirs import user_data_dir
import math

# Try to import httpx for API calls
try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


@dataclass
class EmbeddingVector:
    """A vector embedding with metadata."""

    id: str
    text: str
    vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "vector": self.vector,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmbeddingVector:
        return cls(
            id=data["id"],
            text=data["text"],
            vector=data["vector"],
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", time.time()),
        )


@dataclass
class SearchResult:
    """Result of a vector search."""

    vector: EmbeddingVector
    score: float  # Cosine similarity (0-1)
    rank: int


@dataclass
class EmbeddingStats:
    """Statistics for embedding service."""

    total_vectors: int = 0
    total_dimensions: int = 0
    api_calls: int = 0
    cache_hits: int = 0
    cache_misses: int = 0

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0


class EmbeddingProvider:
    """Base class for embedding providers."""

    def __init__(self, model: str = "default"):
        self.model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts."""
        raise NotImplementedError

    async def embed_single(self, text: str) -> list[float]:
        """Generate embedding for single text."""
        results = await self.embed([text])
        return results[0] if results else []


class SimpleEmbeddingProvider(EmbeddingProvider):
    """Simple fallback embedding using basic text features.

    This is not as good as neural embeddings but works without API calls.
    """

    DIMENSIONS = 128

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate simple embeddings using character n-grams."""
        embeddings = []

        for text in texts:
            # Simple character n-gram based embedding
            vector = [0.0] * self.DIMENSIONS

            # Character frequency features
            text_lower = text.lower()
            for i, char in enumerate(text_lower[:1000]):  # Limit length
                idx = ord(char) % 64
                vector[idx] += 1.0

            # Bigram features
            for i in range(len(text_lower) - 1):
                bigram = text_lower[i : i + 2]
                idx = (ord(bigram[0]) + ord(bigram[1])) % 64 + 64
                vector[idx] += 0.5

            # Normalize
            magnitude = math.sqrt(sum(x * x for x in vector))
            if magnitude > 0:
                vector = [x / magnitude for x in vector]

            embeddings.append(vector)

        return embeddings


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI API embedding provider."""

    def __init__(self, api_key: Optional[str] = None, model: str = "text-embedding-3-small"):
        super().__init__(model)
        self.api_key = api_key
        self.base_url = "https://api.openai.com/v1"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using OpenAI API."""
        if not HAS_HTTPX:
            raise ImportError("httpx is required for API calls")

        if not self.api_key:
            raise ValueError("OpenAI API key required")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": texts,
                },
                timeout=60.0,
            )

            response.raise_for_status()
            data = response.json()

            # Extract embeddings
            embeddings = []
            for item in data["data"]:
                embeddings.append(item["embedding"])

            return embeddings


class VectorStore:
    """In-memory vector store with persistence.

    Uses cosine similarity for nearest neighbor search.
    """

    def __init__(self, persist: bool = True, name: str = "default"):
        self.vectors: dict[str, EmbeddingVector] = {}
        self.persist = persist
        self.name = name

        if persist:
            self._store_dir = Path(user_data_dir("pilotcode", "pilotcode")) / "embeddings"
            self._store_dir.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    def add(self, vector: EmbeddingVector) -> None:
        """Add a vector to the store."""
        self.vectors[vector.id] = vector

        if self.persist:
            self._save_vector_to_disk(vector)

    def add_many(self, vectors: list[EmbeddingVector]) -> None:
        """Add multiple vectors."""
        for vector in vectors:
            self.add(vector)

    def get(self, id: str) -> Optional[EmbeddingVector]:
        """Get vector by ID."""
        return self.vectors.get(id)

    def delete(self, id: str) -> bool:
        """Delete vector by ID."""
        if id in self.vectors:
            del self.vectors[id]

            if self.persist:
                file_path = self._store_dir / f"{id}.json.gz"
                if file_path.exists():
                    file_path.unlink()

            return True
        return False

    def search(
        self, query_vector: list[float], top_k: int = 5, min_score: float = 0.0
    ) -> list[SearchResult]:
        """Search for similar vectors using cosine similarity."""
        if not self.vectors:
            return []

        # Calculate cosine similarity for all vectors
        scored = []
        for vector in self.vectors.values():
            score = self._cosine_similarity(query_vector, vector.vector)
            if score >= min_score:
                scored.append((vector, score))

        # Sort by score (descending)
        scored.sort(key=lambda x: x[1], reverse=True)

        # Return top-k
        results = []
        for rank, (vector, score) in enumerate(scored[:top_k], 1):
            results.append(SearchResult(vector=vector, score=score, rank=rank))

        return results

    def search_by_text(
        self, query_text: str, embed_func, top_k: int = 5, min_score: float = 0.0
    ) -> list[SearchResult]:
        """Search by text (embeds query first)."""
        # This is a synchronous version - async version in EmbeddingService
        return []

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(a) != len(b):
            return 0.0

        dot_product = sum(x * y for x, y in zip(a, b))
        magnitude_a = math.sqrt(sum(x * x for x in a))
        magnitude_b = math.sqrt(sum(x * x for x in b))

        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0

        return dot_product / (magnitude_a * magnitude_b)

    def clear(self) -> None:
        """Clear all vectors."""
        self.vectors.clear()

        if self.persist:
            for file in self._store_dir.glob("*.json.gz"):
                file.unlink()

    def _save_vector_to_disk(self, vector: EmbeddingVector) -> None:
        """Save vector to disk."""
        try:
            file_path = self._store_dir / f"{vector.id}.json.gz"
            with gzip.open(file_path, "wt", encoding="utf-8") as f:
                json.dump(vector.to_dict(), f)
        except Exception as e:
            print(f"Error saving vector: {e}")

    def _load_from_disk(self) -> None:
        """Load vectors from disk."""
        if not self._store_dir.exists():
            return

        for file_path in self._store_dir.glob("*.json.gz"):
            try:
                with gzip.open(file_path, "rt", encoding="utf-8") as f:
                    data = json.load(f)

                vector = EmbeddingVector.from_dict(data)
                self.vectors[vector.id] = vector
            except Exception:
                continue


class EmbeddingService:
    """Main embedding service for semantic search.

    Usage:
        service = EmbeddingService()

        # Embed and store
        await service.embed_text("code snippet", metadata={"file": "test.py"})

        # Search
        results = await service.search("query", top_k=5)
    """

    def __init__(self, provider: Optional[EmbeddingProvider] = None, persist: bool = True):
        self.provider = provider or SimpleEmbeddingProvider()
        self.vector_store = VectorStore(persist=persist)
        self._stats = EmbeddingStats()

        # In-memory cache for embeddings
        self._embedding_cache: OrderedDict[str, list[float]] = OrderedDict()
        self._cache_size = 1000

    async def embed_text(
        self, text: str, metadata: Optional[dict[str, Any]] = None, id: Optional[str] = None
    ) -> EmbeddingVector:
        """Embed a single text and store it."""
        # Generate ID if not provided
        if id is None:
            id = hashlib.sha256(text.encode()).hexdigest()[:16]

        # Check cache
        cache_key = f"{id}:{hashlib.sha256(text.encode()).hexdigest()[:16]}"
        if cache_key in self._embedding_cache:
            self._stats.cache_hits += 1
            vector_data = self._embedding_cache[cache_key]
        else:
            self._stats.cache_misses += 1
            # Generate embedding
            vector_data = await self.provider.embed_single(text)
            self._stats.api_calls += 1

            # Update cache
            self._embedding_cache[cache_key] = vector_data
            if len(self._embedding_cache) > self._cache_size:
                self._embedding_cache.popitem(last=False)

        # Create vector
        embedding = EmbeddingVector(id=id, text=text, vector=vector_data, metadata=metadata or {})

        # Store
        self.vector_store.add(embedding)
        self._stats.total_vectors = len(self.vector_store.vectors)
        self._stats.total_dimensions = len(vector_data)

        return embedding

    async def embed_texts(
        self, texts: list[str], metadatas: Optional[list[dict[str, Any]]] = None
    ) -> list[EmbeddingVector]:
        """Embed multiple texts in batch."""
        if not texts:
            return []

        # Generate embeddings in batch
        vectors_data = await self.provider.embed(texts)
        self._stats.api_calls += 1

        # Create embeddings
        embeddings = []
        for i, (text, vector_data) in enumerate(zip(texts, vectors_data)):
            id = hashlib.sha256(text.encode()).hexdigest()[:16]
            metadata = metadatas[i] if metadatas and i < len(metadatas) else {}

            embedding = EmbeddingVector(id=id, text=text, vector=vector_data, metadata=metadata)
            embeddings.append(embedding)

        # Store all
        self.vector_store.add_many(embeddings)
        self._stats.total_vectors = len(self.vector_store.vectors)

        return embeddings

    async def search(
        self, query: str, top_k: int = 5, min_score: float = 0.0
    ) -> list[SearchResult]:
        """Search for similar texts."""
        # Embed query
        query_vector = await self.provider.embed_single(query)

        # Search
        return self.vector_store.search(query_vector, top_k, min_score)

    async def search_similar(
        self, text: str, top_k: int = 5, min_score: float = 0.0
    ) -> list[SearchResult]:
        """Find texts similar to the given text."""
        return await self.search(text, top_k, min_score)

    def delete(self, id: str) -> bool:
        """Delete an embedding by ID."""
        return self.vector_store.delete(id)

    def clear(self) -> None:
        """Clear all embeddings."""
        self.vector_store.clear()
        self._embedding_cache.clear()
        self._stats = EmbeddingStats()

    def get_stats(self) -> EmbeddingStats:
        """Get embedding statistics."""
        return EmbeddingStats(
            total_vectors=len(self.vector_store.vectors),
            total_dimensions=self._stats.total_dimensions,
            api_calls=self._stats.api_calls,
            cache_hits=self._stats.cache_hits,
            cache_misses=self._stats.cache_misses,
        )

    async def embed_code(
        self, code: str, file_path: Optional[str] = None, language: Optional[str] = None
    ) -> EmbeddingVector:
        """Embed code with code-specific metadata."""
        metadata = {
            "type": "code",
            "language": language or self._detect_language(file_path),
        }
        if file_path:
            metadata["file_path"] = file_path

        id = None
        if file_path:
            id = hashlib.sha256(f"{file_path}:{code}".encode()).hexdigest()[:16]

        return await self.embed_text(code, metadata, id)

    def _detect_language(self, file_path: Optional[str]) -> str:
        """Detect programming language from file path."""
        if not file_path:
            return "unknown"

        ext = Path(file_path).suffix.lower()
        language_map = {
            # Python
            ".py": "python",
            ".pyw": "python",
            ".pyi": "python",
            # JavaScript/TypeScript
            ".js": "javascript",
            ".ts": "typescript",
            # Go, Rust, Java
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            # C
            ".c": "c",
            ".h": "c",
            # C++
            ".cpp": "cpp",
            ".hpp": "cpp",
            ".cc": "cpp",
            ".hh": "cpp",
            ".cxx": "cpp",
            ".hxx": "cpp",
            ".c++": "cpp",
            ".h++": "cpp",
        }
        return language_map.get(ext, "unknown")

    async def embed_memory(
        self, content: str, memory_type: str = "general", tags: Optional[list[str]] = None
    ) -> EmbeddingVector:
        """Embed a memory for later retrieval."""
        metadata = {
            "type": "memory",
            "memory_type": memory_type,
            "tags": tags or [],
            "timestamp": time.time(),
        }

        id = hashlib.sha256(f"{memory_type}:{content}".encode()).hexdigest()[:16]

        return await self.embed_text(content, metadata, id)

    async def search_memories(
        self,
        query: str,
        memory_type: Optional[str] = None,
        tags: Optional[list[str]] = None,
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Search memories with optional filtering."""
        results = await self.search(query, top_k=top_k * 2)  # Get more for filtering

        # Filter by type and tags
        filtered = []
        for result in results:
            meta = result.vector.metadata

            if memory_type and meta.get("memory_type") != memory_type:
                continue

            if tags:
                result_tags = set(meta.get("tags", []))
                if not any(tag in result_tags for tag in tags):
                    continue

            filtered.append(result)

            if len(filtered) >= top_k:
                break

        return filtered


# Global instance
_default_service: Optional[EmbeddingService] = None


def get_embedding_service(provider: Optional[EmbeddingProvider] = None) -> EmbeddingService:
    """Get global embedding service instance."""
    global _default_service
    if _default_service is None:
        _default_service = EmbeddingService(provider=provider)
    return _default_service


def clear_embedding_service() -> None:
    """Clear global embedding service."""
    global _default_service
    if _default_service:
        _default_service.clear()
    _default_service = None
