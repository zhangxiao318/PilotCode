"""Tests for permission system."""

import pytest

from pilotcode.permissions.permission_manager import (
    PermissionManager,
    PermissionRequest,
    PermissionLevel,
    get_permission_manager,
)
from pilotcode.permissions.tool_executor import ToolExecutor, get_tool_executor


class TestPermissionRequest:
    """Tests for PermissionRequest."""
    
    def test_request_creation(self):
        """Test creating a permission request."""
        request = PermissionRequest(
            tool_name="Bash",
            tool_input={"command": "ls"},
            description="List files",
            risk_level="low"
        )
        
        assert request.tool_name == "Bash"
        assert request.fingerprint is not None
    
    def test_fingerprint_consistency(self):
        """Test that fingerprint is consistent for same input."""
        request1 = PermissionRequest(
            tool_name="Bash",
            tool_input={"command": "ls"},
            description="List files",
            risk_level="low"
        )
        
        request2 = PermissionRequest(
            tool_name="Bash",
            tool_input={"command": "ls"},
            description="Different description",  # Different desc
            risk_level="medium"  # Different risk
        )
        
        # Fingerprint should be based on tool_name and tool_input only
        assert request1.fingerprint == request2.fingerprint
    
    def test_fingerprint_uniqueness(self):
        """Test that different inputs produce different fingerprints."""
        request1 = PermissionRequest(
            tool_name="Bash",
            tool_input={"command": "ls"},
            description="List",
            risk_level="low"
        )
        
        request2 = PermissionRequest(
            tool_name="Bash",
            tool_input={"command": "rm"},  # Different command
            description="Remove",
            risk_level="high"
        )
        
        assert request1.fingerprint != request2.fingerprint


class TestPermissionManager:
    """Tests for PermissionManager."""
    
    @pytest.fixture
    def pm(self):
        """Create a fresh PermissionManager."""
        manager = PermissionManager()
        # Clear any existing permissions
        manager._permissions.clear()
        manager._session_grants.clear()
        manager._session_denies.clear()
        return manager
    
    def test_check_permission_no_permission_set(self, pm):
        """Test checking permission when none is set."""
        is_permitted, reason = pm.check_permission("Bash", {"command": "ls"})
        
        assert is_permitted is False
        assert "required" in reason.lower() or "need" in reason.lower()
    
    def test_grant_session_permission(self, pm):
        """Test granting session permission."""
        pm.grant_session_permission("Bash", {"command": "ls"})
        
        is_permitted, reason = pm.check_permission("Bash", {"command": "ls"})
        assert is_permitted is True
        assert "session" in reason.lower()
    
    def test_revoke_session_permission(self, pm):
        """Test revoking session permission."""
        # Grant then revoke
        pm.grant_session_permission("Bash", {"command": "ls"})
        pm.revoke_session_permission("Bash", {"command": "ls"})
        
        is_permitted, _ = pm.check_permission("Bash", {"command": "ls"})
        assert is_permitted is False
    
    def test_set_always_allow(self, pm):
        """Test setting always allow permission."""
        pm.set_permission("Bash", PermissionLevel.ALWAYS_ALLOW)
        
        is_permitted, reason = pm.check_permission("Bash", {"command": "anything"})
        assert is_permitted is True
        assert "always" in reason.lower()
    
    def test_set_never_allow(self, pm):
        """Test setting never allow permission."""
        pm.set_permission("Bash", PermissionLevel.NEVER_ALLOW)
        
        is_permitted, reason = pm.check_permission("Bash", {"command": "ls"})
        assert is_permitted is False
        assert "never" in reason.lower()
    
    def test_reset_session_permissions(self, pm):
        """Test resetting all session permissions."""
        # Grant some permissions
        pm.grant_session_permission("Bash", {"command": "ls"})
        pm.grant_session_permission("FileRead", {"file_path": "/tmp/test"})
        
        # Reset
        pm.reset_session_permissions()
        
        # All should be denied now
        is_permitted1, _ = pm.check_permission("Bash", {"command": "ls"})
        is_permitted2, _ = pm.check_permission("FileRead", {"file_path": "/tmp/test"})
        
        assert is_permitted1 is False
        assert is_permitted2 is False
    
    @pytest.mark.asyncio
    async def test_request_permission_callback(self, pm):
        """Test requesting permission with callback."""
        async def mock_callback(request):
            return PermissionLevel.ALLOW
        
        pm.set_permission_callback(mock_callback)
        
        is_granted, level = await pm.request_permission("Bash", {"command": "ls"})
        
        assert is_granted is True
        assert level == PermissionLevel.ALLOW
    
    @pytest.mark.asyncio
    async def test_request_permission_denied(self, pm):
        """Test requesting permission and being denied."""
        async def mock_callback(request):
            return PermissionLevel.DENY
        
        pm.set_permission_callback(mock_callback)
        
        is_granted, level = await pm.request_permission("Bash", {"command": "ls"})
        
        assert is_granted is False
        assert level == PermissionLevel.DENY


class TestToolExecutor:
    """Tests for ToolExecutor."""
    
    @pytest.fixture
    def executor(self):
        """Create a ToolExecutor."""
        return get_tool_executor()
    
    def test_get_tool_executor_singleton(self):
        """Test that get_tool_executor returns singleton."""
        e1 = get_tool_executor()
        e2 = get_tool_executor()
        assert e1 is e2
    
    @pytest.mark.asyncio
    async def test_execute_tool_by_name_not_found(self, executor, tool_context):
        """Test executing non-existent tool."""
        result = await executor.execute_tool_by_name(
            "NonExistentTool",
            {},
            tool_context
        )
        
        assert not result.success
        assert "not found" in result.message.lower()
    
    @pytest.mark.asyncio
    async def test_execute_tool_with_permission_denied(self, executor, tool_context, monkeypatch):
        """Test executing tool when permission is denied."""
        # Mock permission check to deny
        from pilotcode.permissions import get_permission_manager
        pm = get_permission_manager()
        pm.set_permission("Bash", PermissionLevel.NEVER_ALLOW)
        
        result = await executor.execute_tool_by_name(
            "Bash",
            {"command": "echo test"},
            tool_context
        )
        
        assert not result.success
        assert not result.permission_granted
