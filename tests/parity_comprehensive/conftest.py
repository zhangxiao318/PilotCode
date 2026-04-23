"""Shared fixtures for parity tests."""

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from pilotcode.permissions.permission_manager import (
    PermissionLevel,
    ToolPermission,
    get_permission_manager,
)
from pilotcode.tools.base import ToolUseContext
from pilotcode.tools.registry import get_all_tools, get_tool_by_name


@pytest.fixture
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.parent.parent


@pytest.fixture
def tmp_path(project_root) -> Path:
    """Create a temporary directory within the project for file tests.

    Overrides pytest's default tmp_path to ensure files are created within
    the workspace for security compliance.
    """
    tmp_base = project_root / "tests" / "tmp"
    tmp_base.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="parity_test_", dir=str(tmp_base))
    path = Path(tmp)
    yield path
    shutil.rmtree(tmp, ignore_errors=True)


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
