"""Tests for app_state module."""

import pytest
from dataclasses import fields

from pilotcode.state.app_state import (
    ModelSettings,
    MCPSettings,
    Settings,
    AppState,
    get_default_app_state,
    create_store,
)
from pilotcode.types.permissions import ToolPermissionContext


class TestModelSettings:
    """Tests for ModelSettings."""

    def test_default_values(self):
        """Test default model settings."""
        settings = ModelSettings()

        assert settings.primary == "local/default"
        assert settings.fallback is None
        assert settings.thinking is False
        assert settings.max_tokens == 4096

    def test_custom_values(self):
        """Test custom model settings."""
        settings = ModelSettings(
            primary="openai/gpt-4", fallback="anthropic/claude-3", thinking=True, max_tokens=8192
        )

        assert settings.primary == "openai/gpt-4"
        assert settings.fallback == "anthropic/claude-3"
        assert settings.thinking is True
        assert settings.max_tokens == 8192


class TestMCPSettings:
    """Tests for MCPSettings."""

    def test_default_values(self):
        """Test default MCP settings."""
        settings = MCPSettings()

        assert settings.servers == {}
        assert settings.enabled is True

    def test_custom_servers(self):
        """Test MCP settings with servers."""
        servers = {
            "filesystem": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem"],
            },
            "github": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"]},
        }
        settings = MCPSettings(servers=servers, enabled=False)

        assert settings.servers == servers
        assert settings.enabled is False


class TestSettings:
    """Tests for Settings."""

    def test_default_values(self):
        """Test default settings."""
        settings = Settings()

        assert settings.verbose is False
        assert settings.theme == "default"
        assert settings.auto_compact is True
        assert isinstance(settings.model, ModelSettings)
        assert isinstance(settings.mcp, MCPSettings)
        assert settings.allowed_tools == []

    def test_nested_settings(self):
        """Test nested settings initialization."""
        model_settings = ModelSettings(primary="custom-model")
        mcp_settings = MCPSettings(enabled=False)

        settings = Settings(
            verbose=True,
            theme="dark",
            model=model_settings,
            mcp=mcp_settings,
            allowed_tools=["Bash", "FileRead"],
        )

        assert settings.verbose is True
        assert settings.theme == "dark"
        assert settings.model.primary == "custom-model"
        assert settings.mcp.enabled is False
        assert settings.allowed_tools == ["Bash", "FileRead"]


class TestAppState:
    """Tests for AppState."""

    def test_default_values(self):
        """Test default app state."""
        state = AppState()

        assert isinstance(state.settings, Settings)
        assert state.session_id is None
        assert state.session_name is None
        assert state.status_line is None
        assert state.verbose is False
        assert isinstance(state.tool_permission_context, ToolPermissionContext)
        assert state.mcp_clients == []
        assert state.mcp_tools == []
        assert state.mcp_commands == []
        assert state.messages == []
        assert state.tasks == {}
        assert state.total_cost_usd == 0.0
        assert state.total_tokens == 0
        assert state.version == "0.1.0"

    def test_custom_values(self):
        """Test custom app state."""
        settings = Settings(theme="dark")
        permission_context = ToolPermissionContext(mode="auto")

        state = AppState(
            settings=settings,
            session_id="test-session-123",
            session_name="Test Session",
            cwd="/custom/path",
            verbose=True,
            tool_permission_context=permission_context,
            total_cost_usd=0.05,
            total_tokens=1500,
            version="1.0.0",
        )

        assert state.settings.theme == "dark"
        assert state.session_id == "test-session-123"
        assert state.session_name == "Test Session"
        assert state.cwd == "/custom/path"
        assert state.verbose is True
        assert state.tool_permission_context.mode == "auto"
        assert state.total_cost_usd == 0.05
        assert state.total_tokens == 1500
        assert state.version == "1.0.0"

    def test_state_is_dataclass(self):
        """Test that AppState is a dataclass."""
        state = AppState()

        # Check it's a dataclass by checking for __dataclass_fields__
        assert hasattr(state, "__dataclass_fields__")

        # Check fields exist
        field_names = [f.name for f in fields(AppState)]
        assert "settings" in field_names
        assert "cwd" in field_names
        assert "session_id" in field_names


class TestGetDefaultAppState:
    """Tests for get_default_app_state function."""

    def test_returns_app_state(self):
        """Test that function returns AppState."""
        state = get_default_app_state()

        assert isinstance(state, AppState)
        assert state.version == "0.1.0"

    def test_returns_new_instance(self):
        """Test that function returns new instance each time."""
        state1 = get_default_app_state()
        state2 = get_default_app_state()

        assert state1 is not state2
        assert state1 == state2  # Equal values


class TestCreateStore:
    """Tests for create_store function."""

    def test_creates_store_with_default_state(self):
        """Test creating store with default state."""
        store = create_store()

        from pilotcode.state.store import Store

        assert isinstance(store, Store)
        assert isinstance(store.get_state(), AppState)

    def test_creates_store_with_custom_state(self):
        """Test creating store with custom state."""
        custom_state = AppState(session_id="custom")
        store = create_store(custom_state)

        assert store.get_state().session_id == "custom"

    def test_store_is_independent(self):
        """Test that created stores are independent."""
        store1 = create_store(AppState(session_id="store1"))
        store2 = create_store(AppState(session_id="store2"))

        assert store1.get_state().session_id == "store1"
        assert store2.get_state().session_id == "store2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
