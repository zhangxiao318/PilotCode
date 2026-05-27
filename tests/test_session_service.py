"""Tests for the MVC UI service layer.

Tests the three-channel UIProtocol types, SessionConfig, CommandResult,
and SessionService with a mocked UIProtocol.
"""

import pytest

from pilotcode.ui.protocol import (
    BlockEvent,
    BlockKind,
    BlockPhase,
    StatusUpdate,
    PermissionResult,
)
from pilotcode.ui.config import SessionConfig, CommandResult, CommandAction
from pilotcode.ui.session_service import SessionService

# ------------------------------------------------------------------
# Protocol type tests
# ------------------------------------------------------------------


class TestBlockEvent:
    """Tests for BlockEvent dataclass."""

    def test_create_block_event(self):
        event = BlockEvent(
            block_id="assistant_1",
            kind=BlockKind.ASSISTANT,
            phase=BlockPhase.OPEN,
            content="Hello",
        )
        assert event.block_id == "assistant_1"
        assert event.kind == BlockKind.ASSISTANT
        assert event.phase == BlockPhase.OPEN
        assert event.content == "Hello"
        assert event.metadata == {}

    def test_block_event_with_metadata(self):
        event = BlockEvent(
            block_id="tool_1",
            kind=BlockKind.TOOL_CALL,
            phase=BlockPhase.OPEN,
            content="Bash",
            metadata={"tool_name": "Bash", "command": "ls"},
        )
        assert event.metadata["tool_name"] == "Bash"
        assert event.metadata["command"] == "ls"

    def test_block_kind_values(self):
        expected = {"assistant", "thinking", "tool_call", "tool_result", "system", "plan_progress"}
        actual = {m.value for m in BlockKind}
        assert actual == expected

    def test_block_phase_values(self):
        expected = {"open", "delta", "close"}
        actual = {m.value for m in BlockPhase}
        assert actual == expected


class TestStatusUpdate:
    """Tests for StatusUpdate dataclass."""

    def test_default_values(self):
        update = StatusUpdate()
        assert update.token_count == 0
        assert update.context_window == 0
        assert update.is_processing is False
        assert update.model_name == ""
        assert update.thinking_mode is False

    def test_custom_values(self):
        update = StatusUpdate(
            token_count=1000,
            context_window=128000,
            is_processing=True,
            model_name="deepseek-v3",
            thinking_mode=True,
        )
        assert update.token_count == 1000
        assert update.model_name == "deepseek-v3"
        assert update.thinking_mode is True


class TestPermissionResult:
    """Tests for PermissionResult dataclass."""

    def test_allowed(self):
        result = PermissionResult(allowed=True)
        assert result.allowed is True
        assert result.for_session is False

    def test_denied_for_session(self):
        result = PermissionResult(allowed=False, for_session=True)
        assert result.allowed is False
        assert result.for_session is True


# ------------------------------------------------------------------
# SessionConfig tests
# ------------------------------------------------------------------


class TestSessionConfig:
    """Tests for SessionConfig dataclass."""

    def test_default_values(self):
        config = SessionConfig()
        assert config.model_name == ""
        assert config.thinking_mode is False
        assert config.auto_allow is False
        assert config.max_iterations == 50
        assert config.mode_policy == "manual"
        assert config.tool_reinforcement is True
        assert config.auto_compact is True
        assert config.auto_save is True
        assert config.loop_guard is True
        assert config.compilation_verify is True
        assert config.permission_mode == "default"
        assert config.cwd == ""

    def test_custom_values(self):
        config = SessionConfig(
            cwd="/tmp/project",
            auto_allow=True,
            max_iterations=100,
            thinking_mode=True,
            model_name="deepseek-v3",
        )
        assert config.cwd == "/tmp/project"
        assert config.auto_allow is True
        assert config.max_iterations == 100
        assert config.thinking_mode is True
        assert config.model_name == "deepseek-v3"

    def test_update_method(self):
        config = SessionConfig()
        changed = config.update(model_name="gpt-4", thinking_mode=True)
        assert "model_name" in changed
        assert "thinking_mode" in changed
        assert config.model_name == "gpt-4"
        assert config.thinking_mode is True

    def test_update_no_change(self):
        config = SessionConfig(auto_allow=True)
        changed = config.update(auto_allow=True)
        assert changed == []

    def test_update_ignores_unknown_keys(self):
        config = SessionConfig()
        changed = config.update(nonexistent_field="value")
        assert changed == []
        assert not hasattr(config, "nonexistent_field")


# ------------------------------------------------------------------
# CommandResult tests
# ------------------------------------------------------------------


class TestCommandResult:
    """Tests for CommandResult and CommandAction."""

    def test_quit_result(self):
        result = CommandResult(action=CommandAction.QUIT, message="Goodbye!")
        assert result.action == CommandAction.QUIT
        assert result.message == "Goodbye!"
        assert result.session_id == ""
        assert result.data == {}

    def test_clear_result(self):
        result = CommandResult(action=CommandAction.CLEAR, message="History cleared")
        assert result.action == CommandAction.CLEAR

    def test_switch_session_result(self):
        result = CommandResult(
            action=CommandAction.SWITCH_SESSION,
            message="Switched",
            session_id="sess_123",
        )
        assert result.action == CommandAction.SWITCH_SESSION
        assert result.session_id == "sess_123"

    def test_command_action_values(self):
        expected = {
            "continue",
            "quit",
            "clear",
            "reload",
            "switch_session",
            "executed",
            "unknown",
            "error",
        }
        actual = {m.value for m in CommandAction}
        assert actual == expected


# ------------------------------------------------------------------
# SessionService tests
# ------------------------------------------------------------------


class MockUIProtocol:
    """Mock UIProtocol for testing SessionService."""

    def __init__(self):
        self.block_events: list[BlockEvent] = []
        self.status_updates: list[StatusUpdate] = []
        self.errors: list[str] = []
        self._permission_result = PermissionResult(allowed=True)
        self._user_input_result = "yes"

    async def on_block_event(self, event: BlockEvent) -> None:
        self.block_events.append(event)

    async def on_status_update(self, update: StatusUpdate) -> None:
        self.status_updates.append(update)

    async def request_permission(
        self, tool_name: str, params: dict, risk_level: str
    ) -> PermissionResult:
        return self._permission_result

    async def request_user_input(self, question: str, options: list[str] | None = None) -> str:
        return self._user_input_result

    async def on_error(self, error: str) -> None:
        self.errors.append(error)


class TestSessionService:
    """Tests for SessionService."""

    def test_create_session_service(self):
        ui = MockUIProtocol()
        config = SessionConfig(cwd=".", auto_allow=True)
        service = SessionService(ui=ui, config=config)
        assert service.query_engine is not None
        assert service._session_id.startswith("sess_")
        assert service.config.cwd != ""

    def test_next_block_id(self):
        ui = MockUIProtocol()
        config = SessionConfig(cwd=".", auto_allow=True)
        service = SessionService(ui=ui, config=config)

        id1 = service._next_block_id(BlockKind.ASSISTANT)
        id2 = service._next_block_id(BlockKind.TOOL_CALL)
        id3 = service._next_block_id(BlockKind.ASSISTANT)

        assert id1 == "assistant_1"
        assert id2 == "tool_call_2"
        assert id3 == "assistant_3"

    def test_is_safe_tool(self):
        ui = MockUIProtocol()
        config = SessionConfig(cwd=".", auto_allow=True)
        service = SessionService(ui=ui, config=config)

        # FileRead should be safe
        assert service._is_safe_tool("FileRead", {"path": "/tmp/test.txt"}) is True
        # Bash with read-only command should be safe
        assert service._is_safe_tool("Bash", {"command": "ls"}) is True
        # Bash with destructive command should NOT be safe
        assert service._is_safe_tool("Bash", {"command": "rm -rf /"}) is False
        # FileWrite should NOT be safe
        assert service._is_safe_tool("FileWrite", {"path": "/tmp/test.txt"}) is False

    @pytest.mark.asyncio
    async def test_handle_command_quit(self):
        ui = MockUIProtocol()
        config = SessionConfig(cwd=".", auto_allow=True)
        service = SessionService(ui=ui, config=config)

        result = await service.handle_command("/quit")
        assert result.action == CommandAction.QUIT

    @pytest.mark.asyncio
    async def test_handle_command_help(self):
        ui = MockUIProtocol()
        config = SessionConfig(cwd=".", auto_allow=True)
        service = SessionService(ui=ui, config=config)

        result = await service.handle_command("/help")
        assert result.action == CommandAction.CONTINUE
        assert "Commands" in result.message or "help" in result.message.lower()

    @pytest.mark.asyncio
    async def test_handle_command_clear(self):
        ui = MockUIProtocol()
        config = SessionConfig(cwd=".", auto_allow=True)
        service = SessionService(ui=ui, config=config)

        result = await service.handle_command("/clear")
        assert result.action == CommandAction.CLEAR

    @pytest.mark.asyncio
    async def test_handle_command_unknown(self):
        ui = MockUIProtocol()
        config = SessionConfig(cwd=".", auto_allow=True)
        service = SessionService(ui=ui, config=config)

        result = await service.handle_command("/nonexistent")
        # Unknown commands fall through to registry which returns UNKNOWN or CONTINUE
        assert result.action in (CommandAction.UNKNOWN, CommandAction.CONTINUE, CommandAction.ERROR)

    @pytest.mark.asyncio
    async def test_cancel_current_query_no_query(self):
        ui = MockUIProtocol()
        config = SessionConfig(cwd=".", auto_allow=True)
        service = SessionService(ui=ui, config=config)

        result = service.cancel_current_query()
        assert result is None  # No query running

    def test_set_model(self):
        ui = MockUIProtocol()
        config = SessionConfig(cwd=".", auto_allow=True)
        service = SessionService(ui=ui, config=config)

        service.set_model("deepseek-v3")
        assert service.config.model_name == "deepseek-v3"

    def test_set_thinking_mode(self):
        ui = MockUIProtocol()
        config = SessionConfig(cwd=".", auto_allow=True)
        service = SessionService(ui=ui, config=config)

        service.set_thinking_mode(True)
        assert service.config.thinking_mode is True

    def test_update_config(self):
        ui = MockUIProtocol()
        config = SessionConfig(cwd=".", auto_allow=True)
        service = SessionService(ui=ui, config=config)

        service.update_config(max_iterations=100, auto_compact=False)
        assert service.config.max_iterations == 100
        assert service.config.auto_compact is False

    def test_get_token_count(self):
        ui = MockUIProtocol()
        config = SessionConfig(cwd=".", auto_allow=True)
        service = SessionService(ui=ui, config=config)

        count = service.get_token_count()
        assert isinstance(count, int)
        assert count >= 0

    def test_get_token_info(self):
        ui = MockUIProtocol()
        config = SessionConfig(cwd=".", auto_allow=True)
        service = SessionService(ui=ui, config=config)

        info = service.get_token_info()
        assert "count" in info
        assert "context_window" in info
        assert "max_output_tokens" in info
        assert "usable" in info

    def test_clear_history(self):
        ui = MockUIProtocol()
        config = SessionConfig(cwd=".", auto_allow=True)
        service = SessionService(ui=ui, config=config)

        # Should not raise
        service.clear_history()

    def test_normalize_tool_name(self):
        ui = MockUIProtocol()
        config = SessionConfig(cwd=".", auto_allow=True)
        service = SessionService(ui=ui, config=config)

        # Known tool names should be normalized
        result = service._normalize_tool_name("bash")
        assert result.lower() == "bash" or result == "Bash"

    @pytest.mark.asyncio
    async def test_find_extension_command_not_found(self):
        ui = MockUIProtocol()
        config = SessionConfig(cwd="/tmp/nonexistent", auto_allow=True)
        service = SessionService(ui=ui, config=config)

        result = service._find_extension_command("nonexistent_cmd")
        assert result is None


# ------------------------------------------------------------------
# Integration: SimpleCLIProtocol tests
# ------------------------------------------------------------------


class TestSimpleCLIProtocol:
    """Tests for SimpleCLIProtocol adapter."""

    def test_import(self):
        from pilotcode.tui.simple_cli import SimpleCLIProtocol

        protocol = SimpleCLIProtocol()
        assert hasattr(protocol, "on_block_event")
        assert hasattr(protocol, "on_status_update")
        assert hasattr(protocol, "request_permission")
        assert hasattr(protocol, "request_user_input")
        assert hasattr(protocol, "on_error")


# ------------------------------------------------------------------
# Integration: TUIProtocol tests
# ------------------------------------------------------------------


class TestTUIProtocol:
    """Tests for TUIProtocol adapter."""

    def test_import(self):
        from pilotcode.tui_v2.controller.controller import TUIProtocol

        protocol = TUIProtocol()
        assert hasattr(protocol, "on_block_event")
        assert hasattr(protocol, "on_status_update")
        assert hasattr(protocol, "request_permission")
        assert hasattr(protocol, "on_error")

    @pytest.mark.asyncio
    async def test_block_event_to_ui_message(self):
        from pilotcode.tui_v2.controller.controller import TUIProtocol, UIMessageType

        protocol = TUIProtocol()
        event = BlockEvent(
            block_id="assistant_1",
            kind=BlockKind.ASSISTANT,
            phase=BlockPhase.CLOSE,
            content="Hello world",
        )
        await protocol.on_block_event(event)
        assert len(protocol.collected_messages) == 1
        assert protocol.collected_messages[0].type == UIMessageType.ASSISTANT
        assert protocol.collected_messages[0].content == "Hello world"

    @pytest.mark.asyncio
    async def test_system_block_event(self):
        from pilotcode.tui_v2.controller.controller import TUIProtocol, UIMessageType

        protocol = TUIProtocol()
        event = BlockEvent(
            block_id="system_1",
            kind=BlockKind.SYSTEM,
            phase=BlockPhase.CLOSE,
            content="Context compressed",
        )
        await protocol.on_block_event(event)
        assert len(protocol.collected_messages) == 1
        assert protocol.collected_messages[0].type == UIMessageType.SYSTEM


# ------------------------------------------------------------------
# Integration: WebSocketProtocol tests
# ------------------------------------------------------------------


class TestWebSocketProtocol:
    """Tests for WebSocketProtocol adapter."""

    def test_import(self):
        from pilotcode.web.server import WebSocketProtocol

        assert WebSocketProtocol is not None
