"""Tests for file watcher service."""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from pilotcode.services.file_watcher import (
    FileWatcher,
    FileChangeEvent,
    FileChangeType,
    WatcherConfig,
    get_file_watcher,
    watch_path,
)


class TestWatcherConfig:
    """Tests for WatcherConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = WatcherConfig()
        assert "*.pyc" in config.ignore_patterns
        assert ".git" in config.ignore_patterns
        assert config.poll_interval == 1.0
        assert config.recursive is True


class TestFileWatcher:
    """Tests for FileWatcher."""

    def test_init(self):
        """Test initialization."""
        watcher = FileWatcher()
        assert watcher.config is not None
        assert not watcher._running

    def test_should_ignore(self):
        """Test ignore patterns."""
        watcher = FileWatcher()

        assert watcher._should_ignore("test.pyc") is True
        assert watcher._should_ignore("__pycache__/test.py") is True
        assert watcher._should_ignore(".git/config") is True
        assert watcher._should_ignore("src/main.py") is False

    def test_should_ignore_watch_patterns(self):
        """Test watch patterns."""
        config = WatcherConfig(watch_patterns=["*.py"])
        watcher = FileWatcher(config)

        assert watcher._should_ignore("test.txt") is True
        assert watcher._should_ignore("test.py") is False

    def test_add_watch(self):
        """Test adding watch path."""
        watcher = FileWatcher()

        with tempfile.TemporaryDirectory() as tmpdir:
            assert watcher.add_watch(tmpdir) is True
            assert tmpdir in watcher._watch_paths

    def test_add_watch_nonexistent(self):
        """Test adding nonexistent path."""
        watcher = FileWatcher()
        assert watcher.add_watch("/nonexistent/path") is False

    def test_add_watch_ignored(self):
        """Test adding ignored path."""
        watcher = FileWatcher()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a __pycache__ directory
            pycache = Path(tmpdir) / "__pycache__"
            pycache.mkdir()

            assert watcher.add_watch(str(pycache)) is False

    def test_remove_watch(self):
        """Test removing watch path."""
        watcher = FileWatcher()

        with tempfile.TemporaryDirectory() as tmpdir:
            watcher.add_watch(tmpdir)
            watcher.remove_watch(tmpdir)
            assert tmpdir not in watcher._watch_paths

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Test starting and stopping watcher."""
        watcher = FileWatcher()

        with tempfile.TemporaryDirectory() as tmpdir:
            watcher.add_watch(tmpdir)

            await watcher.start()
            assert watcher._running is True

            await watcher.stop()
            assert watcher._running is False

    @pytest.mark.asyncio
    async def test_detects_new_file(self):
        """Test detecting new file creation."""
        events = []

        def callback(event):
            events.append(event)

        watcher = FileWatcher(config=WatcherConfig(poll_interval=0.1))

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create initial file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("initial")

            watcher.add_watch(tmpdir)
            watcher.add_callback(callback)

            await watcher.start()

            # Wait for initial scan
            await asyncio.sleep(0.2)

            # Create new file
            new_file = Path(tmpdir) / "new.txt"
            new_file.write_text("new content")

            # Wait for detection
            await asyncio.sleep(0.3)

            await watcher.stop()

            # Should have detected the new file
            assert len(events) > 0

    def test_get_watched_count(self):
        """Test getting watched file count."""
        watcher = FileWatcher()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some files
            (Path(tmpdir) / "file1.txt").write_text("1")
            (Path(tmpdir) / "file2.txt").write_text("2")

            watcher.add_watch(tmpdir)
            # Manually add files to watch_paths
            watcher._watch_paths[str(Path(tmpdir) / "file1.txt")] = 1.0
            watcher._watch_paths[str(Path(tmpdir) / "file2.txt")] = 2.0

            count = watcher.get_watched_count()
            assert count == 2


class TestGlobalFunctions:
    """Tests for global functions."""

    def test_get_file_watcher(self):
        """Test getting global watcher."""
        watcher1 = get_file_watcher()
        watcher2 = get_file_watcher()
        assert watcher1 is watcher2

    @pytest.mark.asyncio
    async def test_watch_path(self):
        """Test watch_path convenience function."""
        events = []

        async def callback(event):
            events.append(event)

        with tempfile.TemporaryDirectory() as tmpdir:
            watcher = await watch_path(tmpdir, callback)

            assert tmpdir in watcher._watch_paths
            assert callback in watcher._callbacks

            await watcher.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
