"""Unit tests for hook system."""

import pytest

try:
    from pilotcode.plugins.hooks import (
        HookManager,
        HookType,
        HookContext,
        HookResult,
        PermissionDecision,
        get_hook_manager,
    )

    PLUGINS_AVAILABLE = True
except ImportError:
    PLUGINS_AVAILABLE = False

pytestmark = [
    pytest.mark.plugin,
    pytest.mark.plugin_unit,
    pytest.mark.unit,
    pytest.mark.skipif(not PLUGINS_AVAILABLE, reason="Plugin system not available"),
]


class TestHookContext:
    """Test HookContext."""

    def test_create_context(self):
        """Test creating hook context."""
        context = HookContext(
            hook_type=HookType.PRE_TOOL_USE,
            tool_name="Read",
            tool_input={"path": "/test"},
        )

        assert context.hook_type == HookType.PRE_TOOL_USE
        assert context.tool_name == "Read"
        assert context.tool_input == {"path": "/test"}

    def test_copy_context(self):
        """Test copying context."""
        original = HookContext(
            hook_type=HookType.PRE_TOOL_USE,
            tool_input={"key": "value"},
            metadata={"meta": "data"},
        )

        copy = original.copy()

        assert copy.hook_type == original.hook_type
        assert copy.tool_input == original.tool_input
        # Should be independent copies
        copy.tool_input["new"] = "item"
        assert "new" not in original.tool_input


class TestHookResult:
    """Test HookResult."""

    def test_default_result(self):
        """Test default hook result."""
        result = HookResult()

        assert result.allow_execution is True
        assert result.continue_after is True
        assert result.modified_input is None
        assert result.message is None

    def test_block_result(self):
        """Test result that blocks execution."""
        result = HookResult(
            allow_execution=False,
            stop_reason="Dangerous operation",
            message="Operation blocked for safety",
        )

        assert result.allow_execution is False
        assert result.stop_reason == "Dangerous operation"


class TestPermissionDecision:
    """Test PermissionDecision."""

    def test_allow_decision(self):
        """Test allow decision."""
        decision = PermissionDecision(
            behavior="allow",
            message="Auto-allowed",
        )

        assert decision.behavior == "allow"
        assert decision.message == "Auto-allowed"

    def test_deny_decision(self):
        """Test deny decision."""
        decision = PermissionDecision(
            behavior="deny",
            message="Not allowed",
            interrupt=True,
        )

        assert decision.behavior == "deny"
        assert decision.interrupt is True


class TestHookManager:
    """Test HookManager."""

    def test_create_manager(self):
        """Test creating hook manager."""
        manager = HookManager()

        assert manager.is_enabled() is True
        assert len(manager.list_hooks()) == 0

    @pytest.mark.asyncio
    async def test_register_and_execute_hook(self):
        """Test registering and executing a hook."""
        manager = HookManager()

        called = False

        async def test_hook(context):
            nonlocal called
            called = True
            return HookResult(message="Hook executed")

        manager.register(HookType.PRE_TOOL_USE, test_hook)

        context = HookContext(hook_type=HookType.PRE_TOOL_USE)
        result = await manager.execute_hooks(HookType.PRE_TOOL_USE, context)

        assert called is True
        assert len(result.messages) == 1
        assert result.messages[0] == "Hook executed"

    @pytest.mark.asyncio
    async def test_hook_priority(self):
        """Test hook execution priority."""
        manager = HookManager()

        execution_order = []

        async def low_priority(context):
            execution_order.append("low")
            return HookResult()

        async def high_priority(context):
            execution_order.append("high")
            return HookResult()

        manager.register(HookType.PRE_TOOL_USE, low_priority, priority=0)
        manager.register(HookType.PRE_TOOL_USE, high_priority, priority=100)

        context = HookContext(hook_type=HookType.PRE_TOOL_USE)
        await manager.execute_hooks(HookType.PRE_TOOL_USE, context)

        assert execution_order == ["high", "low"]

    @pytest.mark.asyncio
    async def test_hook_blocks_execution(self):
        """Test that hook can block execution."""
        manager = HookManager()

        async def blocking_hook(context):
            return HookResult(allow_execution=False, stop_reason="Blocked")

        manager.register(HookType.PRE_TOOL_USE, blocking_hook)

        context = HookContext(hook_type=HookType.PRE_TOOL_USE)
        result = await manager.execute_hooks(HookType.PRE_TOOL_USE, context)

        assert result.allow_execution is False
        assert result.stop_reason == "Blocked"

    @pytest.mark.asyncio
    async def test_hook_modifies_input(self):
        """Test that hook can modify input."""
        manager = HookManager()

        async def modifying_hook(context):
            return HookResult(modified_input={"path": "/modified"})

        manager.register(HookType.PRE_TOOL_USE, modifying_hook)

        context = HookContext(
            hook_type=HookType.PRE_TOOL_USE,
            tool_input={"path": "/original"},
        )
        result = await manager.execute_hooks(HookType.PRE_TOOL_USE, context)

        assert result.modified_input == {"path": "/modified"}

    def test_unregister_hook(self):
        """Test unregistering a hook."""
        manager = HookManager()

        async def test_hook(context):
            return HookResult()

        manager.register(HookType.PRE_TOOL_USE, test_hook)
        assert len(manager.get_hooks_for_type(HookType.PRE_TOOL_USE)) == 1

        manager.unregister(HookType.PRE_TOOL_USE, test_hook)
        assert len(manager.get_hooks_for_type(HookType.PRE_TOOL_USE)) == 0

    def test_unregister_by_name(self):
        """Test unregistering hooks by name."""
        manager = HookManager()

        async def hook1(context):
            return HookResult()

        async def hook2(context):
            return HookResult()

        manager.register(HookType.PRE_TOOL_USE, hook1, name="hook1")
        manager.register(HookType.PRE_TOOL_USE, hook2, name="hook2")

        removed = manager.unregister_by_name(name="hook1")
        assert removed == 1
        assert len(manager.get_hooks_for_type(HookType.PRE_TOOL_USE)) == 1

    def test_clear_hooks(self):
        """Test clearing all hooks."""
        manager = HookManager()

        async def test_hook(context):
            return HookResult()

        manager.register(HookType.PRE_TOOL_USE, test_hook)
        manager.register(HookType.POST_TOOL_USE, test_hook)

        manager.clear()

        assert len(manager.get_hooks_for_type(HookType.PRE_TOOL_USE)) == 0
        assert len(manager.get_hooks_for_type(HookType.POST_TOOL_USE)) == 0

    def test_disable_hooks(self):
        """Test disabling hooks."""
        manager = HookManager()
        manager.disable()

        assert manager.is_enabled() is False

    @pytest.mark.asyncio
    async def test_disabled_hooks_not_executed(self):
        """Test that disabled hooks are not executed."""
        manager = HookManager()

        called = False

        async def test_hook(context):
            nonlocal called
            called = True
            return HookResult()

        manager.register(HookType.PRE_TOOL_USE, test_hook)
        manager.disable()

        context = HookContext(hook_type=HookType.PRE_TOOL_USE)
        result = await manager.execute_hooks(HookType.PRE_TOOL_USE, context)

        assert called is False
        assert result.allow_execution is True  # Default when disabled

    @pytest.mark.asyncio
    async def test_convenience_methods(self):
        """Test convenience methods for specific hook types."""
        manager = HookManager()

        called = False

        async def test_hook(context):
            nonlocal called
            called = True
            return HookResult()

        manager.register(HookType.PRE_TOOL_USE, test_hook)

        result = await manager.on_pre_tool_use("Read", {"path": "/test"})

        assert called is True
        assert result.allow_execution is True

    def test_get_hook_manager_singleton(self):
        """Test that get_hook_manager returns singleton."""
        manager1 = get_hook_manager()
        manager2 = get_hook_manager()

        assert manager1 is manager2


class TestHookTypes:
    """Test HookType enum."""

    def test_all_hook_types(self):
        """Test all hook types exist."""
        expected = [
            "PreToolUse",
            "PostToolUse",
            "PostToolUseFailure",
            "SessionStart",
            "UserPromptSubmit",
            "PermissionRequest",
            "PermissionDenied",
            "SubagentStart",
            "CwdChanged",
            "FileChanged",
            "Notification",
            "Elicitation",
            "ElicitationResult",
            "Setup",
        ]

        for hook_type in HookType:
            assert hook_type.value in expected

    def test_hook_type_comparison(self):
        """Test hook type comparison."""
        assert HookType.PRE_TOOL_USE == HookType.PRE_TOOL_USE
        assert HookType.PRE_TOOL_USE != HookType.POST_TOOL_USE
