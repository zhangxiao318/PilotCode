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
