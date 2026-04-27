"""Tests for session persistence."""

import pytest
import tempfile
import shutil
from pathlib import Path
from pilotcode.services.session_persistence import (
    SessionPersistence,
    get_session_persistence,
)
from pilotcode.types.message import (
    UserMessage,
    AssistantMessage,
    SystemMessage,
    ToolUseMessage,
    ToolResultMessage,
)


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

    def test_save_and_load_all_message_types(self, persistence):
        """Smoke test: every message type round-trips without data loss.

        This guards against field-name mismatches between _message_to_dict
        and _dict_to_message (e.g. using message.name on ToolResultMessage
        which has no such attribute).
        """
        messages = [
            SystemMessage(content="You are a helpful assistant."),
            UserMessage(content="Read file /home/lyr/GDSystem/main.c"),
            AssistantMessage(
                content="I'll read the file for you.",
                reasoning_content="<thinking>User wants to read a file</thinking>",
            ),
            ToolUseMessage(
                tool_use_id="toolu_01AbCdEf",
                name="FileRead",
                input={"file_path": "/home/lyr/GDSystem/main.c"},
            ),
            ToolResultMessage(
                tool_use_id="toolu_01AbCdEf",
                content="int main() { return 0; }\n",
                is_error=False,
            ),
            AssistantMessage(content="Here is the content of the file."),
            UserMessage(content="Now edit it"),
            ToolUseMessage(
                tool_use_id="toolu_02XyZaBc",
                name="FileEdit",
                input={
                    "file_path": "/home/lyr/GDSystem/main.c",
                    "old_string": "return 0;",
                    "new_string": "return 42;",
                },
            ),
            ToolResultMessage(
                tool_use_id="toolu_02XyZaBc",
                content="[CLEARED] (was 15 chars)",
                is_error=False,
            ),
            ToolResultMessage(
                tool_use_id="toolu_03ErrOne",
                content="File not found",
                is_error=True,
            ),
        ]

        success = persistence.save_session(
            session_id="smoke_test_all_types",
            messages=messages,
            name="Smoke Test",
            project_path="/home/lyr/GDSystem",
        )
        assert success is True

        result = persistence.load_session("smoke_test_all_types")
        assert result is not None

        loaded_messages, metadata = result
        assert len(loaded_messages) == len(messages)
        assert metadata["project_path"] == "/home/lyr/GDSystem"

        # Verify each message type and critical fields
        assert isinstance(loaded_messages[0], SystemMessage)
        assert loaded_messages[0].content == "You are a helpful assistant."

        assert isinstance(loaded_messages[1], UserMessage)
        assert loaded_messages[1].content == "Read file /home/lyr/GDSystem/main.c"

        assert isinstance(loaded_messages[2], AssistantMessage)
        assert loaded_messages[2].content == "I'll read the file for you."
        assert (
            loaded_messages[2].reasoning_content == "<thinking>User wants to read a file</thinking>"
        )

        assert isinstance(loaded_messages[3], ToolUseMessage)
        assert loaded_messages[3].tool_use_id == "toolu_01AbCdEf"
        assert loaded_messages[3].name == "FileRead"
        assert loaded_messages[3].input["file_path"] == "/home/lyr/GDSystem/main.c"

        assert isinstance(loaded_messages[4], ToolResultMessage)
        assert loaded_messages[4].tool_use_id == "toolu_01AbCdEf"
        assert "int main()" in loaded_messages[4].content
        assert loaded_messages[4].is_error is False

        # Verify tool_use / tool_result pairing integrity
        tu_msg = loaded_messages[7]
        tr_msg = loaded_messages[8]
        assert tu_msg.tool_use_id == tr_msg.tool_use_id == "toolu_02XyZaBc"

        # Verify error flag survives round-trip
        err_msg = loaded_messages[9]
        assert err_msg.is_error is True
        assert err_msg.content == "File not found"

    def test_legacy_field_backward_compat(self, persistence):
        """Old session files used legacy field names; ensure they still load."""
        import gzip, json

        legacy_data = {
            "version": "1.0",
            "session_id": "legacy_test",
            "saved_at": "2026-04-01T00:00:00",
            "messages": [
                {
                    "type": "tool_use",
                    "tool_name": "Bash",
                    "tool_input": {"command": "ls"},
                    "id": "legacy_id_001",
                },
                {
                    "type": "tool_result",
                    "tool_name": "Bash",
                    "tool_result": "file.txt\n",
                    "tool_error": None,
                    "id": "legacy_id_001",
                },
            ],
        }
        session_path = persistence.DATA_DIR / "legacy_test.json.gz"
        with gzip.open(session_path, "wt", encoding="utf-8") as f:
            json.dump(legacy_data, f)

        # Write metadata so list_sessions doesn't crash
        meta_path = persistence.DATA_DIR / "legacy_test.meta.json"
        meta_path.write_text(
            '{"session_id": "legacy_test", "name": "Legacy", "message_count": 2, "created_at": "2026-04-01T00:00:00", "updated_at": "2026-04-01T00:00:00"}'
        )

        loaded = persistence.load_session("legacy_test")
        assert loaded is not None
        msgs, _ = loaded
        assert len(msgs) == 2

        # Legacy tool_use should load with empty tool_use_id fallback
        assert isinstance(msgs[0], ToolUseMessage)
        assert msgs[0].name == "Bash"
        assert msgs[0].input == {"command": "ls"}

        # Legacy tool_result should load content from tool_result field
        assert isinstance(msgs[1], ToolResultMessage)
        assert msgs[1].content == "file.txt\n"
        assert msgs[1].is_error is False


class TestGlobalInstance:
    """Test global instance functions."""

    def test_get_session_persistence(self):
        """Test getting global instance."""
        p1 = get_session_persistence()
        p2 = get_session_persistence()
        assert p1 is p2
