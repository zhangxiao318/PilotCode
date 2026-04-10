"""Shared fixtures for parity tests."""

import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from pilotcode.permissions.permission_manager import (
    PermissionLevel,
    ToolPermission,
    get_permission_manager,
)
from pilotcode.tools.base import ToolResult, ToolUseContext
from pilotcode.tools.registry import get_all_tools, get_tool_by_name


async def _always_allow(*args, **kwargs):
    return {"behavior": "allow"}


async def allow_all(tool_name: str, input_data: dict, context: ToolUseContext | None = None):
    """Helper to call a tool with auto-allow permissions."""
    tool = get_tool_by_name(tool_name)
    if tool is None:
        raise RuntimeError(f"Tool {tool_name} not found")
    ctx = context or ToolUseContext()
    parsed = tool.input_schema(**input_data)
    return await tool.call(parsed, ctx, _always_allow, None, lambda x: None)


@pytest.fixture
def auto_allow_all(monkeypatch):
    """Grant ALWAYS_ALLOW for all tools globally."""
    pm = get_permission_manager()
    for tool in get_all_tools():
        pm._permissions[tool.name] = ToolPermission(
            tool_name=tool.name,
            level=PermissionLevel.ALWAYS_ALLOW,
        )
    yield pm


@pytest.fixture(autouse=True)
def cleanup_tasks_after_test():
    """Automatically cleanup tasks after each test to prevent hanging."""
    yield
    # Cleanup after test
    try:
        from pilotcode.tools.task_tools import cleanup_all_tasks
        # Try to run cleanup if we're in an async context
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                # Schedule cleanup in the background
                asyncio.create_task(cleanup_all_tasks())
        except RuntimeError:
            # No running loop, can create new one
            asyncio.run(cleanup_all_tasks())
    except Exception:
        pass  # Ignore cleanup errors
