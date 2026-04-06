"""Tests for Embedding Service."""

import pytest
import tempfile
import shutil
import math
from pathlib import Path

from pilotcode.services.embedding_service import (
    EmbeddingVector,
    SearchResult,
    EmbeddingStats,
    SimpleEmbeddingProvider,
    VectorStore,
    EmbeddingService,
    get_embedding_service,
    clear_embedding_service,
)


class TestEmbeddingVector:
    """Test EmbeddingVector dataclass."""
    
    def test_creation(self):
        """Test vector creation."""
        vector = EmbeddingVector(
            id="test123",
            text="Hello world",
            vector=[0.1, 0.2, 0.3],
            metadata={"source": "test"}
        )
        
        assert vector.id == "test123"
        assert vector.text == "Hello world"
        assert len(vector.vector) == 3
        assert vector.metadata["source"] == "test"
    
    def test_serialization(self):
        """Test dict serialization."""
        vector = EmbeddingVector(
            id="test",
            text="text",
            vector=[0.1, 0.2],
            metadata={"key": "value"}
        )
        
        data = vector.to_dict()
        restored = EmbeddingVector.from_dict(data)
        
        assert restored.id == vector.id
        assert restored.text == vector.text
        assert restored.vector == vector.vector
        assert restored.metadata == vector.metadata


class TestSimpleEmbeddingProvider:
    """Test SimpleEmbeddingProvider."""
    
    @pytest.fixture
    def provider(self):
        return SimpleEmbeddingProvider()
    
    @pytest.mark.asyncio
    async def test_embed_single(self, provider):
        """Test single text embedding."""
        vector = await provider.embed_single("Hello world")
        
        assert len(vector) == SimpleEmbeddingProvider.DIMENSIONS
        assert all(isinstance(x, float) for x in vector)
    
    @pytest.mark.asyncio
    async def test_embed_multiple(self, provider):
        """Test multiple text embedding."""
        vectors = await provider.embed(["Hello", "World"])
        
        assert len(vectors) == 2
        assert len(vectors[0]) == SimpleEmbeddingProvider.DIMENSIONS
        assert len(vectors[1]) == SimpleEmbeddingProvider.DIMENSIONS
    
    @pytest.mark.asyncio
    async def test_vectors_normalized(self, provider):
        """Test that vectors are normalized."""
        vector = await provider.embed_single("Test text")
        
        # Calculate magnitude
        magnitude = math.sqrt(sum(x*x for x in vector))
        
        # Should be close to 1 (normalized)
        assert abs(magnitude - 1.0) < 0.01 or magnitude == 0
    
    @pytest.mark.asyncio
    async def test_different_texts_different_vectors(self, provider):
        """Test that different texts produce different vectors."""
        vectors = await provider.embed(["Hello", "World", "Python"])
        
        # All should be different
        assert vectors[0] != vectors[1]
        assert vectors[1] != vectors[2]
    
    @pytest.mark.asyncio
    async def test_similar_texts_similar_vectors(self, provider):
        """Test that similar texts have higher similarity."""
        vectors = await provider.embed(["hello world", "hello there", "completely different"])
        
        # Calculate similarities
        def cosine_sim(a, b):
            dot = sum(x*y for x, y in zip(a, b))
            mag_a = math.sqrt(sum(x*x for x in a))
            mag_b = math.sqrt(sum(x*x for x in b))
            return dot / (mag_a * mag_b) if mag_a and mag_b else 0
        
        sim_0_1 = cosine_sim(vectors[0], vectors[1])  # Similar
        sim_0_2 = cosine_sim(vectors[0], vectors[2])  # Different
        
        # Similar texts should have higher similarity
        assert sim_0_1 > sim_0_2


class TestVectorStore:
    """Test VectorStore functionality."""
    
    @pytest.fixture
    def store(self):
        return VectorStore(persist=False)
    
    def test_add_and_get(self, store):
        """Test adding and retrieving vectors."""
        vector = EmbeddingVector(
            id="test1",
            text="Hello",
            vector=[1.0, 0.0, 0.0]
        )
        
        store.add(vector)
        
        retrieved = store.get("test1")
        assert retrieved is not None
        assert retrieved.id == "test1"
        assert retrieved.text == "Hello"
    
    def test_add_many(self, store):
        """Test adding multiple vectors."""
        vectors = [
            EmbeddingVector(id="v1", text="A", vector=[1.0, 0.0, 0.0]),
            EmbeddingVector(id="v2", text="B", vector=[0.0, 1.0, 0.0]),
            EmbeddingVector(id="v3", text="C", vector=[0.0, 0.0, 1.0]),
        ]
        
        store.add_many(vectors)
        
        assert len(store.vectors) == 3
        assert store.get("v1") is not None
        assert store.get("v2") is not None
        assert store.get("v3") is not None
    
    def test_delete(self, store):
        """Test deleting vectors."""
        vector = EmbeddingVector(id="to_delete", text="Text", vector=[1.0, 0.0])
        store.add(vector)
        
        assert store.delete("to_delete") is True
        assert store.get("to_delete") is None
        assert store.delete("to_delete") is False
    
    def test_search_exact_match(self, store):
        """Test searching for exact match."""
        # Add vectors
        store.add(EmbeddingVector(id="v1", text="Hello world", vector=[1.0, 0.0, 0.0]))
        store.add(EmbeddingVector(id="v2", text="Goodbye", vector=[0.0, 1.0, 0.0]))
        
        # Search with same vector
        results = store.search([1.0, 0.0, 0.0], top_k=1)
        
        assert len(results) == 1
        assert results[0].vector.id == "v1"
        assert results[0].score > 0.99  # Very high similarity
    
    def test_search_ranking(self, store):
        """Test search result ranking."""
        # Add vectors with different similarities
        store.add(EmbeddingVector(id="close", text="Close", vector=[0.9, 0.1, 0.0]))
        store.add(EmbeddingVector(id="far", text="Far", vector=[0.0, 1.0, 0.0]))
        store.add(EmbeddingVector(id="exact", text="Exact", vector=[1.0, 0.0, 0.0]))
        
        # Search
        results = store.search([1.0, 0.0, 0.0], top_k=3)
        
        assert len(results) == 3
        assert results[0].vector.id == "exact"  # Highest score
        assert results[0].rank == 1
        assert results[1].rank == 2
        assert results[2].rank == 3
        assert results[0].score > results[1].score > results[2].score
    
    def test_search_min_score(self, store):
        """Test search with minimum score filter."""
        store.add(EmbeddingVector(id="high", text="High", vector=[0.9, 0.1, 0.0]))
        store.add(EmbeddingVector(id="low", text="Low", vector=[0.1, 0.9, 0.0]))
        
        results = store.search([1.0, 0.0, 0.0], min_score=0.5)
        
        # Only high similarity should pass
        assert len(results) == 1
        assert results[0].vector.id == "high"
    
    def test_search_empty_store(self, store):
        """Test searching empty store."""
        results = store.search([1.0, 0.0, 0.0])
        assert results == []
    
    def test_clear(self, store):
        """Test clearing store."""
        store.add(EmbeddingVector(id="v1", text="Text", vector=[1.0]))
        store.clear()
        
        assert len(store.vectors) == 0
        assert store.get("v1") is None
    
    def test_cosine_similarity_orthogonal(self, store):
        """Test cosine similarity for orthogonal vectors."""
        # Orthogonal vectors have 0 similarity
        sim = store._cosine_similarity([1.0, 0.0], [0.0, 1.0])
        assert abs(sim) < 0.0001
    
    def test_cosine_similarity_same(self, store):
        """Test cosine similarity for identical vectors."""
        sim = store._cosine_similarity([1.0, 0.0], [1.0, 0.0])
        assert abs(sim - 1.0) < 0.0001
    
    def test_cosine_similarity_opposite(self, store):
        """Test cosine similarity for opposite vectors."""
        sim = store._cosine_similarity([1.0, 0.0], [-1.0, 0.0])
        assert abs(sim - (-1.0)) < 0.0001


class TestEmbeddingService:
    """Test EmbeddingService."""
    
    @pytest.fixture
    def service(self):
        return EmbeddingService(persist=False)
    
    @pytest.mark.asyncio
    async def test_embed_text(self, service):
        """Test embedding single text."""
        vector = await service.embed_text(
            "Hello world",
            metadata={"source": "test"}
        )
        
        assert vector.id is not None
        assert vector.text == "Hello world"
        assert len(vector.vector) > 0
        assert vector.metadata["source"] == "test"
        
        # Should be stored
        assert service.vector_store.get(vector.id) is not None
    
    @pytest.mark.asyncio
    async def test_embed_texts_batch(self, service):
        """Test batch embedding."""
        texts = ["First text", "Second text", "Third text"]
        vectors = await service.embed_texts(texts)
        
        assert len(vectors) == 3
        for i, vector in enumerate(vectors):
            assert vector.text == texts[i]
    
    @pytest.mark.asyncio
    async def test_search(self, service):
        """Test semantic search."""
        # Add some texts
        await service.embed_text("Python programming language", {"topic": "python"})
        await service.embed_text("JavaScript web development", {"topic": "js"})
        await service.embed_text("Machine learning with Python", {"topic": "ml"})
        
        # Search
        results = await service.search("python coding", top_k=2)
        
        assert len(results) > 0
        # Python-related results should be first
        assert "python" in results[0].vector.text.lower()
    
    @pytest.mark.asyncio
    async def test_embed_code(self, service):
        """Test code embedding."""
        code = "def hello():\n    print('Hello')"
        vector = await service.embed_code(
            code,
            file_path="/path/to/test.py",
            language="python"
        )
        
        assert vector.metadata["type"] == "code"
        assert vector.metadata["language"] == "python"
        assert vector.metadata["file_path"] == "/path/to/test.py"
    
    @pytest.mark.asyncio
    async def test_embed_code_auto_detect_language(self, service):
        """Test automatic language detection."""
        vector = await service.embed_code(
            "console.log('hello')",
            file_path="test.js"
        )
        
        assert vector.metadata["language"] == "javascript"
    
    @pytest.mark.asyncio
    async def test_embed_memory(self, service):
        """Test memory embedding."""
        vector = await service.embed_memory(
            "User prefers dark mode",
            memory_type="preference",
            tags=["ui", "settings"]
        )
        
        assert vector.metadata["type"] == "memory"
        assert vector.metadata["memory_type"] == "preference"
        assert "ui" in vector.metadata["tags"]
    
    @pytest.mark.asyncio
    async def test_search_memories(self, service):
        """Test memory search with filtering."""
        # Add memories
        await service.embed_memory("Python is great", "language", ["python"])
        await service.embed_memory("JavaScript is versatile", "language", ["js"])
        await service.embed_memory("I like Python", "preference", ["python"])
        
        # Search with type filter
        results = await service.search_memories("python", memory_type="language")
        
        assert len(results) > 0
        for result in results:
            assert result.vector.metadata["memory_type"] == "language"
    
    @pytest.mark.asyncio
    async def test_caching(self, service):
        """Test embedding caching."""
        text = "Cache test text"
        
        # First call
        vector1 = await service.embed_text(text)
        
        # Second call (should use cache)
        vector2 = await service.embed_text(text)
        
        # Should be identical (same object or same values)
        assert vector1.vector == vector2.vector
        
        # Check stats
        stats = service.get_stats()
        assert stats.cache_hits >= 1
    
    def test_delete(self, service):
        """Test deleting embeddings."""
        # Need to run async operation first
        import asyncio
        vector = asyncio.run(service.embed_text("To delete"))
        
        assert service.delete(vector.id) is True
        assert service.vector_store.get(vector.id) is None
        assert service.delete(vector.id) is False
    
    def test_clear(self, service):
        """Test clearing service."""
        import asyncio
        asyncio.run(service.embed_text("Text"))
        
        service.clear()
        
        assert len(service.vector_store.vectors) == 0
        assert len(service._embedding_cache) == 0
    
    def test_get_stats(self, service):
        """Test statistics."""
        import asyncio
        asyncio.run(service.embed_text("Test"))
        
        stats = service.get_stats()
        
        assert stats.total_vectors >= 1
        assert stats.total_dimensions > 0
        assert stats.api_calls >= 1


class TestEmbeddingStats:
    """Test EmbeddingStats."""
    
    def test_cache_hit_rate(self):
        """Test cache hit rate calculation."""
        stats = EmbeddingStats(cache_hits=75, cache_misses=25)
        assert stats.cache_hit_rate == 0.75
        
        # Empty stats
        stats2 = EmbeddingStats()
        assert stats2.cache_hit_rate == 0.0
    
    def test_default_values(self):
        """Test default values."""
        stats = EmbeddingStats()
        
        assert stats.total_vectors == 0
        assert stats.total_dimensions == 0
        assert stats.api_calls == 0
        assert stats.cache_hits == 0
        assert stats.cache_misses == 0


class TestGlobalInstance:
    """Test global instance functions."""
    
    def test_get_embedding_service(self):
        """Test getting global service."""
        clear_embedding_service()
        
        service1 = get_embedding_service()
        service2 = get_embedding_service()
        
        assert service1 is service2
    
    def test_clear_embedding_service(self):
        """Test clearing global service."""
        service = get_embedding_service()
        
        clear_embedding_service()
        
        service2 = get_embedding_service()
        assert service2 is not service


class TestEdgeCases:
    """Test edge cases."""
    
    @pytest.mark.asyncio
    async def test_empty_text(self):
        """Test embedding empty text."""
        service = EmbeddingService(persist=False)
        vector = await service.embed_text("")
        
        assert vector.text == ""
        assert len(vector.vector) == SimpleEmbeddingProvider.DIMENSIONS
    
    @pytest.mark.asyncio
    async def test_very_long_text(self):
        """Test embedding very long text."""
        service = EmbeddingService(persist=False)
        long_text = "word " * 10000
        
        vector = await service.embed_text(long_text)
        
        assert len(vector.vector) == SimpleEmbeddingProvider.DIMENSIONS
    
    @pytest.mark.asyncio
    async def test_unicode_text(self):
        """Test embedding unicode text."""
        service = EmbeddingService(persist=False)
        text = "Hello 世界 🌍 ñ"
        
        vector = await service.embed_text(text)
        
        assert vector.text == text
        assert len(vector.vector) == SimpleEmbeddingProvider.DIMENSIONS
    
    @pytest.mark.asyncio
    async def test_special_characters(self):
        """Test embedding special characters."""
        service = EmbeddingService(persist=False)
        text = "<script>alert('xss')</script> \n\t\\"
        
        vector = await service.embed_text(text)
        
        assert vector.text == text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
