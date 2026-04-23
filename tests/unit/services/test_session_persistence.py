"""Tests for session persistence."""

import pytest
import tempfile
import shutil
from pathlib import Path
from pilotcode.services.session_persistence import (
    SessionPersistence,
    get_session_persistence,
)
from pilotcode.types.message import UserMessage, AssistantMessage


class TestSessionPersistence:
    """Test session persistence functionality."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)

    @pytest.fixture
    def persistence(self, temp_dir, monkeypatch):
        """Create persistence instance with temp directory."""
        p = SessionPersistence()
        # Override data dir
        p.DATA_DIR = Path(temp_dir)
        return p

    def test_save_and_load_session(self, persistence):
        """Test saving and loading a session."""
        messages = [UserMessage(content="Hello"), AssistantMessage(content="Hi there!")]

        # Save session
        success = persistence.save_session(
            session_id="test123",
            messages=messages,
            name="Test Session",
            project_path="/tmp/project",
        )
        assert success is True

        # Load session
        result = persistence.load_session("test123")
        assert result is not None

        loaded_messages, metadata = result
        assert len(loaded_messages) == 2
        assert metadata["name"] == "Test Session"
        assert metadata["project_path"] == "/tmp/project"

    def test_load_nonexistent_session(self, persistence):
        """Test loading a session that doesn't exist."""
        result = persistence.load_session("nonexistent")
        assert result is None

    def test_list_sessions(self, persistence):
        """Test listing sessions."""
        # Create multiple sessions
        for i in range(3):
            persistence.save_session(
                session_id=f"session{i}",
                messages=[UserMessage(content=f"Message {i}")],
                name=f"Session {i}",
            )

        sessions = persistence.list_sessions()
        assert len(sessions) == 3

    def test_list_sessions_filtered_by_project(self, persistence):
        """Test listing sessions filtered by project."""
        persistence.save_session(
            session_id="proj1", messages=[UserMessage(content="Hello")], project_path="/project1"
        )
        persistence.save_session(
            session_id="proj2", messages=[UserMessage(content="Hello")], project_path="/project2"
        )

        sessions = persistence.list_sessions(project_path="/project1")
        assert len(sessions) == 1
        assert sessions[0].session_id == "proj1"

    def test_delete_session(self, persistence):
        """Test deleting a session."""
        persistence.save_session(session_id="to_delete", messages=[UserMessage(content="Hello")])

        success = persistence.delete_session("to_delete")
        assert success is True

        # Verify it's gone
        result = persistence.load_session("to_delete")
        assert result is None

    def test_rename_session(self, persistence):
        """Test renaming a session."""
        persistence.save_session(
            session_id="to_rename", messages=[UserMessage(content="Hello")], name="Old Name"
        )

        success = persistence.rename_session("to_rename", "New Name")
        assert success is True

        # Verify rename
        sessions = persistence.list_sessions()
        assert sessions[0].name == "New Name"

    def test_export_session_json(self, persistence, temp_dir):
        """Test exporting session to JSON."""
        persistence.save_session(
            session_id="export_test", messages=[UserMessage(content="Hello")], name="Export Test"
        )

        export_path = Path(temp_dir) / "export.json"
        success = persistence.export_session("export_test", export_path, "json")

        assert success is True
        assert export_path.exists()

        # Verify content
        import json

        with open(export_path) as f:
            data = json.load(f)
        assert "metadata" in data
        assert "messages" in data

    def test_export_session_markdown(self, persistence, temp_dir):
        """Test exporting session to Markdown."""
        persistence.save_session(
            session_id="export_md",
            messages=[UserMessage(content="Hello"), AssistantMessage(content="Hi!")],
            name="Export MD Test",
        )

        export_path = Path(temp_dir) / "export.md"
        success = persistence.export_session("export_md", export_path, "markdown")

        assert success is True
        assert export_path.exists()

        content = export_path.read_text()
        assert "# Export MD Test" in content
        assert "## User" in content
        assert "## Assistant" in content

    def test_generate_summary(self, persistence):
        """Test summary generation."""
        messages = [
            AssistantMessage(content="First"),
            UserMessage(content="This is a test message for summary generation"),
        ]

        summary = persistence._generate_summary(messages)
        assert "test message" in summary

    def test_generate_summary_empty(self, persistence):
        """Test summary generation for empty session."""
        summary = persistence._generate_summary([])
        assert summary == "Empty session"


class TestGlobalInstance:
    """Test global instance functions."""

    def test_get_session_persistence(self):
        """Test getting global instance."""
        p1 = get_session_persistence()
        p2 = get_session_persistence()
        assert p1 is p2
