"""Tests for file metadata cache service."""

import tempfile
from pathlib import Path

import pytest

from pilotcode.services.file_metadata_cache import (
    FileMetadataCache,
    LineEndingType,
    LRUCache,
    detect_file_encoding,
    detect_line_endings,
    detect_file_encoding_direct,
    detect_line_endings_direct,
    get_file_metadata_cache,
    clear_file_metadata_cache,
    cached_file_operation,
    FileMetadata,
)


class TestLRUCache:
    """Tests for LRUCache."""

    def test_basic_get_set(self):
        """Test basic get and set operations."""
        cache = LRUCache[str](max_size=3)

        cache.set("key1", "value1")
        cache.set("key2", "value2")

        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"
        assert cache.get("key3") is None

    def test_lru_eviction(self):
        """Test LRU eviction when max size is reached."""
        cache = LRUCache[int](max_size=3)

        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)

        # Access 'a' to make it recently used
        cache.get("a")

        # Add new item - should evict 'b' (least recently used)
        cache.set("d", 4)

        assert cache.get("a") == 1  # Still there
        assert cache.get("b") is None  # Evicted
        assert cache.get("c") == 3  # Still there
        assert cache.get("d") == 4  # New

    def test_update_moves_to_end(self):
        """Test that updating a key moves it to end."""
        cache = LRUCache[int](max_size=3)

        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)

        # Update 'a'
        cache.set("a", 10)

        # Add new item - should evict 'b'
        cache.set("d", 4)

        assert cache.get("a") == 10
        assert cache.get("b") is None
        assert cache.get("c") == 3

    def test_invalidate(self):
        """Test invalidating a specific key."""
        cache = LRUCache[str](max_size=3)

        cache.set("a", "value_a")
        cache.set("b", "value_b")

        assert cache.invalidate("a") is True
        assert cache.get("a") is None
        assert cache.get("b") == "value_b"
        assert cache.invalidate("a") is False

    def test_clear(self):
        """Test clearing all entries."""
        cache = LRUCache[str](max_size=3)

        cache.set("a", "value_a")
        cache.set("b", "value_b")

        cache.clear()

        assert cache.get("a") is None
        assert cache.get("b") is None
        assert cache.get_stats()["size"] == 0

    def test_stats(self):
        """Test cache statistics."""
        cache = LRUCache[str](max_size=5)

        # Misses
        cache.get("missing")
        cache.get("also_missing")

        # Hits
        cache.set("key", "value")
        cache.get("key")
        cache.get("key")

        stats = cache.get_stats()

        assert stats["size"] == 1
        assert stats["max_size"] == 5
        assert stats["hits"] == 2
        assert stats["misses"] == 2
        assert stats["hit_rate"] == 0.5


class TestFileMetadataCache:
    """Tests for FileMetadataCache."""

    def test_singleton_instance(self):
        """Test that global cache is singleton."""
        clear_file_metadata_cache()
        cache1 = get_file_metadata_cache()
        cache2 = get_file_metadata_cache()
        assert cache1 is cache2

    def test_encoding_cache(self):
        """Test encoding caching."""
        cache = FileMetadataCache(max_size=10)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Hello World")
            temp_path = f.name

        try:
            # Initially not cached
            assert cache.get_encoding(temp_path) is None

            # Set encoding
            cache.set_encoding(temp_path, "utf-8")

            # Now cached
            assert cache.get_encoding(temp_path) == "utf-8"

            # Invalidate and check cleared
            cache.invalidate(temp_path)
            assert cache.get_encoding(temp_path) is None
        finally:
            Path(temp_path).unlink()

    def test_line_ending_cache(self):
        """Test line ending caching."""
        cache = FileMetadataCache(max_size=10)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("line1\nline2\n")
            temp_path = f.name

        try:
            cache.set_line_ending(temp_path, LineEndingType.LF)
            assert cache.get_line_ending(temp_path) == LineEndingType.LF
        finally:
            Path(temp_path).unlink()

    def test_metadata_with_mtime_check(self):
        """Test that metadata respects file modification time."""
        cache = FileMetadataCache(max_size=10)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("content")
            temp_path = f.name

        try:
            path = Path(temp_path)
            stat = path.stat()

            # Set metadata
            metadata = FileMetadata(
                encoding="utf-8",
                line_ending=LineEndingType.LF,
                size=stat.st_size,
                mtime=stat.st_mtime,
            )
            cache.set_metadata(temp_path, metadata)

            # Should get cached value
            cached = cache.get_metadata(temp_path)
            assert cached is not None
            assert cached.encoding == "utf-8"

            # Modify file
            import time

            time.sleep(0.01)  # Ensure mtime changes
            path.write_text("modified content")

            # Cache should be invalid now
            cached = cache.get_metadata(temp_path)
            assert cached is None
        finally:
            path.unlink()

    def test_clear_all_caches(self):
        """Test clearing all caches."""
        cache = FileMetadataCache(max_size=10)

        cache.set_encoding("/fake/path", "utf-8")
        cache.set_line_ending("/fake/path", LineEndingType.LF)

        cache.clear()

        assert cache.get_encoding("/fake/path") is None
        assert cache.get_line_ending("/fake/path") is None


class TestEncodingDetection:
    """Tests for encoding detection."""

    def test_detect_utf8(self):
        """Test detecting UTF-8 encoding."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("Hello UTF-8: 你好世界")
            temp_path = f.name

        try:
            encoding = detect_file_encoding_direct(temp_path)
            assert encoding.lower() in ("utf-8", "utf8", "ascii")
        finally:
            Path(temp_path).unlink()

    def test_detect_with_fallback(self):
        """Test encoding detection with fallback."""
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".txt", delete=False) as f:
            # Write some binary content
            f.write(b"\x00\x01\x02\x03")
            temp_path = f.name

        try:
            encoding = detect_file_encoding_direct(temp_path)
            # Should return some encoding, not crash
            assert isinstance(encoding, str)
        finally:
            Path(temp_path).unlink()

    def test_detect_line_endings_lf(self):
        """Test detecting LF line endings."""
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".txt", delete=False) as f:
            f.write(b"line1\nline2\nline3\n")
            temp_path = f.name

        try:
            ending = detect_line_endings_direct(temp_path)
            assert ending == LineEndingType.LF
        finally:
            Path(temp_path).unlink()

    def test_detect_line_endings_crlf(self):
        """Test detecting CRLF line endings."""
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".txt", delete=False) as f:
            f.write(b"line1\r\nline2\r\n")
            temp_path = f.name

        try:
            ending = detect_line_endings_direct(temp_path)
            assert ending == LineEndingType.CRLF
        finally:
            Path(temp_path).unlink()

    def test_detect_line_endings_mixed(self):
        """Test detecting mixed line endings."""
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".txt", delete=False) as f:
            f.write(b"line1\r\nline2\nline3\r\n")
            temp_path = f.name

        try:
            ending = detect_line_endings_direct(temp_path)
            assert ending == LineEndingType.MIXED
        finally:
            Path(temp_path).unlink()

    def test_caching_integration(self):
        """Test that cached versions use the cache."""
        clear_file_metadata_cache()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("content")
            temp_path = f.name

        try:
            # First call should cache
            encoding1 = detect_file_encoding(temp_path)

            # Second call should use cache
            encoding2 = detect_file_encoding(temp_path)

            assert encoding1 == encoding2

            # Check cache stats
            cache = get_file_metadata_cache()
            stats = cache.get_stats()
            assert stats["encoding"]["hits"] >= 1
        finally:
            Path(temp_path).unlink()


class TestCachedFileOperation:
    """Tests for cached_file_operation decorator."""

    def test_method_caching(self):
        """Test caching on class methods."""

        class TestTool:
            def __init__(self):
                self.call_count = 0

            @cached_file_operation(max_size=10)
            def read_file(self, path: str) -> str:
                self.call_count += 1
                return Path(path).read_text()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test content")
            temp_path = f.name

        try:
            tool = TestTool()

            # First call
            result1 = tool.read_file(temp_path)
            assert result1 == "test content"
            assert tool.call_count == 1

            # Second call should use cache
            result2 = tool.read_file(temp_path)
            assert result2 == "test content"
            assert tool.call_count == 1  # Not incremented
        finally:
            Path(temp_path).unlink()

    def test_cache_invalidation_on_modify(self):
        """Test that cache is invalidated when file changes."""

        class TestTool:
            def __init__(self):
                self.call_count = 0

            @cached_file_operation(max_size=10)
            def read_file(self, path: str) -> str:
                self.call_count += 1
                return Path(path).read_text()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("original")
            temp_path = f.name

        try:
            tool = TestTool()
            path = Path(temp_path)

            # First call
            tool.read_file(temp_path)
            assert tool.call_count == 1

            # Modify file
            import time

            time.sleep(0.01)
            path.write_text("modified")

            # Should call again (cache miss due to mtime change)
            result = tool.read_file(temp_path)
            assert result == "modified"
            assert tool.call_count == 2
        finally:
            path.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
