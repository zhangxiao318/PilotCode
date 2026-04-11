"""Unit tests for LSP support."""

import pytest

try:
    from pilotcode.plugins.lsp import (
        LSPManager,
        LspServerConfig,
        LspServer,
        LspTransport,
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


class TestLspServerConfig:
    """Test LspServerConfig."""

    def test_create_config(self):
        """Test creating config."""
        config = LspServerConfig(
            command="typescript-language-server",
            args=["--stdio"],
            extensionToLanguage={".ts": "typescript"},
        )

        assert config.command == "typescript-language-server"
        assert config.args == ["--stdio"]
        assert config.extensionToLanguage == {".ts": "typescript"}

    def test_default_transport(self):
        """Test default transport is stdio."""
        config = LspServerConfig(command="test")

        assert config.transport == LspTransport.STDIO

    def test_default_timeouts(self):
        """Test default timeouts."""
        config = LspServerConfig(command="test")

        assert config.startupTimeout == 30000
        assert config.shutdownTimeout == 5000
        assert config.requestTimeout == 10000

    def test_restart_policy(self):
        """Test restart policy defaults."""
        config = LspServerConfig(command="test")

        assert config.restartOnCrash is True
        assert config.maxRestarts == 3


class TestLspServer:
    """Test LspServer."""

    def test_create_server(self):
        """Test creating server instance."""
        config = LspServerConfig(
            command="test",
            extensionToLanguage={".ts": "typescript"},
        )
        server = LspServer(
            name="typescript",
            config=config,
        )

        assert server.name == "typescript"
        assert server.initialized is False
        assert server.restart_count == 0

    def test_get_language_for_file(self):
        """Test getting language for file."""
        config = LspServerConfig(
            command="test",
            extensionToLanguage={
                ".ts": "typescript",
                ".js": "javascript",
            },
        )
        server = LspServer(name="test", config=config)

        assert server.get_language_for_file("/path/to/file.ts") == "typescript"
        assert server.get_language_for_file("/path/to/file.js") == "javascript"
        assert server.get_language_for_file("/path/to/file.py") is None

    def test_supports_language(self):
        """Test checking language support."""
        config = LspServerConfig(
            command="test",
            extensionToLanguage={".ts": "typescript"},
        )
        server = LspServer(name="test", config=config)

        assert server.supports_language("typescript") is True
        assert server.supports_language("python") is False


class TestLSPManager:
    """Test LSPManager."""

    def test_create_manager(self):
        """Test creating manager."""
        manager = LSPManager()

        assert len(manager.list_servers()) == 0

    def test_get_server_for_file(self):
        """Test getting server for file type."""
        manager = LSPManager()

        # Manually register a server mapping
        config = LspServerConfig(
            command="test",
            extensionToLanguage={".ts": "typescript"},
        )
        server = LspServer(name="typescript", config=config)
        manager._servers["typescript"] = server
        manager._file_server_map[".ts"] = "typescript"

        result = manager.get_server_for_file("/path/to/file.ts")

        assert result is not None
        assert result.name == "typescript"

    def test_get_server_for_unsupported_file(self):
        """Test getting server for unsupported file."""
        manager = LSPManager()

        result = manager.get_server_for_file("/path/to/file.xyz")

        assert result is None

    def test_get_server_for_language(self):
        """Test getting server by language ID."""
        manager = LSPManager()

        config = LspServerConfig(
            command="test",
            extensionToLanguage={".ts": "typescript"},
        )
        server = LspServer(name="typescript", config=config)
        manager._servers["typescript"] = server
        manager._language_server_map["typescript"] = "typescript"

        result = manager.get_server_for_language("typescript")

        assert result is not None

    def test_list_servers(self):
        """Test listing servers."""
        manager = LSPManager()

        config = LspServerConfig(command="test1")
        server1 = LspServer(name="server1", config=config)
        server2 = LspServer(name="server2", config=config)

        manager._servers["server1"] = server1
        manager._servers["server2"] = server2

        servers = manager.list_servers()

        assert len(servers) == 2


class TestLspTypes:
    """Test LSP types."""

    def test_transport_enum(self):
        """Test transport enum values."""
        assert LspTransport.STDIO.value == "stdio"
        assert LspTransport.SOCKET.value == "socket"
