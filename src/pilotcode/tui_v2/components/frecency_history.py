"""Frecency-based input history for intelligent suggestions.

Frecency = Frequency + Recency
Combines how often (frequency) and how recently an item was used
to provide better suggestions than simple chronological history.
"""

import json
import time
import math
from typing import List, Dict, Optional
from dataclasses import dataclass
from pathlib import Path


@dataclass
class HistoryEntry:
    """A single history entry with frecency tracking."""

    text: str
    timestamp: float
    frequency: int = 1
    last_accessed: float = 0.0

    def __post_init__(self):
        if self.last_accessed == 0.0:
            self.last_accessed = self.timestamp

    @property
    def frecency_score(self) -> float:
        """Calculate the frecency score.

        Formula: frequency * decay_factor
        where decay_factor = 1 / (1 + ln(hours_since_last_use + 1))

        This gives:
        - Higher scores for frequently used items
        - Higher scores for recently used items
        - Score decays logarithmically over time
        """
        hours_since = (time.time() - self.last_accessed) / 3600
        decay_factor = 1.0 / (1.0 + math.log1p(hours_since))
        return self.frequency * decay_factor


class FrecencyHistory:
    """Input history with frecency-based ranking.

    Features:
    - Deduplication (same text = same entry, updates frequency)
    - Frecency-based sorting
    - Prefix matching for suggestions
    - Persistence to disk
    - Configurable max entries
    """

    def __init__(
        self,
        storage_file: Optional[Path] = None,
        max_entries: int = 1000,
        max_suggestions: int = 10,
    ):
        self.storage_file = storage_file or Path.home() / ".pilotcode" / "input_history.json"
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        self.max_entries = max_entries
        self.max_suggestions = max_suggestions

        # History storage: text -> HistoryEntry
        self._entries: Dict[str, HistoryEntry] = {}

        self._load()

    def _load(self):
        """Load history from disk."""
        if not self.storage_file.exists():
            return

        try:
            with open(self.storage_file, "r") as f:
                data = json.load(f)

            for item in data:
                entry = HistoryEntry(
                    text=item["text"],
                    timestamp=item["timestamp"],
                    frequency=item.get("frequency", 1),
                    last_accessed=item.get("last_accessed", item["timestamp"]),
                )
                self._entries[entry.text] = entry
        except Exception as e:
            print(f"Failed to load history: {e}")

    def save(self):
        """Save history to disk."""
        try:
            # Sort by frecency score and limit entries
            sorted_entries = self.get_all_by_frecency()
            entries_to_save = sorted_entries[: self.max_entries]

            data = [
                {
                    "text": entry.text,
                    "timestamp": entry.timestamp,
                    "frequency": entry.frequency,
                    "last_accessed": entry.last_accessed,
                }
                for entry in entries_to_save
            ]

            with open(self.storage_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Failed to save history: {e}")

    def add(self, text: str):
        """Add or update an entry.

        If the text already exists, update its frequency and timestamp.
        Otherwise, create a new entry.
        """
        if not text or not text.strip():
            return

        text = text.strip()
        now = time.time()

        if text in self._entries:
            # Update existing entry
            entry = self._entries[text]
            entry.frequency += 1
            entry.last_accessed = now
        else:
            # Create new entry
            entry = HistoryEntry(text=text, timestamp=now)
            self._entries[text] = entry

        # Prune if too many entries
        if len(self._entries) > self.max_entries * 1.5:
            self._prune()

        # Auto-save periodically (every 10 additions)
        if len(self._entries) % 10 == 0:
            self.save()

    def _prune(self):
        """Remove low-frecency entries to stay under max_entries."""
        sorted_entries = self.get_all_by_frecency()
        to_keep = {e.text for e in sorted_entries[: self.max_entries]}
        self._entries = {k: v for k, v in self._entries.items() if k in to_keep}

    def get_suggestions(self, prefix: str = "") -> List[HistoryEntry]:
        """Get suggestions matching the prefix, sorted by frecency.

        Args:
            prefix: The prefix to match against

        Returns:
            List of HistoryEntry objects sorted by frecency score (highest first)
        """
        if not prefix:
            # Return top entries by frecency
            return self.get_all_by_frecency()[: self.max_suggestions]

        prefix_lower = prefix.lower()

        # Find matching entries
        matching = [
            entry for entry in self._entries.values() if entry.text.lower().startswith(prefix_lower)
        ]

        # Sort by frecency score
        matching.sort(key=lambda e: e.frecency_score, reverse=True)

        return matching[: self.max_suggestions]

    def get_all_by_frecency(self) -> List[HistoryEntry]:
        """Get all entries sorted by frecency score (highest first)."""
        entries = list(self._entries.values())
        entries.sort(key=lambda e: e.frecency_score, reverse=True)
        return entries

    def get_recent(self, n: int = 10) -> List[HistoryEntry]:
        """Get the n most recently used entries."""
        entries = list(self._entries.values())
        entries.sort(key=lambda e: e.last_accessed, reverse=True)
        return entries[:n]

    def get_most_frequent(self, n: int = 10) -> List[HistoryEntry]:
        """Get the n most frequently used entries."""
        entries = list(self._entries.values())
        entries.sort(key=lambda e: e.frequency, reverse=True)
        return entries[:n]

    def remove(self, text: str) -> bool:
        """Remove an entry by text."""
        if text in self._entries:
            del self._entries[text]
            return True
        return False

    def clear(self):
        """Clear all history."""
        self._entries.clear()
        if self.storage_file.exists():
            self.storage_file.unlink()

    def __len__(self) -> int:
        return len(self._entries)

    def get_stats(self) -> Dict[str, any]:
        """Get statistics about the history."""
        if not self._entries:
            return {
                "total_entries": 0,
                "avg_frequency": 0,
                "most_used": None,
            }

        frequencies = [e.frequency for e in self._entries.values()]
        most_used = max(self._entries.values(), key=lambda e: e.frequency)

        return {
            "total_entries": len(self._entries),
            "avg_frequency": sum(frequencies) / len(frequencies),
            "most_used": most_used.text[:50],
            "most_used_count": most_used.frequency,
        }


class FrecencyInputHistory:
    """Enhanced input history with multiple history categories.

    Maintains separate histories for:
    - All inputs (general)
    - Commands (starting with /)
    - File references (@filename)

    Each category has its own frecency tracking.
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or Path.home() / ".pilotcode"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.general = FrecencyHistory(self.storage_dir / "history_general.json")
        self.commands = FrecencyHistory(self.storage_dir / "history_commands.json")
        self.files = FrecencyHistory(self.storage_dir / "history_files.json")

    def add(self, text: str):
        """Add an entry to appropriate history."""
        # Add to general history
        self.general.add(text)

        # Categorize and add to specific history
        if text.strip().startswith("/"):
            self.commands.add(text)
        elif "@" in text:
            self.files.add(text)

    def get_suggestions(
        self, prefix: str = "", category: Optional[str] = None
    ) -> List[HistoryEntry]:
        """Get suggestions from a specific category or all."""
        if category == "commands":
            return self.commands.get_suggestions(prefix)
        elif category == "files":
            return self.files.get_suggestions(prefix)
        else:
            return self.general.get_suggestions(prefix)

    def get_command_suggestions(self, prefix: str = "") -> List[HistoryEntry]:
        """Get command suggestions."""
        # Only suggest if prefix starts with / or is empty
        if not prefix or prefix.startswith("/"):
            return self.commands.get_suggestions(prefix)
        return []

    def save(self):
        """Save all histories."""
        self.general.save()
        self.commands.save()
        self.files.save()

    def get_stats(self) -> Dict[str, Dict]:
        """Get statistics for all histories."""
        return {
            "general": self.general.get_stats(),
            "commands": self.commands.get_stats(),
            "files": self.files.get_stats(),
        }


# Example usage and testing
if __name__ == "__main__":
    # Create a test history
    history = FrecencyHistory(max_entries=100)

    # Add some entries
    history.add("Hello world")
    history.add("How are you")
    history.add("Hello world")  # Increases frequency
    history.add("Testing frecency")

    # Simulate time passing (in real usage, this would be natural)
    time.sleep(0.1)

    # Add more entries
    history.add("Newer entry")
    history.add("Hello world")  # Even higher frequency

    # Get suggestions
    print("Top suggestions:")
    for entry in history.get_suggestions():
        print(f"  {entry.text}: score={entry.frecency_score:.2f}, freq={entry.frequency}")

    # Get suggestions with prefix
    print("\nSuggestions for 'He':")
    for entry in history.get_suggestions("He"):
        print(f"  {entry.text}: score={entry.frecency_score:.2f}")

    print(f"\nStats: {history.get_stats()}")
