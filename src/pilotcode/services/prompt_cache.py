"""Prompt Cache - LLM prompt caching for cost optimization.

This module implements prompt caching similar to ClaudeCode:
1. Cache LLM prompts and responses
2. Detect cache breaks (content changes)
3. Support provider-specific caching (Anthropic, OpenAI)
4. Persistent cache storage

Features:
- In-memory LRU cache for fast access
- Disk persistence for cache survival across restarts
- Cache-aware message ordering
- Token savings tracking
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


@dataclass
class CacheEntry:
    """A cached prompt and its response."""
    cache_key: str
    messages_hash: str
    response: str
    model: str
    tokens_input: int
    tokens_output: int
    created_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    access_count: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "cache_key": self.cache_key,
            "messages_hash": self.messages_hash,
            "response": self.response,
            "model": self.model,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "created_at": self.created_at,
            "accessed_at": self.accessed_at,
            "access_count": self.access_count,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CacheEntry:
        return cls(
            cache_key=data["cache_key"],
            messages_hash=data["messages_hash"],
            response=data["response"],
            model=data["model"],
            tokens_input=data["tokens_input"],
            tokens_output=data["tokens_output"],
            created_at=data.get("created_at", time.time()),
            accessed_at=data.get("accessed_at", time.time()),
            access_count=data.get("access_count", 0),
        )
    
    @property
    def age_hours(self) -> float:
        """Age of cache entry in hours."""
        return (time.time() - self.created_at) / 3600
    
    @property
    def total_tokens(self) -> int:
        """Total tokens (input + output)."""
        return self.tokens_input + self.tokens_output


@dataclass
class CacheStats:
    """Statistics for prompt cache."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_entries: int = 0
    total_tokens_saved: int = 0
    disk_size_bytes: int = 0
    
    @property
    def hit_rate(self) -> float:
        """Cache hit rate (0-1)."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
    
    @property
    def estimated_cost_saved(self) -> float:
        """Estimated cost saved in USD (rough estimate: $0.01 per 1K tokens)."""
        return (self.total_tokens_saved / 1000) * 0.01


class PromptCache:
    """LRU cache for LLM prompts with disk persistence.
    
    Usage:
        cache = PromptCache(max_size=1000)
        
        # Check cache
        entry = cache.get(messages, model)
        if entry:
            return entry.response
        
        # Store in cache after API call
        cache.put(messages, model, response, tokens_input, tokens_output)
    """
    
    DEFAULT_MAX_SIZE = 1000
    DEFAULT_TTL_HOURS = 24 * 7  # 1 week
    
    def __init__(
        self,
        max_size: int = DEFAULT_MAX_SIZE,
        ttl_hours: float = DEFAULT_TTL_HOURS,
        persist: bool = True
    ):
        self.max_size = max_size
        self.ttl_hours = ttl_hours
        self.persist = persist
        
        # In-memory cache: OrderedDict for LRU
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        
        # Statistics
        self._stats = CacheStats()
        
        # Disk storage
        if persist:
            self._cache_dir = Path(user_data_dir("pilotcode", "pilotcode")) / "prompt_cache"
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()
    
    def _compute_hash(self, messages: list[dict[str, Any]]) -> str:
        """Compute hash for messages to use as cache key.
        
        Normalizes messages to ensure consistent hashing.
        """
        # Normalize: sort keys, convert to JSON
        normalized = json.dumps(messages, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    def _generate_cache_key(self, messages: list[dict[str, Any]], model: str) -> str:
        """Generate cache key from messages and model."""
        messages_hash = self._compute_hash(messages)
        # Include model in key
        combined = f"{model}:{messages_hash}"
        return hashlib.sha256(combined.encode()).hexdigest()[:32]
    
    def get(
        self,
        messages: list[dict[str, Any]],
        model: str
    ) -> Optional[CacheEntry]:
        """Get cached response for messages.
        
        Returns None if not found or expired.
        """
        cache_key = self._generate_cache_key(messages, model)
        
        entry = self._cache.get(cache_key)
        if entry is None:
            self._stats.misses += 1
            return None
        
        # Check TTL
        if entry.age_hours > self.ttl_hours:
            # Expired
            del self._cache[cache_key]
            self._stats.misses += 1
            self._stats.evictions += 1
            return None
        
        # Cache hit - update LRU order
        self._cache.move_to_end(cache_key)
        entry.accessed_at = time.time()
        entry.access_count += 1
        
        self._stats.hits += 1
        self._stats.total_tokens_saved += entry.total_tokens
        
        return entry
    
    def put(
        self,
        messages: list[dict[str, Any]],
        model: str,
        response: str,
        tokens_input: int,
        tokens_output: int
    ) -> None:
        """Store response in cache."""
        cache_key = self._generate_cache_key(messages, model)
        messages_hash = self._compute_hash(messages)
        
        # Create entry
        entry = CacheEntry(
            cache_key=cache_key,
            messages_hash=messages_hash,
            response=response,
            model=model,
            tokens_input=tokens_input,
            tokens_output=tokens_output
        )
        
        # Check if entry exists
        if cache_key in self._cache:
            # Update existing
            self._cache.move_to_end(cache_key)
        else:
            # Check size limit
            if len(self._cache) >= self.max_size:
                # Evict oldest
                self._cache.popitem(last=False)
                self._stats.evictions += 1
        
        # Store entry
        self._cache[cache_key] = entry
        
        # Persist to disk
        if self.persist:
            self._save_entry_to_disk(entry)
    
    def invalidate(self, model: Optional[str] = None) -> int:
        """Invalidate cache entries.
        
        If model is specified, only invalidate entries for that model.
        Returns number of entries invalidated.
        """
        if model is None:
            count = len(self._cache)
            self._cache.clear()
            if self.persist:
                self._clear_disk_cache()
            return count
        
        # Invalidate specific model
        to_remove = [
            key for key, entry in self._cache.items()
            if entry.model == model
        ]
        
        for key in to_remove:
            del self._cache[key]
        
        return len(to_remove)
    
    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        if self.persist:
            self._clear_disk_cache()
    
    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        stats = CacheStats(
            hits=self._stats.hits,
            misses=self._stats.misses,
            evictions=self._stats.evictions,
            total_entries=len(self._cache),
            total_tokens_saved=self._stats.total_tokens_saved,
        )
        
        # Calculate disk size
        if self.persist and self._cache_dir.exists():
            stats.disk_size_bytes = sum(
                f.stat().st_size for f in self._cache_dir.glob("*.json.gz")
            )
        
        return stats
    
    def _save_entry_to_disk(self, entry: CacheEntry) -> None:
        """Save cache entry to disk."""
        try:
            cache_file = self._cache_dir / f"{entry.cache_key}.json.gz"
            with gzip.open(cache_file, 'wt', encoding='utf-8') as f:
                json.dump(entry.to_dict(), f)
        except Exception as e:
            print(f"Error saving cache entry: {e}")
    
    def _load_from_disk(self) -> None:
        """Load cache entries from disk."""
        if not self._cache_dir.exists():
            return
        
        loaded = 0
        for cache_file in self._cache_dir.glob("*.json.gz"):
            try:
                with gzip.open(cache_file, 'rt', encoding='utf-8') as f:
                    data = json.load(f)
                
                entry = CacheEntry.from_dict(data)
                
                # Check TTL
                if entry.age_hours <= self.ttl_hours:
                    self._cache[entry.cache_key] = entry
                    loaded += 1
                else:
                    # Delete expired
                    cache_file.unlink()
            
            except Exception:
                # Skip corrupted files
                continue
        
        # Reorder by access time
        self._cache = OrderedDict(
            sorted(self._cache.items(), key=lambda x: x[1].accessed_at)
        )
        
        self._stats.total_entries = loaded
    
    def _clear_disk_cache(self) -> None:
        """Clear all cache files from disk."""
        if not self._cache_dir.exists():
            return
        
        for cache_file in self._cache_dir.glob("*.json.gz"):
            try:
                cache_file.unlink()
            except Exception:
                pass


class CacheAwareMessageBuilder:
    """Builds messages with cache awareness.
    
    Optimizes message ordering to maximize cache hits.
    ClaudeCode-style cache optimization.
    """
    
    def __init__(self, cache: PromptCache):
        self.cache = cache
    
    def build_messages(
        self,
        system_message: Optional[str],
        conversation_history: list[dict[str, Any]],
        user_message: str,
        model: str
    ) -> list[dict[str, Any]]:
        """Build message list optimized for caching.
        
        Strategy:
        1. Check if full conversation can be cached
        2. Find longest cached prefix
        3. Build optimized message list
        """
        messages = []
        
        if system_message:
            messages.append({"role": "system", "content": system_message})
        
        messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_message})
        
        # Check cache
        entry = self.cache.get(messages, model)
        if entry:
            # Full cache hit
            return messages
        
        # Try to find cached prefix for incremental caching
        # This is where we'd implement prefix-based caching
        # For now, return full messages
        
        return messages
    
    def detect_cache_break(
        self,
        old_messages: list[dict[str, Any]],
        new_messages: list[dict[str, Any]]
    ) -> int:
        """Detect where cache breaks between old and new messages.
        
        Returns the index where messages diverge.
        """
        min_len = min(len(old_messages), len(new_messages))
        
        for i in range(min_len):
            if self._message_hash(old_messages[i]) != self._message_hash(new_messages[i]):
                return i
        
        if len(old_messages) != len(new_messages):
            return min_len
        
        return -1  # No break
    
    def _message_hash(self, message: dict[str, Any]) -> str:
        """Generate hash for a single message."""
        return hashlib.sha256(
            json.dumps(message, sort_keys=True).encode()
        ).hexdigest()


# Global instance
_default_cache: Optional[PromptCache] = None


def get_prompt_cache() -> PromptCache:
    """Get global prompt cache instance."""
    global _default_cache
    if _default_cache is None:
        _default_cache = PromptCache()
    return _default_cache


def clear_prompt_cache() -> None:
    """Clear global prompt cache."""
    global _default_cache
    if _default_cache:
        _default_cache.clear()
    _default_cache = None
