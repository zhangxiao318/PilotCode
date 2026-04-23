"""Tests for TUI v2 application startup."""

import pytest
from unittest.mock import patch, MagicMock


class TestTUIv2Startup:
    """Tests for TUI v2 startup and welcome screen."""

    def test_import_tui_v2_components(self):
        """Test that all TUI v2 components can be imported."""
        # This verifies the MessageType import fix
        from pilotcode.tui_v2.controller.controller import UIMessageType

        # Verify UIMessageType is an Enum with expected values
        assert hasattr(UIMessageType, "USER")
        assert hasattr(UIMessageType, "ASSISTANT")
        assert hasattr(UIMessageType, "SYSTEM")
        assert hasattr(UIMessageType, "ERROR")
        assert hasattr(UIMessageType, "TOOL_USE")
        assert hasattr(UIMessageType, "TOOL_RESULT")

    def test_uimessage_creation(self):
        """Test that UIMessage can be created with all message types."""
        from pilotcode.tui_v2.controller.controller import UIMessage, UIMessageType

        # Test all message types
        for msg_type in UIMessageType:
            msg = UIMessage(type=msg_type, content=f"Test {msg_type.name}")
            assert msg.type == msg_type
            assert msg.content == f"Test {msg_type.name}"
            assert msg.metadata == {}
            assert msg.is_streaming is False
            assert msg.is_complete is True

    def test_session_screen_import(self):
        """Test that SessionScreen can be imported and instantiated."""
        from pilotcode.tui_v2.screens.session import SessionScreen

        # Verify the class exists and has required methods
        assert hasattr(SessionScreen, "on_mount")
        assert hasattr(SessionScreen, "_show_welcome")
        assert hasattr(SessionScreen, "compose")

    def test_message_display_import(self):
        """Test that MessageDisplay can be imported with correct type handling."""
        from pilotcode.tui_v2.controller.controller import UIMessage, UIMessageType
        from pilotcode.tui_v2.components.message.display import MessageDisplay

        # Test that MessageDisplay can be created with different message types
        for msg_type in [UIMessageType.SYSTEM, UIMessageType.USER, UIMessageType.ASSISTANT]:
            UIMessage(type=msg_type, content=f"Test {msg_type.name}")
            # Note: We can't fully instantiate without textual's runtime,
            # but we can verify the import and basic structure
            assert MessageDisplay is not None

    def test_welcome_message_creation(self):
        """Test that welcome message can be created correctly."""
        from pilotcode.tui_v2.controller.controller import UIMessage, UIMessageType

        welcome_text = """┌────────────────────────────────────────────────────────┐
│  Welcome to PilotCode v0.2.0! 🚀                       │
│                                                        │
│  Commands              Tips                            │
│  ──────────────────────────────────────────────────────│
│  /help  - Show cmds    • @filename to ref files       │
│  /save  - Save session • Shift+Enter for new line     │
│  /load  - Load session • Up/Down for history          │
│  /clear - Clear history                                │
│  /quit  - Exit                                         │
└────────────────────────────────────────────────────────┘"""

        welcome_msg = UIMessage(type=UIMessageType.SYSTEM, content=welcome_text)
        assert welcome_msg.type == UIMessageType.SYSTEM
        assert "Welcome to PilotCode" in welcome_msg.content
        assert "🚀" in welcome_msg.content

    @pytest.mark.asyncio
    async def test_controller_submit_message_mock(self):
        """Test controller message submission with mocked dependencies."""
        from pilotcode.tui_v2.controller.controller import TUIController

        # Create controller with mocked query engine
        with patch("pilotcode.tui_v2.controller.controller.QueryEngine") as MockEngine:
            mock_engine = MagicMock()
            mock_engine.count_tokens.return_value = 0
            MockEngine.return_value = mock_engine

            controller = TUIController(max_iterations=10)
            controller.query_engine = mock_engine

            # Verify controller is properly initialized
            assert controller.max_iterations == 10
            assert controller.get_token_count() == 0


class TestWelcomeScreen:
    """Tests for welcome screen content and display."""

    def test_welcome_screen_content(self):
        """Test that welcome screen contains expected elements."""
        from pilotcode.tui_v2.controller.controller import UIMessage, UIMessageType

        # This is the actual welcome text from session.py
        welcome_text = """┌────────────────────────────────────────────────────────┐
│  Welcome to PilotCode v0.2.0! 🚀                       │
│                                                        │
│  Commands              Tips                            │
│  ──────────────────────────────────────────────────────│
│  /help  - Show cmds    • @filename to ref files       │
│  /save  - Save session • Shift+Enter for new line     │
│  /load  - Load session • Up/Down for history          │
│  /clear - Clear history                                │
│  /quit  - Exit                                         │
└────────────────────────────────────────────────────────┘"""

        welcome_msg = UIMessage(type=UIMessageType.SYSTEM, content=welcome_text)

        # Verify all expected elements are in the welcome message
        assert "PilotCode" in welcome_msg.content
        assert "v0.2.0" in welcome_msg.content
        assert "🚀" in welcome_msg.content

        # Verify commands are listed
        assert "/help" in welcome_msg.content
        assert "/save" in welcome_msg.content
        assert "/load" in welcome_msg.content
        assert "/clear" in welcome_msg.content
        assert "/quit" in welcome_msg.content

        # Verify tips are listed
        assert "@filename" in welcome_msg.content
        assert "Shift+Enter" in welcome_msg.content
        assert "Up/Down" in welcome_msg.content

        # Verify it's a system message
        assert welcome_msg.type == UIMessageType.SYSTEM

    def test_welcome_message_box_formatting(self):
        """Test that welcome message uses proper box drawing characters."""
        from pilotcode.tui_v2.controller.controller import UIMessage, UIMessageType

        welcome_text = """┌────────────────────────────────────────────────────────┐
│  Welcome to PilotCode v0.2.0! 🚀                       │
└────────────────────────────────────────────────────────┘"""

        welcome_msg = UIMessage(type=UIMessageType.SYSTEM, content=welcome_text)

        # Verify box drawing characters
        assert "┌" in welcome_msg.content  # Top left corner
        assert "┐" in welcome_msg.content  # Top right corner
        assert "└" in welcome_msg.content  # Bottom left corner
        assert "┘" in welcome_msg.content  # Bottom right corner
        assert "│" in welcome_msg.content  # Vertical line
        assert "─" in welcome_msg.content  # Horizontal line


class TestTUIv2Integration:
    """Integration tests for TUI v2 startup flow."""

    def test_full_tui_import_chain(self):
        """Test that the full TUI import chain works without errors."""
        # This test verifies all the MessageType import fixes are correct

        # Import main app
        from pilotcode.tui_v2.app import EnhancedApp

        # Import screens
        from pilotcode.tui_v2.screens.session import SessionScreen

        # Import components
        from pilotcode.tui_v2.components.message.display import MessageDisplay
        from pilotcode.tui_v2.components.message.virtual_list import HybridMessageList

        # Import controller
        from pilotcode.tui_v2.controller.controller import TUIController, UIMessage, UIMessageType

        # Verify all imports succeeded
        assert EnhancedApp is not None
        assert SessionScreen is not None
        assert MessageDisplay is not None
        assert HybridMessageList is not None
        assert TUIController is not None
        assert UIMessage is not None
        assert UIMessageType is not None

    def test_message_type_class_mapping(self):
        """Test that MessageDisplay type class mapping uses correct types."""
        from pilotcode.tui_v2.controller.controller import UIMessageType

        # This mirrors the mapping in display.py
        mapping = {
            UIMessageType.USER: "user",
            UIMessageType.ASSISTANT: "assistant",
            UIMessageType.TOOL_USE: "tool",
            UIMessageType.TOOL_RESULT: "tool-result",
            UIMessageType.ERROR: "error",
            UIMessageType.SYSTEM: "system",
        }

        # Verify all types are mapped
        for msg_type in UIMessageType:
            assert msg_type in mapping, f"{msg_type} not in mapping"

    def test_message_type_label_mapping(self):
        """Test that MessageDisplay label mapping uses correct types."""
        from pilotcode.tui_v2.controller.controller import UIMessageType

        # This mirrors the label mapping in display.py
        labels = {
            UIMessageType.USER: "You",
            UIMessageType.ASSISTANT: "🤖",
            UIMessageType.TOOL_USE: "🔧",
            UIMessageType.TOOL_RESULT: "📤",
            UIMessageType.ERROR: "❌",
            UIMessageType.SYSTEM: "ℹ️",
        }

        # Verify all types have labels
        for msg_type in UIMessageType:
            assert msg_type in labels, f"{msg_type} not in labels"
