"""Tests for session persistence and resume."""

import json
import os
import tempfile

import pytest

from pilotcode.query_engine import QueryEngine, QueryEngineConfig
from pilotcode.types.message import UserMessage, AssistantMessage


class TestSessionPersistence:
    def test_save_and_load_session(self):
        engine = QueryEngine(QueryEngineConfig(cwd="/tmp"))
        engine.messages.append(UserMessage(content="Hello"))
        engine.messages.append(AssistantMessage(content="Hi there"))

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "session.json")
            engine.save_session(path)
            assert os.path.exists(path)

            # Verify file contents
            with open(path) as f:
                data = json.load(f)
            assert data["cwd"] == "/tmp"
            assert len(data["messages"]) == 2

            # Load into new engine
            engine2 = QueryEngine(QueryEngineConfig(cwd="."))
            assert engine2.load_session(path) is True
            assert len(engine2.messages) == 2
            assert engine2.messages[0].content == "Hello"
            assert engine2.messages[1].content == "Hi there"
            assert engine2.config.cwd == "/tmp"

    def test_load_missing_session_returns_false(self):
        engine = QueryEngine(QueryEngineConfig(cwd="."))
        assert engine.load_session("/nonexistent/path/session.json") is False

    @pytest.mark.asyncio
    async def test_resume_command_exists(self):
        from pilotcode.commands.base import process_user_input, CommandContext

        is_cmd, result = await process_user_input("/resume", CommandContext(cwd="."))
        assert is_cmd is True
        assert "No saved session" in result or "messages loaded" in result
