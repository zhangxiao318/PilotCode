"""File system watcher service.

Monitors file system changes and notifies subscribers.
Used for:
- Auto-invalidating caches when files change
- Detecting external modifications
- Triggering incremental indexing
"""

from __future__ import annotations

import asyncio
import fnmatch
import os
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Coroutine, Any


class FileChangeType(Enum):
    """Type of file change."""

    CREATED = auto()
    MODIFIED = auto()
    DELETED = auto()
    MOVED = auto()


@dataclass
class FileChangeEvent:
    """File change event."""

    path: str
    change_type: FileChangeType
    timestamp: float
    is_directory: bool = False
    old_path: str | None = None  # For move events


@dataclass
class WatcherConfig:
    """Configuration for file watcher."""

    # Patterns to ignore (gitignore-style)
    ignore_patterns: list[str] = field(
        default_factory=lambda: [
            "*.pyc",
            "__pycache__",
            ".git",
            ".svn",
            ".hg",
            "node_modules",
            ".idea",
            ".vscode",
            "*.swp",
            "*.swo",
            ".DS_Store",
            "Thumbs.db",
        ]
    )
    # Only watch these patterns (empty = watch all)
    watch_patterns: list[str] = field(default_factory=list)
    # Check interval in seconds
    poll_interval: float = 1.0
    # Whether to watch recursively
    recursive: bool = True
    # Whether to follow symlinks
    follow_symlinks: bool = False


class FileWatcher:
    """Watch files for changes.

    Uses polling-based watching for cross-platform compatibility.
    For production use, could be enhanced with platform-specific APIs:
    - Linux: inotify
    - macOS: FSEvents
    - Windows: ReadDirectoryChangesW
    """

    def __init__(self, config: WatcherConfig | None = None):
        self.config = config or WatcherConfig()
        self._watch_paths: dict[str, float] = {}  # path -> last_mtime
        self._callbacks: list[Callable[[FileChangeEvent], Coroutine[Any, Any, None] | None]] = []
        self._running = False
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._event_queue: asyncio.Queue[FileChangeEvent] = asyncio.Queue()

    def _should_ignore(self, path: str) -> bool:
        """Check if path should be ignored."""
        name = os.path.basename(path)

        # Check ignore patterns
        for pattern in self.config.ignore_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
            # Also check if any parent directory matches
            for part in Path(path).parts:
                if fnmatch.fnmatch(part, pattern):
                    return True

        # If watch patterns specified, only watch those
        if self.config.watch_patterns:
            for pattern in self.config.watch_patterns:
                if fnmatch.fnmatch(name, pattern):
                    return False
            return True  # Not in watch patterns

        return False

    def _scan_directory(self, path: str) -> dict[str, float]:
        """Scan directory and return file mtimes."""
        files = {}

        try:
            if self.config.recursive:
                for root, dirs, filenames in os.walk(path):
                    # Filter ignored directories
                    dirs[:] = [d for d in dirs if not self._should_ignore(os.path.join(root, d))]

                    for filename in filenames:
                        filepath = os.path.join(root, filename)
                        if not self._should_ignore(filepath):
                            try:
                                stat = os.stat(filepath)
                                files[filepath] = stat.st_mtime
                            except (OSError, IOError):
                                pass
            else:
                for entry in os.scandir(path):
                    if entry.is_file() and not self._should_ignore(entry.path):
                        try:
                            files[entry.path] = entry.stat().st_mtime
                        except (OSError, IOError):
                            pass
        except (OSError, IOError):
            pass

        return files

    def _get_file_mtime(self, path: str) -> float | None:
        """Get file modification time."""
        try:
            return os.path.getmtime(path)
        except (OSError, IOError):
            return None

    async def _check_changes(self, watch_path: str) -> list[FileChangeEvent]:
        """Check for changes in watched path."""
        events = []
        current_files = {}

        if os.path.isdir(watch_path):
            current_files = self._scan_directory(watch_path)
        elif os.path.isfile(watch_path):
            mtime = self._get_file_mtime(watch_path)
            if mtime is not None:
                current_files[watch_path] = mtime

        # Find modified and deleted files
        for path, old_mtime in self._watch_paths.items():
            if path not in current_files:
                # File deleted
                events.append(
                    FileChangeEvent(
                        path=path,
                        change_type=FileChangeType.DELETED,
                        timestamp=time.time(),
                        is_directory=os.path.isdir(path) if os.path.exists(path) else False,
                    )
                )
            elif current_files[path] != old_mtime:
                # File modified
                events.append(
                    FileChangeEvent(
                        path=path,
                        change_type=FileChangeType.MODIFIED,
                        timestamp=time.time(),
                        is_directory=os.path.isdir(path),
                    )
                )

        # Find new files
        for path in current_files:
            if path not in self._watch_paths:
                events.append(
                    FileChangeEvent(
                        path=path,
                        change_type=FileChangeType.CREATED,
                        timestamp=time.time(),
                        is_directory=os.path.isdir(path),
                    )
                )

        # Update state
        self._watch_paths = current_files

        return events

    async def _watch_loop(self) -> None:
        """Main watch loop."""
        while self._running:
            try:
                all_events = []

                # Check all watched paths
                for watch_path in list(self._watch_paths.keys()):
                    events = await self._check_changes(watch_path)
                    all_events.extend(events)

                # Queue events
                for event in all_events:
                    await self._event_queue.put(event)

                await asyncio.sleep(self.config.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(self.config.poll_interval)

    async def _process_events(self) -> None:
        """Process events from queue."""
        while self._running:
            try:
                event = await self._event_queue.get()

                # Notify callbacks
                for callback in self._callbacks:
                    try:
                        result = callback(event)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        pass

                self._event_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    def add_watch(self, path: str) -> bool:
        """Add a path to watch.

        Args:
            path: File or directory path to watch

        Returns:
            True if path added successfully
        """
        if not os.path.exists(path):
            return False

        if self._should_ignore(path):
            return False

        # Initialize file list
        if os.path.isdir(path):
            self._watch_paths[path] = 0  # Directory marker
        else:
            mtime = self._get_file_mtime(path)
            if mtime is not None:
                self._watch_paths[path] = mtime

        return True

    def remove_watch(self, path: str) -> None:
        """Remove a watched path."""
        if path in self._watch_paths:
            del self._watch_paths[path]

    def add_callback(
        self, callback: Callable[[FileChangeEvent], Coroutine[Any, Any, None] | None]
    ) -> None:
        """Add a callback for file change events."""
        self._callbacks.append(callback)

    def remove_callback(
        self, callback: Callable[[FileChangeEvent], Coroutine[Any, Any, None] | None]
    ) -> None:
        """Remove a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def start(self) -> None:
        """Start watching."""
        if self._running:
            return

        self._running = True

        # Initialize state for all watch paths
        for path in list(self._watch_paths.keys()):
            if os.path.isdir(path):
                files = self._scan_directory(path)
                self._watch_paths.update(files)

        # Start tasks
        self._task = asyncio.create_task(self._watch_loop())
        asyncio.create_task(self._process_events())

    async def stop(self) -> None:
        """Stop watching."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def get_watched_count(self) -> int:
        """Get number of watched files."""
        return len([p for p in self._watch_paths.keys() if os.path.isfile(p)])


# Global watcher instance
_global_watcher: FileWatcher | None = None


def get_file_watcher(config: WatcherConfig | None = None) -> FileWatcher:
    """Get global file watcher."""
    global _global_watcher
    if _global_watcher is None:
        _global_watcher = FileWatcher(config)
    return _global_watcher


async def watch_path(
    path: str,
    callback: Callable[[FileChangeEvent], Coroutine[Any, Any, None] | None],
    config: WatcherConfig | None = None,
) -> FileWatcher:
    """Convenience function to watch a path.

    Args:
        path: Path to watch
        callback: Callback for change events
        config: Optional watcher configuration

    Returns:
        Configured and started FileWatcher
    """
    watcher = FileWatcher(config)
    watcher.add_watch(path)
    watcher.add_callback(callback)
    await watcher.start()
    return watcher
