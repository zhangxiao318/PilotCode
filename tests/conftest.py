"""Pytest configuration and fixtures for pilotcode tests."""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import Generator

import pytest

# Ensure src is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pilotcode.permissions.permission_manager import (
    PermissionManager,
    PermissionLevel,
    ToolPermission,
    get_permission_manager,
)
from pilotcode.tools.base import ToolUseContext
from pilotcode.tools.registry import get_all_tools
from pilotcode.utils.model_client import get_model_client
from tests.mock_llm import MockModelClient


# ---------------------------------------------------------------------------
# Event loop policy for asyncio tests
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


# ---------------------------------------------------------------------------
# Basic fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_dir() -> Generator[str, None, None]:
    """Provide a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def tool_context(temp_dir: str) -> ToolUseContext:
    """Provide a default ToolUseContext pointing at a temp directory."""
    return ToolUseContext(options={"cwd": temp_dir})


@pytest.fixture
def allow_all_callback():
    """Permission callback that always allows."""
    async def _callback(*args, **kwargs):
        return {"behavior": "allow"}
    return _callback


# ---------------------------------------------------------------------------
# Permission fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def fresh_permission_manager(monkeypatch):
    """Provide a fresh permission manager and monkeypatch the global getter."""
    pm = PermissionManager()
    monkeypatch.setattr(
        "pilotcode.permissions.permission_manager._permission_manager", pm
    )
    # Also patch get_permission_manager to return this instance
    monkeypatch.setattr(
        "pilotcode.permissions.permission_manager.get_permission_manager",
        lambda: pm,
    )
    # Patch tool_executor to use this pm
    from pilotcode.permissions import tool_executor as te_mod
    original_get = te_mod.get_tool_executor

    def _patched_get(console=None):
        exe = te_mod.ToolExecutor(console)
        exe.permission_manager = pm
        return exe

    monkeypatch.setattr(te_mod, "get_tool_executor", _patched_get)
    return pm


@pytest.fixture
def auto_allow_permissions(fresh_permission_manager):
    """Set up permissions so all tools are auto-allowed."""
    pm = fresh_permission_manager
    tools = get_all_tools()
    for tool in tools:
        pm._permissions[tool.name] = ToolPermission(
            tool_name=tool.name,
            level=PermissionLevel.ALWAYS_ALLOW,
        )
    return pm


# ---------------------------------------------------------------------------
# Mock LLM fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_model_client(monkeypatch) -> MockModelClient:
    """Replace the global model client with a MockModelClient."""
    client = MockModelClient()
    monkeypatch.setattr(
        "pilotcode.utils.model_client._client", client
    )
    # Also patch get_model_client
    monkeypatch.setattr(
        "pilotcode.utils.model_client.get_model_client", lambda *a, **k: client
    )
    # Patch query_engine's import path as well
    monkeypatch.setattr(
        "pilotcode.query_engine.get_model_client", lambda *a, **k: client
    )
    return client


@pytest.fixture
def query_engine_factory(mock_model_client):
    """Factory fixture to create QueryEngines wired to the mock client."""
    from pilotcode.query_engine import QueryEngine, QueryEngineConfig

    def _make(tools=None, cwd=".", custom_system_prompt=None):
        config = QueryEngineConfig(
            cwd=cwd,
            tools=tools or [],
            custom_system_prompt=custom_system_prompt,
        )
        engine = QueryEngine(config)
        # Start fresh
        engine.messages.clear()
        return engine

    return _make


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def create_test_file(directory: str, filename: str, content: str) -> str:
    """Helper to create a test file."""
    path = Path(directory) / filename
    path.write_text(content, encoding="utf-8")
    return str(path)
