"""Tests for the permission system and tool executor."""

import pytest

from pilotcode.permissions.permission_manager import (
    PermissionManager,
    PermissionLevel,
    PermissionRequest,
)
from pilotcode.permissions.tool_executor import ToolExecutor
from pilotcode.tools.base import ToolUseContext


class TestPermissionManager:
    """Tests for PermissionManager logic."""

    def test_read_only_tools_auto_allowed(self):
        pm = PermissionManager()
        allowed, reason = pm.check_permission("FileRead", {"file_path": "test.txt"})
        assert allowed is True
        assert "Read-only" in reason

    def test_bash_requires_permission(self):
        pm = PermissionManager()
        allowed, reason = pm.check_permission("Bash", {"command": "echo hi"})
        assert allowed is False
        assert "required" in reason.lower() or "Permission" in reason

    def test_session_grant_persists(self):
        pm = PermissionManager()
        req = PermissionRequest("Bash", {"command": "echo hi"}, "test", "medium")

        # Grant session permission
        pm.grant_session_permission("Bash", {"command": "echo hi"})
        allowed, _ = pm.check_permission("Bash", {"command": "echo hi"})
        assert allowed is True

    def test_risk_levels(self):
        pm = PermissionManager()
        assert pm.get_tool_risk_level("FileRead", {}) == "low"
        assert pm.get_tool_risk_level("Bash", {"command": "echo hi"}) == "medium"
        assert pm.get_tool_risk_level("Bash", {"command": "rm -rf /"}) == "critical"

    @pytest.mark.asyncio
    async def test_request_permission_callback(self):
        pm = PermissionManager()

        async def callback(req):
            return PermissionLevel.ALLOW

        pm.set_permission_callback(callback)
        granted, level = await pm.request_permission("Bash", {"command": "ls"})
        assert granted is True
        assert level == PermissionLevel.ALLOW


class TestToolExecutor:
    """Tests for ToolExecutor with real permission flows."""

    @pytest.mark.asyncio
    async def test_execute_tool_denied(self, fresh_permission_manager):
        """Tool execution denied when permission callback returns deny."""
        pm = fresh_permission_manager

        async def deny_callback(req):
            return PermissionLevel.DENY

        pm.set_permission_callback(deny_callback)
        executor = ToolExecutor()
        executor.permission_manager = pm

        result = await executor.execute_tool_by_name(
            "Bash",
            {"command": "echo hello"},
            ToolUseContext(),
        )
        assert result.success is False
        assert result.permission_granted is False
        assert "denied" in result.message.lower()

    @pytest.mark.asyncio
    async def test_execute_tool_allowed(self, fresh_permission_manager):
        """Tool executes when permission callback returns allow."""
        pm = fresh_permission_manager

        async def allow_callback(req):
            return PermissionLevel.ALLOW

        pm.set_permission_callback(allow_callback)
        executor = ToolExecutor()
        executor.permission_manager = pm

        result = await executor.execute_tool_by_name(
            "Bash",
            {"command": "echo hello"},
            ToolUseContext(),
        )
        assert result.success is True
        assert result.permission_granted is True
        assert "hello" in str(result.result.data)

    @pytest.mark.asyncio
    async def test_execute_read_only_tool_no_prompt(self):
        """Read-only tools should not trigger permission prompts."""
        executor = ToolExecutor()
        result = await executor.execute_tool_by_name(
            "FileRead",
            {"file_path": "."},
            ToolUseContext(),
        )
        # FileRead of "." will error because it's a directory, but permission should be granted
        assert result.permission_granted is True
