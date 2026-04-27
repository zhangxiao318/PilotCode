"""Tests for numpy-optimized vector search in VectorStore."""

import math

import pytest

from pilotcode.services.embedding_service import (
    EmbeddingVector,
    SearchResult,
    VectorStore,
    HAS_NUMPY,
)


class TestDeleteByFilePath:
    """Tests for delete_by_file_path (incremental re-indexing fix)."""

    def test_delete_by_file_path_removes_matching(self):
        store = VectorStore(persist=False)
        store.add(EmbeddingVector(id="v1", text="a", vector=[1.0, 0.0], metadata={"file_path": "/a.py"}))
        store.add(EmbeddingVector(id="v2", text="b", vector=[0.0, 1.0], metadata={"file_path": "/b.py"}))
        store.add(EmbeddingVector(id="v3", text="c", vector=[1.0, 1.0], metadata={"file_path": "/a.py"}))

        deleted = store.delete_by_file_path("/a.py")
        assert deleted == 2
        assert store.get("v1") is None
        assert store.get("v3") is None
        assert store.get("v2") is not None

    def test_delete_by_file_path_no_match(self):
        store = VectorStore(persist=False)
        store.add(EmbeddingVector(id="v1", text="a", vector=[1.0, 0.0]))
        deleted = store.delete_by_file_path("/nonexistent.py")
        assert deleted == 0
        assert store.get("v1") is not None

    def test_delete_by_file_path_updates_matrix(self):
        store = VectorStore(persist=False)
        for i in range(5):
            store.add(
                EmbeddingVector(
                    id=f"v{i}",
                    text=f"t{i}",
                    vector=[float(i), 0.0],
                    metadata={"file_path": "/a.py" if i < 3 else "/b.py"},
                )
            )

        if HAS_NUMPY:
            assert store._matrix is not None
            old_shape = store._matrix.shape

        store.delete_by_file_path("/a.py")

        if HAS_NUMPY:
            assert store._matrix is not None
            assert store._matrix.shape[0] == old_shape[0] - 3


class TestNumpyBatchSearch:
    """Tests for numpy batch cosine similarity search."""

    @pytest.fixture
    def large_store(self):
        """Create a store with >100 vectors to trigger numpy path."""
        store = VectorStore(persist=False)
        vectors = []
        for i in range(150):
            # Create random-ish normalized vectors
            vec = [0.0] * 128
            vec[i % 128] = 1.0
            vectors.append(
                EmbeddingVector(
                    id=f"vec{i:03d}",
                    text=f"text {i}",
                    vector=vec,
                    metadata={"idx": i},
                )
            )
        store.add_many(vectors)
        return store

    def test_numpy_path_triggered(self, large_store):
        if not HAS_NUMPY:
            pytest.skip("numpy not available")
        assert large_store._matrix is not None
        assert large_store._matrix.shape == (150, 128)

    def test_batch_search_results(self, large_store):
        if not HAS_NUMPY:
            pytest.skip("numpy not available")

        # Query aligns with vec005 -> should return vec005 first
        query = [0.0] * 128
        query[5] = 1.0
        results = large_store.search(query, top_k=5)

        assert len(results) == 5
        assert results[0].vector.id == "vec005"
        assert results[0].score > 0.99
        # Scores should be descending
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score

    def test_batch_search_min_score(self, large_store):
        if not HAS_NUMPY:
            pytest.skip("numpy not available")

        # With 150 vectors and 128 dims, vec000 and vec128 are identical basis vectors.
        # min_score=0.9 should include both perfect matches.
        query = [0.0] * 128
        query[0] = 1.0
        results = large_store.search(query, top_k=10, min_score=0.9)

        assert len(results) == 2
        ids = {r.vector.id for r in results}
        assert ids == {"vec000", "vec128"}

    def test_batch_search_empty_store(self):
        store = VectorStore(persist=False)
        results = store.search([1.0, 0.0], top_k=5)
        assert results == []

    def test_batch_search_few_vectors_uses_fallback(self):
        """With <=100 vectors, Python loop fallback is used."""
        store = VectorStore(persist=False)
        for i in range(10):
            vec = [0.0] * 4
            vec[i % 4] = 1.0
            store.add(EmbeddingVector(id=f"v{i}", text=f"t{i}", vector=vec))

        query = [1.0, 0.0, 0.0, 0.0]
        results = store.search(query, top_k=3)
        assert len(results) == 3
        assert results[0].rank == 1

    def test_consistency_between_paths(self):
        """Numpy batch and Python fallback should give same ordering/scores."""
        store = VectorStore(persist=False)
        vectors = []
        for i in range(10):
            vec = [0.0] * 8
            vec[i % 8] = 1.0
            vectors.append(EmbeddingVector(id=f"v{i}", text=f"t{i}", vector=vec))
        store.add_many(vectors)

        query = [0.0] * 8
        query[3] = 1.0
        # Manually force Python path by temporarily setting _matrix None
        saved_matrix = store._matrix
        saved_ids = store._ids
        store._matrix = None
        store._ids = []
        results_py = store.search(query, top_k=5)
        store._matrix = saved_matrix
        store._ids = saved_ids
        results_np = store.search(query, top_k=5)

        assert len(results_py) == len(results_np)
        for r1, r2 in zip(results_py, results_np):
            assert r1.vector.id == r2.vector.id
            assert abs(r1.score - r2.score) < 1e-5


class TestMatrixRebuild:
    """Tests for _rebuild_matrix behavior."""

    def test_rebuild_on_dimension_mismatch(self):
        if not HAS_NUMPY:
            pytest.skip("numpy not available")
        store = VectorStore(persist=False)
        store.add(EmbeddingVector(id="v1", text="a", vector=[1.0, 0.0]))
        assert store._matrix is not None

        # Adding vector with different dimension should trigger rebuild
        store.add(EmbeddingVector(id="v2", text="b", vector=[1.0, 0.0, 0.0]))
        # After rebuild, matrix should include both if dimensions now match globally
        # Actually dimensions differ, so matrix should be None
        assert store._matrix is None

    def test_rebuild_on_replace(self):
        if not HAS_NUMPY:
            pytest.skip("numpy not available")
        store = VectorStore(persist=False)
        store.add(EmbeddingVector(id="v1", text="a", vector=[1.0, 0.0]))
        old_matrix = store._matrix

        store.add(EmbeddingVector(id="v1", text="a2", vector=[0.5, 0.5]))
        # Matrix should be updated in-place for replacement
        assert store._matrix is not None
        # Same object if replaced in-place
        if HAS_NUMPY:
            # Check the value changed
            idx = store._ids.index("v1")
            assert store._matrix[idx][0] == pytest.approx(0.5)

    def test_clear_clears_matrix(self):
        if not HAS_NUMPY:
            pytest.skip("numpy not available")
        store = VectorStore(persist=False)
        store.add(EmbeddingVector(id="v1", text="a", vector=[1.0, 0.0]))
        store.clear()
        assert store._matrix is None
        assert store._ids == []


class TestCosineSimilarityBatch:
    """Tests for _cosine_similarity_batch static method."""

    @pytest.mark.skipif(not HAS_NUMPY, reason="numpy not available")
    def test_orthogonal_vectors(self):
        import numpy as np

        query = np.array([1.0, 0.0], dtype=np.float32)
        matrix = np.array([[0.0, 1.0], [0.0, 2.0]], dtype=np.float32)
        scores = VectorStore._cosine_similarity_batch(query, matrix)
        assert abs(scores[0]) < 1e-6
        assert abs(scores[1]) < 1e-6

    @pytest.mark.skipif(not HAS_NUMPY, reason="numpy not available")
    def test_identical_vectors(self):
        import numpy as np

        query = np.array([1.0, 2.0], dtype=np.float32)
        matrix = np.array([[1.0, 2.0], [2.0, 4.0]], dtype=np.float32)
        scores = VectorStore._cosine_similarity_batch(query, matrix)
        assert abs(scores[0] - 1.0) < 1e-6
        assert abs(scores[1] - 1.0) < 1e-6

    @pytest.mark.skipif(not HAS_NUMPY, reason="numpy not available")
    def test_opposite_vectors(self):
        import numpy as np

        query = np.array([1.0, 0.0], dtype=np.float32)
        matrix = np.array([[-1.0, 0.0]], dtype=np.float32)
        scores = VectorStore._cosine_similarity_batch(query, matrix)
        assert abs(scores[0] - (-1.0)) < 1e-6


class TestEmbeddingServiceDeleteByFilePath:
    """Tests for EmbeddingService.delete_by_file_path wrapper."""

    @pytest.mark.asyncio
    async def test_service_wrapper(self):
        from pilotcode.services.embedding_service import EmbeddingService

        service = EmbeddingService(persist=False)
        await service.embed_code("def a(): pass", file_path="/x.py")
        await service.embed_code("def b(): pass", file_path="/x.py")
        await service.embed_code("def c(): pass", file_path="/y.py")

        assert len(service.vector_store.vectors) == 3
        deleted = service.delete_by_file_path("/x.py")
        assert deleted == 2
        assert len(service.vector_store.vectors) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
