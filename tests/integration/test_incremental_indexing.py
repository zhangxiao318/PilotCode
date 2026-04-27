"""Tests for incremental indexing bug fixes and optimizations."""

import asyncio
import time
from pathlib import Path

import pytest

from pilotcode.services.codebase_indexer import CodebaseIndexer
from pilotcode.services.code_index import CodeIndexer


class TestIncrementalIndexingFixes:
    """Tests for the 3 incremental indexing bug fixes."""

    @pytest.fixture
    def indexer(self, temp_dir):
        """Create a CodebaseIndexer with in-memory embedding service."""
        from pilotcode.services.embedding_service import EmbeddingService

        emb = EmbeddingService(persist=False)
        idx = CodebaseIndexer(temp_dir, embedding_service=emb)
        # Tests run in tests/tmp/ which is in IGNORE_DIRS; remove tmp-related entries
        # so that test files are not silently ignored.
        idx.IGNORE_DIRS = {d for d in idx.IGNORE_DIRS if d not in ("tmp", "temp", "_tmp", "_temp")}
        return idx

    def _create_files(self, directory, spec):
        """Helper to create files from a dict {rel_path: content}."""
        for rel_path, content in spec.items():
            path = directory / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

    @pytest.mark.asyncio
    async def test_incremental_ignores_max_files(self, indexer, temp_dir):
        """Bugfix 1: incremental=True scans ALL files, max_files is ignored."""
        # Create 15 files
        files = {f"src/file{i:02d}.py": f"def func{i}(): pass\n" for i in range(15)}
        self._create_files(temp_dir, files)

        # First full index
        stats = await indexer.index_codebase(incremental=False, max_files=5)
        # Only 5 files indexed in non-incremental mode with max_files=5
        assert stats.total_files == 5

        # Now incremental: should scan all 15 files even with max_files=5
        stats = await indexer.index_codebase(incremental=True, max_files=5)
        # All 15 discovered; 10 are new/changed
        assert stats.total_files == 15

    @pytest.mark.asyncio
    async def test_deleted_files_removed(self, indexer, temp_dir):
        """Bugfix 3: deleted files are detected and removed from index."""
        files = {
            "keep.py": "def keep(): pass\n",
            "remove.py": "def remove(): pass\n",
        }
        self._create_files(temp_dir, files)

        await indexer.index_codebase(incremental=False)
        assert "remove.py" in {Path(f).name for f in indexer._indexed_files}

        # Delete one file
        (temp_dir / "remove.py").unlink()

        # Incremental re-index should detect deletion
        await indexer.index_codebase(incremental=True)
        indexed_names = {Path(f).name for f in indexer._indexed_files}
        assert "remove.py" not in indexed_names
        assert "keep.py" in indexed_names

    @pytest.mark.asyncio
    async def test_old_embeddings_cleared_on_reindex(self, indexer, temp_dir):
        """Bugfix 2: old embedding vectors deleted before re-indexing."""
        file_path = temp_dir / "module.py"
        file_path.write_text("def old_func(): pass\n")

        await indexer.index_codebase(incremental=False)
        # Embedding service should have vectors for module.py
        vectors_before = [
            v for v in indexer.embedding_service.vector_store.vectors.values()
            if v.metadata.get("file_path") == str(file_path)
        ]
        assert len(vectors_before) > 0

        # Modify file
        file_path.write_text("def new_func(): pass\n")
        await indexer.index_codebase(incremental=True)

        # Old vectors should be gone, new ones present
        vectors_after = [
            v for v in indexer.embedding_service.vector_store.vectors.values()
            if v.metadata.get("file_path") == str(file_path)
        ]
        assert len(vectors_after) > 0
        # Ensure no ghost vectors from old content
        texts = [v.text for v in vectors_after]
        assert all("old_func" not in t for t in texts)

    def test_filter_unchanged_files_mtime_fast_path(self, indexer, temp_dir):
        """Two-layer filter: mtime fast path skips unchanged files."""
        file_path = temp_dir / "stable.py"
        file_path.write_text("def stable(): pass\n")

        # First index
        asyncio.run(indexer.index_codebase(incremental=False))

        # Second incremental call: file unchanged
        files = [file_path]
        changed = indexer._filter_unchanged_files(files)
        assert len(changed) == 0

    def test_filter_unchanged_files_hash_detects_change(self, indexer, temp_dir):
        """SHA256 layer detects content changes when mtime record is missing."""
        file_path = temp_dir / "mutant.py"
        file_path.write_text("def v1(): pass\n")

        # Index once (stores hash and mtime)
        asyncio.run(indexer.index_codebase(incremental=False))

        # Modify content and remove mtime record so layer 1 cannot short-circuit
        file_path.write_text("def v2(): pass\n")
        indexer._file_hashes.pop(f"{file_path}:mtime", None)

        changed = indexer._filter_unchanged_files([file_path])
        assert len(changed) == 1

    def test_estimate_indexing_time(self, indexer):
        """Progress estimation based on language mix."""
        files = [Path("a.py")] * 100 + [Path("b.go")] * 50
        est = indexer._estimate_indexing_time(files)
        # 100 python * 0.003 + 50 go * 0.014 + 0.1 init overhead
        assert est > 0
        assert est < 10  # Should be sub-second for small sets

    def test_estimate_indexing_time_empty(self, indexer):
        assert indexer._estimate_indexing_time([]) == 0.0

    @pytest.mark.asyncio
    async def test_progress_callback_invoked(self, indexer, temp_dir):
        """Progress callback receives (file_path, current, total)."""
        files = {f"f{i}.py": "pass\n" for i in range(5)}
        self._create_files(temp_dir, files)

        progress_calls = []

        def cb(file_path, current, total):
            progress_calls.append((file_path, current, total))

        indexer.set_progress_callback(cb)
        await indexer.index_codebase(incremental=False)

        assert len(progress_calls) > 0
        for fp, cur, tot in progress_calls:
            assert isinstance(cur, int)
            assert isinstance(tot, int)
            assert cur <= tot

    @pytest.mark.asyncio
    async def test_checkpoint_saves_state(self, indexer, temp_dir):
        """Checkpoint saves intermediate state during indexing."""
        files = {f"f{i}.py": "pass\n" for i in range(20)}
        self._create_files(temp_dir, files)

        await indexer.index_codebase(incremental=False)
        assert indexer._cache_path.exists()

    def test_find_source_files_prefers_git(self, temp_dir):
        """Git repos use git ls-files instead of rglob."""
        import subprocess

        # Init git repo
        subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"], cwd=temp_dir, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "config", "user.name", "T"], cwd=temp_dir, capture_output=True, check=True
        )

        (temp_dir / "tracked.py").write_text("pass\n")
        (temp_dir / "untracked.pyc").write_text("pass\n")
        subprocess.run(["git", "add", "."], cwd=temp_dir, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=temp_dir, capture_output=True, check=True
        )

        indexer = CodebaseIndexer(temp_dir)
        indexer.IGNORE_DIRS = {d for d in indexer.IGNORE_DIRS if d not in ("tmp", "temp", "_tmp", "_temp")}
        files = indexer._find_source_files()
        names = {f.name for f in files}
        assert "tracked.py" in names
        # .pyc is not in SUPPORTED_EXTENSIONS
        assert "untracked.pyc" not in names

    def test_find_source_files_rglob_fallback(self, temp_dir):
        """Non-git directories fall back to rglob."""
        (temp_dir / "a.py").write_text("pass\n")
        (temp_dir / "b.js").write_text("//\n")

        indexer = CodebaseIndexer(temp_dir)
        indexer.IGNORE_DIRS = {d for d in indexer.IGNORE_DIRS if d not in ("tmp", "temp", "_tmp", "_temp")}
        files = indexer._find_source_files()
        names = {f.name for f in files}
        assert "a.py" in names
        assert "b.js" in names

    def test_should_ignore_hidden(self, temp_dir):
        indexer = CodebaseIndexer(temp_dir)
        assert indexer._should_ignore(temp_dir / ".hidden" / "file.py") is True

    def test_should_ignore_build_artifacts(self, temp_dir):
        indexer = CodebaseIndexer(temp_dir)
        # test files live under tests/tmp which is in IGNORE_DIRS; remove it for this test
        indexer.IGNORE_DIRS = {d for d in indexer.IGNORE_DIRS if d not in ("tmp", "temp", "_tmp", "_temp")}
        assert indexer._should_ignore(temp_dir / "node_modules" / "x.js") is True
        assert indexer._should_ignore(temp_dir / "build" / "out.o") is True
        # Create the file so it exists (otherwise _should_ignore returns True on OSError)
        src_file = temp_dir / "src" / "main.py"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("pass\n")
        assert indexer._should_ignore(src_file) is False

    def test_should_ignore_large_files(self, temp_dir):
        indexer = CodebaseIndexer(temp_dir)
        large = temp_dir / "large.py"
        large.write_text("x" * 2_000_000)
        assert indexer._should_ignore(large) is True

    @pytest.mark.asyncio
    async def test_hierarchical_index_built_for_large_projects(self, indexer, temp_dir):
        """Hierarchical index auto-built when >10 files."""
        files = {f"src/f{i}.py": f"def func{i}(): pass\n" for i in range(15)}
        self._create_files(temp_dir, files)

        await indexer.index_codebase(incremental=False)
        assert indexer._hierarchical_builder is not None
        master = indexer._hierarchical_builder.get_master_index()
        assert master is not None
        assert master.total_files == 15

    @pytest.mark.asyncio
    async def test_hierarchical_index_skips_small_projects(self, indexer, temp_dir):
        """Hierarchical index not built for <=10 files."""
        files = {f"f{i}.py": "pass\n" for i in range(3)}
        self._create_files(temp_dir, files)

        await indexer.index_codebase(incremental=False)
        # Either no builder or builder with no master index
        if indexer._hierarchical_builder:
            assert indexer._hierarchical_builder.get_master_index() is None

    @pytest.mark.asyncio
    async def test_build_context_injects_memory_kb(self, indexer, temp_dir):
        """Memory KB results are injected into build_context."""
        # Add a memory entry
        indexer._memory_kb.add_fact("Project uses asyncio everywhere", tags=["architecture"])

        # Create a source file so there's something to index
        (temp_dir / "main.py").write_text("import asyncio\n")
        await indexer.index_codebase(incremental=False)

        context = await indexer.build_context("asyncio patterns")
        # Memory snippet should be present with high relevance
        assert any(
            "asyncio" in s.content.lower() and s.relevance_score >= 0.9
            for s in context.snippets
        )

    def test_list_subgraphs(self, indexer, temp_dir):
        """list_subgraphs returns info after hierarchical index built."""
        files = {f"src/f{i}.py": f"def func{i}(): pass\n" for i in range(15)}
        self._create_files(temp_dir, files)
        asyncio.run(indexer.index_codebase(incremental=False))

        subgraphs = indexer.list_subgraphs()
        assert len(subgraphs) > 0
        assert "id" in subgraphs[0]
        assert "name" in subgraphs[0]
        assert "file_count" in subgraphs[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
