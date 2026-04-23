"""Workspace snapshot and rollback service.

Provides save/restore functionality for the workspace:
- Create snapshots of the entire workspace
- Rollback to previous snapshots
- Diff between snapshots
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


@dataclass
class SnapshotInfo:
    """Information about a snapshot."""

    id: str
    name: str
    description: str
    created_at: float
    file_count: int
    total_size: int
    checksum: str
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SnapshotDiff:
    """Difference between two snapshots."""

    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)


class SnapshotManager:
    """Manages workspace snapshots."""

    SNAPSHOT_DIR = ".pilotcode/snapshots"
    MANIFEST_FILE = "manifest.json"

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root)
        self.snapshot_dir = self.workspace_root / self.SNAPSHOT_DIR
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

        # Ignore patterns (like gitignore)
        self.ignore_patterns = [
            ".git",
            "__pycache__",
            "*.pyc",
            ".pilotcode/snapshots",
            "node_modules",
            ".idea",
            ".vscode",
            "*.swp",
        ]

    def _generate_snapshot_id(self) -> str:
        """Generate unique snapshot ID."""
        timestamp = str(time.time())
        return hashlib.sha256(timestamp.encode()).hexdigest()[:16]

    def _should_ignore(self, path: str) -> bool:
        """Check if path should be ignored."""
        import fnmatch

        try:
            rel_path = os.path.relpath(path, self.workspace_root)
        except ValueError:
            # On Windows, relpath fails if path and workspace_root are on different drives
            rel_path = path

        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
            if fnmatch.fnmatch(os.path.basename(path), pattern):
                return True

        return False

    def _collect_files(self) -> list[Path]:
        """Collect all files to snapshot."""
        files = []

        for item in self.workspace_root.rglob("*"):
            if item.is_file() and not self._should_ignore(str(item)):
                files.append(item)

        return files

    def _calculate_checksum(self, file_paths: list[Path]) -> str:
        """Calculate checksum of all files."""
        hasher = hashlib.sha256()

        for path in sorted(file_paths):
            rel_path = str(path.relative_to(self.workspace_root))
            hasher.update(rel_path.encode())

            try:
                content = path.read_bytes()
                hasher.update(content)
            except (IOError, OSError):
                pass

        return hasher.hexdigest()

    def _get_total_size(self, file_paths: list[Path]) -> int:
        """Get total size of files."""
        total = 0
        for path in file_paths:
            try:
                total += path.stat().st_size
            except (IOError, OSError):
                pass
        return total

    def create_snapshot(
        self,
        name: str | None = None,
        description: str = "",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        progress_callback: Callable[[str, int, int], Any] | None = None,
    ) -> SnapshotInfo:
        """Create a new snapshot.

        Args:
            name: Snapshot name (auto-generated if None)
            description: Description of the snapshot
            tags: Tags for categorization
            metadata: Additional metadata
            progress_callback: Called with (status, current, total)

        Returns:
            SnapshotInfo for the created snapshot
        """
        snapshot_id = self._generate_snapshot_id()
        name = name or f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Collect files
        if progress_callback:
            progress_callback("Collecting files...", 0, 0)

        files = self._collect_files()

        # Create snapshot directory
        snapshot_path = self.snapshot_dir / snapshot_id
        snapshot_path.mkdir(exist_ok=True)

        # Copy files
        total_size = 0
        for i, src_path in enumerate(files, 1):
            rel_path = src_path.relative_to(self.workspace_root)
            dst_path = snapshot_path / rel_path
            dst_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                shutil.copy2(src_path, dst_path)
                total_size += src_path.stat().st_size
            except (IOError, OSError):
                pass

            if progress_callback:
                progress_callback(f"Copying {rel_path}...", i, len(files))

        # Calculate checksum
        if progress_callback:
            progress_callback("Calculating checksum...", len(files), len(files))

        checksum = self._calculate_checksum(files)

        # Create snapshot info
        info = SnapshotInfo(
            id=snapshot_id,
            name=name,
            description=description,
            created_at=time.time(),
            file_count=len(files),
            total_size=total_size,
            checksum=checksum,
            tags=tags or [],
            metadata=metadata or {},
        )

        # Save manifest
        manifest_path = snapshot_path / self.MANIFEST_FILE
        manifest_path.write_text(
            json.dumps(
                {
                    "id": info.id,
                    "name": info.name,
                    "description": info.description,
                    "created_at": info.created_at,
                    "file_count": info.file_count,
                    "total_size": info.total_size,
                    "checksum": info.checksum,
                    "tags": info.tags,
                    "metadata": info.metadata,
                },
                indent=2,
            )
        )

        return info

    def list_snapshots(self) -> list[SnapshotInfo]:
        """List all snapshots."""
        snapshots = []

        for snapshot_path in self.snapshot_dir.iterdir():
            if snapshot_path.is_dir():
                manifest_path = snapshot_path / self.MANIFEST_FILE
                if manifest_path.exists():
                    try:
                        data = json.loads(manifest_path.read_text())
                        snapshots.append(SnapshotInfo(**data))
                    except (json.JSONDecodeError, TypeError):
                        pass

        # Sort by creation time (newest first)
        snapshots.sort(key=lambda s: s.created_at, reverse=True)
        return snapshots

    def get_snapshot(self, snapshot_id: str) -> SnapshotInfo | None:
        """Get snapshot info by ID."""
        manifest_path = self.snapshot_dir / snapshot_id / self.MANIFEST_FILE

        if not manifest_path.exists():
            return None

        try:
            data = json.loads(manifest_path.read_text())
            return SnapshotInfo(**data)
        except (json.JSONDecodeError, TypeError):
            return None

    def restore_snapshot(
        self,
        snapshot_id: str,
        confirm: bool = True,
        progress_callback: Callable[[str, int, int], Any] | None = None,
    ) -> bool:
        """Restore workspace to a snapshot.

        Args:
            snapshot_id: ID of snapshot to restore
            confirm: If True, will raise error if workspace has uncommitted changes
            progress_callback: Called with (status, current, total)

        Returns:
            True if restore successful
        """
        snapshot_path = self.snapshot_dir / snapshot_id

        if not snapshot_path.exists():
            raise ValueError(f"Snapshot {snapshot_id} not found")

        # Check for uncommitted changes if confirm is True
        if confirm and self._has_uncommitted_changes():
            raise RuntimeError(
                "Workspace has uncommitted changes. Commit or stash changes before restoring."
            )

        # Get list of files in snapshot
        files_to_restore = list(snapshot_path.rglob("*"))
        files_to_restore = [
            f for f in files_to_restore if f.is_file() and f.name != self.MANIFEST_FILE
        ]

        # Clear current workspace (except .git and snapshot dir)
        if progress_callback:
            progress_callback("Clearing workspace...", 0, len(files_to_restore))

        self._clear_workspace()

        # Restore files
        for i, src_path in enumerate(files_to_restore, 1):
            rel_path = src_path.relative_to(snapshot_path)
            dst_path = self.workspace_root / rel_path
            dst_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                shutil.copy2(src_path, dst_path)
            except (IOError, OSError) as e:
                if progress_callback:
                    progress_callback(f"Error restoring {rel_path}: {e}", i, len(files_to_restore))
                continue

            if progress_callback:
                progress_callback(f"Restoring {rel_path}...", i, len(files_to_restore))

        return True

    def _has_uncommitted_changes(self) -> bool:
        """Check if git workspace has uncommitted changes."""
        git_dir = self.workspace_root / ".git"
        if not git_dir.exists():
            return False

        try:
            import subprocess

            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
            )
            return len(result.stdout.strip()) > 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def _clear_workspace(self) -> None:
        """Clear workspace files (preserving git and snapshots)."""
        for item in self.workspace_root.iterdir():
            if item.name == ".git":
                continue
            if item.name == ".pilotcode" and (item / "snapshots").exists():
                continue

            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except (IOError, OSError):
                pass

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot."""
        snapshot_path = self.snapshot_dir / snapshot_id

        if not snapshot_path.exists():
            return False

        try:
            shutil.rmtree(snapshot_path)
            return True
        except (IOError, OSError):
            return False

    def diff_snapshots(self, snapshot_id1: str, snapshot_id2: str) -> SnapshotDiff:
        """Compare two snapshots."""
        path1 = self.snapshot_dir / snapshot_id1
        path2 = self.snapshot_dir / snapshot_id2

        if not path1.exists() or not path2.exists():
            raise ValueError("One or both snapshots not found")

        files1 = self._get_snapshot_files(path1)
        files2 = self._get_snapshot_files(path2)

        diff = SnapshotDiff()

        # Find added and modified files
        for rel_path, checksum in files2.items():
            if rel_path not in files1:
                diff.added.append(rel_path)
            elif files1[rel_path] != checksum:
                diff.modified.append(rel_path)

        # Find removed files
        for rel_path in files1:
            if rel_path not in files2:
                diff.removed.append(rel_path)

        return diff

    def _get_snapshot_files(self, snapshot_path: Path) -> dict[str, str]:
        """Get dict of relative path -> checksum for all files in snapshot."""
        files = {}

        for file_path in snapshot_path.rglob("*"):
            if file_path.is_file() and file_path.name != self.MANIFEST_FILE:
                rel_path = str(file_path.relative_to(snapshot_path))
                try:
                    content = file_path.read_bytes()
                    files[rel_path] = hashlib.sha256(content).hexdigest()
                except (IOError, OSError):
                    pass

        return files

    def export_snapshot(self, snapshot_id: str, output_path: str) -> bool:
        """Export snapshot as tar.gz archive."""
        snapshot_path = self.snapshot_dir / snapshot_id

        if not snapshot_path.exists():
            return False

        try:
            with tarfile.open(output_path, "w:gz") as tar:
                tar.add(snapshot_path, arcname=snapshot_id)
            return True
        except (IOError, OSError):
            return False

    def import_snapshot(self, archive_path: str) -> SnapshotInfo | None:
        """Import snapshot from tar.gz archive."""
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                # Extract to temp dir first
                with tempfile.TemporaryDirectory() as tmpdir:
                    tar.extractall(tmpdir)

                    # Find snapshot directory
                    extracted = Path(tmpdir)
                    snapshot_dirs = [d for d in extracted.iterdir() if d.is_dir()]

                    if not snapshot_dirs:
                        return None

                    src_path = snapshot_dirs[0]
                    manifest_path = src_path / self.MANIFEST_FILE

                    if not manifest_path.exists():
                        return None

                    # Load manifest
                    data = json.loads(manifest_path.read_text())
                    snapshot_id = data["id"]

                    # Copy to snapshots directory
                    dst_path = self.snapshot_dir / snapshot_id
                    if dst_path.exists():
                        shutil.rmtree(dst_path)
                    shutil.copytree(src_path, dst_path)

                    return SnapshotInfo(**data)
        except (IOError, OSError, json.JSONDecodeError, tarfile.TarError):
            return None


# Global manager instance
_global_managers: dict[str, SnapshotManager] = {}


def get_snapshot_manager(workspace_root: str) -> SnapshotManager:
    """Get snapshot manager for workspace."""
    if workspace_root not in _global_managers:
        _global_managers[workspace_root] = SnapshotManager(workspace_root)
    return _global_managers[workspace_root]
