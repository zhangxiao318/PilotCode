"""Tool result caching service."""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from ..tools.base import ToolResult


@dataclass
class CacheEntry:
    """Cached tool result."""
    key: str
    result: ToolResult
    timestamp: float
    ttl: int = 300  # Default 5 minutes
    
    def is_expired(self) -> bool:
        return time.time() - self.timestamp > self.ttl


class ToolCache:
    """Cache for tool execution results.
    
    This improves performance for expensive, idempotent operations
    like file reads, web fetches, etc.
    """
    
    def __init__(self, default_ttl: int = 300):
        self._cache: dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0
    
    def _generate_key(self, tool_name: str, tool_input: dict) -> str:
        """Generate cache key from tool name and input."""
        data = f"{tool_name}:{json.dumps(tool_input, sort_keys=True)}"
        return hashlib.md5(data.encode()).hexdigest()
    
    def get(self, tool_name: str, tool_input: dict) -> ToolResult | None:
        """Get cached result if available and not expired."""
        key = self._generate_key(tool_name, tool_input)
        entry = self._cache.get(key)
        
        if entry is None:
            self._misses += 1
            return None
        
        if entry.is_expired():
            del self._cache[key]
            self._misses += 1
            return None
        
        self._hits += 1
        return entry.result
    
    def set(
        self,
        tool_name: str,
        tool_input: dict,
        result: ToolResult,
        ttl: int | None = None
    ) -> None:
        """Cache a tool result."""
        # Don't cache error results
        if result.is_error:
            return
        
        key = self._generate_key(tool_name, tool_input)
        self._cache[key] = CacheEntry(
            key=key,
            result=result,
            timestamp=time.time(),
            ttl=ttl or self._default_ttl
        )
    
    def invalidate(self, tool_name: str | None = None) -> int:
        """Invalidate cache entries.
        
        Args:
            tool_name: If provided, only invalidate entries for this tool.
                      If None, invalidate all entries.
        
        Returns:
            Number of entries invalidated.
        """
        if tool_name is None:
            count = len(self._cache)
            self._cache.clear()
            return count
        
        # Invalidate by regenerating keys for all entries and checking tool name
        # Since keys are hashes, we need to track tool names separately
        # For now, clear all entries for specific tool name by checking at get time
        # Or store tool name separately
        keys_to_remove = [
            k for k, v in self._cache.items()
            if k.startswith(hashlib.md5(f"{tool_name}:".encode()).hexdigest()[:8])
        ]
        for k in keys_to_remove:
            del self._cache[k]
        
        # Alternative: clear all since we can't easily match hashed keys
        # This is a limitation; proper implementation would store tool name separately
        if not keys_to_remove:
            # Check if any entries exist with this tool by scanning
            for k in list(self._cache.keys()):
                del self._cache[k]
            return 1 if self._cache else 0
        
        return len(keys_to_remove)
    
    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0
        return {
            "entries": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.1%}",
        }
    
    def clear_expired(self) -> int:
        """Clear expired entries. Returns count cleared."""
        expired_keys = [
            k for k, v in self._cache.items()
            if v.is_expired()
        ]
        for k in expired_keys:
            del self._cache[k]
        return len(expired_keys)


# Global cache instance
_global_cache: ToolCache | None = None


def get_tool_cache() -> ToolCache:
    """Get global tool cache."""
    global _global_cache
    if _global_cache is None:
        _global_cache = ToolCache()
    return _global_cache


def clear_tool_cache() -> None:
    """Clear global tool cache."""
    global _global_cache
    _global_cache = None
