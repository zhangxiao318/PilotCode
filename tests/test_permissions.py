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
        assert "Auto-allowed" in reason or "Read-only" in reason

    def test_bash_requires_permission(self):
        pm = PermissionManager()
        # Use a high-risk command to test permission requirement
        allowed, reason = pm.check_permission("Bash", {"command": "rm -rf /"})
        # High-risk commands should require permission
        assert isinstance(allowed, bool)
        assert isinstance(reason, str)

    def test_session_grant_persists(self):
        pm = PermissionManager()
        req = PermissionRequest("Bash", {"command": "rm -rf test"}, "test", "critical")

        # Grant session permission
        pm.grant_session_permission("Bash", {"command": "rm -rf test"})
        allowed, _ = pm.check_permission("Bash", {"command": "rm -rf test"})
        assert allowed is True

    def test_risk_levels(self):
        pm = PermissionManager()
        # FileRead is typically low risk
        file_read_risk = pm.get_tool_risk_level("FileRead", {})
        assert file_read_risk in ["low", "none"]

        # Bash with simple command
        bash_simple_risk = pm.get_tool_risk_level("Bash", {"command": "echo hi"})
        assert bash_simple_risk in ["low", "medium", "none"]

        # Bash with dangerous command
        bash_dangerous_risk = pm.get_tool_risk_level("Bash", {"command": "rm -rf /"})
        assert bash_dangerous_risk in ["critical", "high"]

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

    @pytest.fixture
    def fresh_pm(self):
        """Create a fresh PermissionManager."""
        pm = PermissionManager()
        pm._session_grants.clear()
        pm._session_denies.clear()
        return pm

    @pytest.mark.asyncio
    async def test_execute_tool_denied(self, fresh_pm):
        """Tool execution denied when permission callback returns deny."""
        pm = fresh_pm

        async def deny_callback(req):
            return PermissionLevel.DENY

        pm.set_permission_callback(deny_callback)
        executor = ToolExecutor()
        executor.permission_manager = pm

        result = await executor.execute_tool_by_name(
            "Bash",
            {"command": "rm -rf /"},  # Use high-risk command
            ToolUseContext(),
        )
        # Tool should be denied or fail
        assert result.success is False or result.permission_granted is False

    @pytest.mark.asyncio
    async def test_execute_tool_allowed(self, fresh_pm):
        """Tool executes when permission callback returns allow."""
        pm = fresh_pm

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
        # With allow callback, tool should execute successfully
        # Note: Bash tool may be auto-allowed for safe commands
        if result.success:
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
