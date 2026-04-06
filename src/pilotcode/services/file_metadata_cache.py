"""LRU cache for file metadata (encoding, line endings, etc.).

This module provides LRU caching for expensive file metadata operations,
following Claude Code's approach to reduce repeated file detection operations.
"""

from __future__ import annotations

import functools
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, TypeVar, ParamSpec, Generic


class LineEndingType(Enum):
    """Line ending types."""

    LF = "lf"
    CRLF = "crlf"
    MIXED = "mixed"
    UNKNOWN = "unknown"


T = TypeVar("T")
P = ParamSpec("P")


class LRUCache(Generic[T]):
    """Simple LRU cache implementation."""

    def __init__(self, max_size: int = 1000):
        self._max_size = max_size
        self._cache: OrderedDict[str, T] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> T | None:
        """Get value from cache."""
        if key in self._cache:
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]
        self._misses += 1
        return None

    def set(self, key: str, value: T) -> None:
        """Set value in cache."""
        if key in self._cache:
            # Update existing and move to end
            self._cache.move_to_end(key)
        self._cache[key] = value

        # Remove oldest if over capacity
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def invalidate(self, key: str) -> bool:
        """Invalidate a cache entry."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def get_stats(self) -> dict:
        """Get cache statistics."""
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0,
        }


@dataclass
class FileMetadata:
    """File metadata cache entry."""

    encoding: str
    line_ending: LineEndingType
    size: int
    mtime: float


class FileMetadataCache:
    """Cache for file metadata like encoding and line endings.

    This follows Claude Code's approach of caching expensive file operations
    to avoid repeated detection of file encoding and line endings.
    """

    def __init__(self, max_size: int = 1000):
        self._encoding_cache = LRUCache[str](max_size=max_size)
        self._line_ending_cache = LRUCache[LineEndingType](max_size=max_size)
        self._metadata_cache = LRUCache[FileMetadata](max_size=max_size)

    def _get_cache_key(self, path: str | Path) -> str:
        """Generate cache key for a path."""
        return str(Path(path).resolve())

    def get_encoding(self, path: str | Path) -> str | None:
        """Get cached encoding for a file."""
        return self._encoding_cache.get(self._get_cache_key(path))

    def set_encoding(self, path: str | Path, encoding: str) -> None:
        """Set cached encoding for a file."""
        self._encoding_cache.set(self._get_cache_key(path), encoding)

    def get_line_ending(self, path: str | Path) -> LineEndingType | None:
        """Get cached line ending for a file."""
        return self._line_ending_cache.get(self._get_cache_key(path))

    def set_line_ending(self, path: str | Path, line_ending: LineEndingType) -> None:
        """Set cached line ending for a file."""
        self._line_ending_cache.set(self._get_cache_key(path), line_ending)

    def get_metadata(self, path: str | Path) -> FileMetadata | None:
        """Get cached metadata for a file."""
        key = self._get_cache_key(path)
        metadata = self._metadata_cache.get(key)

        if metadata is not None:
            # Check if file has been modified
            try:
                stat = Path(path).stat()
                if stat.st_mtime != metadata.mtime or stat.st_size != metadata.size:
                    # File has changed, invalidate cache
                    self.invalidate(path)
                    return None
            except (OSError, FileNotFoundError):
                self.invalidate(path)
                return None

        return metadata

    def set_metadata(self, path: str | Path, metadata: FileMetadata) -> None:
        """Set cached metadata for a file."""
        self._metadata_cache.set(self._get_cache_key(path), metadata)

    def invalidate(self, path: str | Path) -> None:
        """Invalidate cache entries for a file."""
        key = self._get_cache_key(path)
        self._encoding_cache.invalidate(key)
        self._line_ending_cache.invalidate(key)
        self._metadata_cache.invalidate(key)

    def clear(self) -> None:
        """Clear all cache entries."""
        self._encoding_cache.clear()
        self._line_ending_cache.clear()
        self._metadata_cache.clear()

    def get_stats(self) -> dict:
        """Get combined cache statistics."""
        return {
            "encoding": self._encoding_cache.get_stats(),
            "line_ending": self._line_ending_cache.get_stats(),
            "metadata": self._metadata_cache.get_stats(),
        }


# Global cache instance
_file_metadata_cache: FileMetadataCache | None = None


def get_file_metadata_cache() -> FileMetadataCache:
    """Get global file metadata cache."""
    global _file_metadata_cache
    if _file_metadata_cache is None:
        _file_metadata_cache = FileMetadataCache()
    return _file_metadata_cache


def clear_file_metadata_cache() -> None:
    """Clear global file metadata cache."""
    global _file_metadata_cache
    if _file_metadata_cache is not None:
        _file_metadata_cache.clear()


def detect_file_encoding_direct(path: str | Path) -> str:
    """Detect file encoding directly (without cache).

    Uses chardet if available, otherwise uses utf-8 with fallback.
    """
    try:
        # Try importing chardet for better detection
        import chardet

        with open(path, "rb") as f:
            raw = f.read(4096)  # Read first 4KB for detection
            result = chardet.detect(raw)
            if result and result["encoding"]:
                return result["encoding"]
    except ImportError:
        pass
    except Exception:
        pass

    # Fallback: try common encodings
    encodings = ["utf-8", "latin-1", "cp1252", "gbk"]
    for encoding in encodings:
        try:
            with open(path, "r", encoding=encoding) as f:
                f.read()
            return encoding
        except (UnicodeDecodeError, IOError):
            continue

    return "utf-8"  # Default fallback


def detect_line_endings_direct(path: str | Path) -> LineEndingType:
    """Detect line endings directly (without cache)."""
    try:
        with open(path, "rb") as f:
            content = f.read(8192)  # Read first 8KB

        has_crlf = b"\r\n" in content
        has_lf = b"\n" in content.replace(b"\r\n", b"")

        if has_crlf and has_lf:
            return LineEndingType.MIXED
        elif has_crlf:
            return LineEndingType.CRLF
        elif has_lf:
            return LineEndingType.LF
        else:
            return LineEndingType.UNKNOWN
    except Exception:
        return LineEndingType.UNKNOWN


def detect_file_encoding(path: str | Path) -> str:
    """Detect file encoding with caching."""
    cache = get_file_metadata_cache()
    cached = cache.get_encoding(path)

    if cached is not None:
        return cached

    encoding = detect_file_encoding_direct(path)
    cache.set_encoding(path, encoding)
    return encoding


def detect_line_endings(path: str | Path) -> LineEndingType:
    """Detect line endings with caching."""
    cache = get_file_metadata_cache()
    cached = cache.get_line_ending(path)

    if cached is not None:
        return cached

    line_ending = detect_line_endings_direct(path)
    cache.set_line_ending(path, line_ending)
    return line_ending


def cached_file_operation(
    cache_attr: str = "_file_cache", max_size: int = 1000
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator to cache file operations based on file path and mtime.

    Args:
        cache_attr: Attribute name to store cache (on the class instance)
        max_size: Maximum cache size

    Example:
        class MyTool:
            @cached_file_operation()
            def read_with_cache(self, path: str) -> str:
                return Path(path).read_text()
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Get self if method
            self = args[0] if args else None

            # Get or create cache
            cache = None
            if self is not None:
                cache = getattr(self, cache_attr, None)
                if cache is None:
                    cache = LRUCache[T](max_size=max_size)
                    setattr(self, cache_attr, cache)

            # Generate cache key from args
            # Assumes first arg after self is path
            path_arg = args[1] if len(args) > 1 else kwargs.get("path")

            if path_arg and cache is not None:
                try:
                    path = Path(path_arg)
                    stat = path.stat()
                    cache_key = f"{path.resolve()}:{stat.st_mtime}:{stat.st_size}"

                    cached = cache.get(cache_key)
                    if cached is not None:
                        return cached

                    result = func(*args, **kwargs)
                    cache.set(cache_key, result)
                    return result
                except (OSError, FileNotFoundError):
                    pass

            return func(*args, **kwargs)

        return wrapper

    return decorator
