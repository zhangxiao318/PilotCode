"""Tests for snapshot service."""

import os
import tempfile
from pathlib import Path

import pytest

from pilotcode.services.snapshot import (
    SnapshotManager,
    SnapshotInfo,
    SnapshotDiff,
    get_snapshot_manager,
)


class TestSnapshotInfo:
    """Tests for SnapshotInfo dataclass."""
    
    def test_snapshot_info_creation(self):
        """Test creating snapshot info."""
        info = SnapshotInfo(
            id="abc123",
            name="test_snapshot",
            description="Test",
            created_at=1234567890.0,
            file_count=10,
            total_size=1024,
            checksum="abc"
        )
        
        assert info.id == "abc123"
        assert info.name == "test_snapshot"
        assert info.file_count == 10


class TestSnapshotDiff:
    """Tests for SnapshotDiff dataclass."""
    
    def test_diff_creation(self):
        """Test creating diff."""
        diff = SnapshotDiff(
            added=["file1.py"],
            removed=["file2.py"],
            modified=["file3.py"]
        )
        
        assert len(diff.added) == 1
        assert len(diff.removed) == 1
        assert len(diff.modified) == 1


class TestSnapshotManager:
    """Tests for SnapshotManager."""
    
    def test_init(self):
        """Test initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(tmpdir)
            
            assert manager.workspace_root == Path(tmpdir)
            assert (Path(tmpdir) / ".pilotcode/snapshots").exists()
    
    def test_should_ignore(self):
        """Test ignore patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(tmpdir)
            
            # Files that should be ignored
            assert manager._should_ignore("test.pyc") is True
            assert manager._should_ignore("__pycache__") is True
            assert manager._should_ignore(".git") is True
            # Files that should not be ignored
            assert manager._should_ignore("src/main.py") is False
            assert manager._should_ignore("test.py") is False
    
    def test_collect_files(self):
        """Test collecting files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(tmpdir)
            
            # Create test files
            (Path(tmpdir) / "file1.py").write_text("print(1)")
            (Path(tmpdir) / "file2.txt").write_text("text")
            (Path(tmpdir) / "__pycache__").mkdir()
            (Path(tmpdir) / "__pycache__" / "cached.pyc").write_text("")
            
            files = manager._collect_files()
            
            # Should collect .py and .txt, not .pyc
            assert len(files) == 2
            assert all(f.suffix != ".pyc" for f in files)
    
    def test_create_snapshot(self):
        """Test creating a snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(tmpdir)
            
            # Create test files
            (Path(tmpdir) / "main.py").write_text("def main(): pass")
            (Path(tmpdir) / "src").mkdir()
            (Path(tmpdir) / "src" / "utils.py").write_text("def util(): pass")
            
            info = manager.create_snapshot(name="test", description="Test snapshot")
            
            assert info.name == "test"
            assert info.description == "Test snapshot"
            assert info.file_count == 2
            assert info.total_size > 0
            assert info.checksum != ""
            
            # Verify snapshot directory exists
            snapshot_path = Path(tmpdir) / ".pilotcode/snapshots" / info.id
            assert snapshot_path.exists()
            
            # Verify manifest
            assert (snapshot_path / "manifest.json").exists()
    
    def test_list_snapshots(self):
        """Test listing snapshots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(tmpdir)
            
            # Create a snapshot
            (Path(tmpdir) / "file.py").write_text("test")
            manager.create_snapshot(name="test1")
            
            snapshots = manager.list_snapshots()
            
            assert len(snapshots) == 1
            assert snapshots[0].name == "test1"
    
    def test_get_snapshot(self):
        """Test getting snapshot info."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(tmpdir)
            
            (Path(tmpdir) / "file.py").write_text("test")
            created = manager.create_snapshot(name="test")
            
            info = manager.get_snapshot(created.id)
            
            assert info is not None
            assert info.id == created.id
            assert info.name == "test"
    
    def test_get_snapshot_not_found(self):
        """Test getting nonexistent snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(tmpdir)
            
            info = manager.get_snapshot("nonexistent")
            
            assert info is None
    
    def test_delete_snapshot(self):
        """Test deleting a snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(tmpdir)
            
            (Path(tmpdir) / "file.py").write_text("test")
            created = manager.create_snapshot(name="test")
            
            result = manager.delete_snapshot(created.id)
            
            assert result is True
            assert manager.get_snapshot(created.id) is None
    
    def test_delete_snapshot_not_found(self):
        """Test deleting nonexistent snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(tmpdir)
            
            result = manager.delete_snapshot("nonexistent")
            
            assert result is False
    
    def test_diff_snapshots(self):
        """Test diffing snapshots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(tmpdir)
            
            # Create first snapshot
            (Path(tmpdir) / "file1.py").write_text("content1")
            (Path(tmpdir) / "file2.py").write_text("content2")
            snap1 = manager.create_snapshot(name="snap1")
            
            # Modify workspace and create second snapshot
            (Path(tmpdir) / "file1.py").write_text("modified")
            (Path(tmpdir) / "file3.py").write_text("new")
            (Path(tmpdir) / "file2.py").unlink()
            snap2 = manager.create_snapshot(name="snap2")
            
            diff = manager.diff_snapshots(snap1.id, snap2.id)
            
            assert "file3.py" in diff.added
            assert "file2.py" in diff.removed
            assert "file1.py" in diff.modified


class TestGlobalFunctions:
    """Tests for global functions."""
    
    def test_get_snapshot_manager(self):
        """Test getting global manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager1 = get_snapshot_manager(tmpdir)
            manager2 = get_snapshot_manager(tmpdir)
            assert manager1 is manager2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
