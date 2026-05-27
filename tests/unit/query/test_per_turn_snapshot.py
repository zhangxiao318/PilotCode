"""Tests for per-turn file snapshot tracker."""

from __future__ import annotations


from pilotcode.query.per_turn_snapshot import (
    FileSnapshot,
    PerTurnSnapshotTracker,
    TurnDiff,
)


class TestFileSnapshot:
    def test_basic_creation(self):
        snap = FileSnapshot(path="src/main.py", content_hash="abc123", mtime=1.0)
        assert snap.path == "src/main.py"
        assert snap.content_hash == "abc123"
        assert snap.mtime == 1.0


class TestTurnDiff:
    def test_empty_diff_has_no_changes(self):
        diff = TurnDiff()
        assert not diff.has_changes
        assert diff.to_summary() == ""

    def test_added_files_summary(self):
        diff = TurnDiff(added=["a.py", "b.py"])
        assert diff.has_changes
        summary = diff.to_summary()
        assert "created" in summary
        assert "a.py" in summary
        assert "b.py" in summary

    def test_modified_files_summary(self):
        diff = TurnDiff(modified=["x.py"])
        assert diff.has_changes
        summary = diff.to_summary()
        assert "modified" in summary
        assert "x.py" in summary

    def test_removed_files_summary(self):
        diff = TurnDiff(removed=["old.py"])
        assert diff.has_changes
        summary = diff.to_summary()
        assert "deleted" in summary
        assert "old.py" in summary

    def test_max_files_truncation(self):
        diff = TurnDiff(added=[f"f{i}.py" for i in range(15)])
        summary = diff.to_summary(max_files=5)
        assert "(+10 more)" in summary


class TestPerTurnSnapshotTracker:
    def test_init(self, tmp_path):
        tracker = PerTurnSnapshotTracker(str(tmp_path))
        assert tracker.workspace_root == tmp_path
        assert tracker.get_turn_history() == []

    def test_first_turn_no_diff(self, tmp_path):
        tracker = PerTurnSnapshotTracker(str(tmp_path))
        diff = tracker.end_turn()
        assert diff is None
        assert len(tracker.get_turn_history()) == 1

    def test_tracks_file_changes(self, tmp_path):
        tracker = PerTurnSnapshotTracker(str(tmp_path))

        # Turn 0: create a file
        f = tmp_path / "main.py"
        f.write_text("print(1)")
        tracker.track_file("main.py")
        tracker.end_turn()

        # Turn 1: modify the file
        f.write_text("print(2)")
        tracker.track_file("main.py")
        diff = tracker.end_turn()

        assert diff is not None
        assert diff.modified == ["main.py"]
        assert not diff.added
        assert not diff.removed

    def test_detects_new_file(self, tmp_path):
        tracker = PerTurnSnapshotTracker(str(tmp_path))
        tracker.end_turn()  # turn 0: empty

        f = tmp_path / "new.py"
        f.write_text("hello")
        tracker.track_file("new.py")
        diff = tracker.end_turn()

        assert diff is not None
        assert diff.added == ["new.py"]

    def test_detects_deleted_file(self, tmp_path):
        tracker = PerTurnSnapshotTracker(str(tmp_path))

        f = tmp_path / "gone.py"
        f.write_text("bye")
        tracker.track_file("gone.py")
        tracker.end_turn()

        f.unlink()
        # Note: we don't track the file this turn, so it appears as removed
        # because it was in the previous snapshot but not the current one.
        diff = tracker.end_turn()

        assert diff is not None
        assert diff.removed == ["gone.py"]

    def test_absolute_path_handling(self, tmp_path):
        tracker = PerTurnSnapshotTracker(str(tmp_path))
        f = tmp_path / "abs.py"
        f.write_text("content")
        tracker.track_file(str(f))
        diff = tracker.end_turn()
        assert diff is None  # first turn
        assert len(tracker.get_turn_history()) == 1
        assert "abs.py" in tracker.get_turn_history()[0].files

    def test_nonexistent_file_ignored(self, tmp_path):
        tracker = PerTurnSnapshotTracker(str(tmp_path))
        tracker.track_file("does_not_exist.py")
        diff = tracker.end_turn()
        assert diff is None
        assert tracker.get_turn_history()[0].files == {}

    def test_get_last_diff(self, tmp_path):
        tracker = PerTurnSnapshotTracker(str(tmp_path))
        assert tracker.get_last_diff() is None

        f = tmp_path / "a.py"
        f.write_text("v1")
        tracker.track_file("a.py")
        tracker.end_turn()

        f.write_text("v2")
        tracker.track_file("a.py")
        tracker.end_turn()

        last = tracker.get_last_diff()
        assert last is not None
        assert last.modified == ["a.py"]

    def test_reset_clears_history(self, tmp_path):
        tracker = PerTurnSnapshotTracker(str(tmp_path))
        f = tmp_path / "x.py"
        f.write_text("x")
        tracker.track_file("x.py")
        tracker.end_turn()

        tracker.reset()
        assert tracker.get_turn_history() == []
        assert tracker.get_last_diff() is None

    def test_multiple_file_changes(self, tmp_path):
        tracker = PerTurnSnapshotTracker(str(tmp_path))

        f1 = tmp_path / "a.py"
        f1.write_text("a")
        tracker.track_file("a.py")
        tracker.end_turn()

        f1.write_text("a2")
        f2 = tmp_path / "b.py"
        f2.write_text("b")
        tracker.track_file("a.py")
        tracker.track_file("b.py")
        diff = tracker.end_turn()

        assert diff is not None
        assert diff.modified == ["a.py"]
        assert diff.added == ["b.py"]
