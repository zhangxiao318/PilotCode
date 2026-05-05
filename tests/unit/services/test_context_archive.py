"""Tests for context archive and session memory."""

import tempfile
from pathlib import Path
from pilotcode.services.context_archive import ContextArchive, SessionMemory, ContextEntry


class TestSessionMemory:
    def test_empty(self):
        mem = SessionMemory()
        prompt = mem.to_prompt_section()
        assert "Session Context" in prompt

    def test_with_data(self):
        mem = SessionMemory(
            primary_request="Fix the login bug",
            key_technical_concepts=["OAuth2", "JWT"],
            files_examined=["src/auth.py", "src/login.py"],
            errors_encountered=["TypeError in validate()"],
        )
        prompt = mem.to_prompt_section()
        assert "Fix the login bug" in prompt
        assert "OAuth2" in prompt
        assert "src/auth.py" in prompt
        assert "TypeError" in prompt

    def test_roundtrip(self):
        mem = SessionMemory(primary_request="Test", decisions_made=["use Redis"])
        data = mem.to_dict()
        restored = SessionMemory.from_dict(data)
        assert restored.primary_request == "Test"
        assert "use Redis" in restored.decisions_made


class TestContextArchive:
    def test_archive_and_retrieve(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = ContextArchive(base_dir=tmp)
            aid = archive.archive_compaction(
                messages=[],
                summary={"primary_request": "test run"},
                token_saved=1000,
            )
            assert aid is not None
            # Retrieve
            result = archive.get_archive(aid)
            assert result is not None
            assert result["archive_id"] == aid
            assert result["token_saved"] == 1000

    def test_list_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = ContextArchive(base_dir=tmp)
            archive.archive_compaction(
                messages=[],
                summary={"primary_request": "first"},
                token_saved=500,
            )
            archive.archive_compaction(
                messages=[],
                summary={"primary_request": "second"},
                token_saved=300,
            )
            archives = archive.list_archives()
            assert len(archives) == 2
            assert archives[0]["token_saved"] == 300  # most recent first

    def test_query_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = ContextArchive(base_dir=tmp)

            class FakeMsg:
                content = "The login function uses OAuth2"

            archive.archive_compaction(
                messages=[FakeMsg()],
                summary={"primary_request": "auth fix"},
                token_saved=100,
            )

            results = archive.query_context("OAuth2")
            assert len(results) >= 1

            results = archive.query_context("nonexistent")
            assert len(results) == 0

    def test_session_memory_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = ContextArchive(base_dir=tmp)
            archive.session_memory.primary_request = "Fix bug"
            archive.session_memory.files_examined = ["main.py"]
            archive.save_session_memory()

            # New archive instance loads from disk
            archive2 = ContextArchive(base_dir=tmp)
            assert archive2.session_memory.primary_request == "Fix bug"
            assert "main.py" in archive2.session_memory.files_examined

    def test_get_session_memory_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = ContextArchive(base_dir=tmp)
            archive.session_memory.primary_request = "Implement feature X"
            prompt = archive.get_session_memory_prompt()
            assert "Implement feature X" in prompt

    def test_cleanup_old_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = ContextArchive(base_dir=tmp)
            archive.archive_compaction(
                messages=[],
                summary={"primary_request": "old"},
                token_saved=0,
            )
            # max_age_days=365 should keep everything
            cleaned = archive.cleanup_old_archives(max_age_days=365)
            assert cleaned == 0

    def test_total_tokens_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = ContextArchive(base_dir=tmp)
            archive.archive_compaction(
                messages=[],
                summary={},
                token_saved=500,
            )
            archive.archive_compaction(
                messages=[],
                summary={},
                token_saved=300,
            )
            assert archive.get_total_tokens_saved() == 800
