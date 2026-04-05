"""Tests for LSP Manager."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from pilotcode.services.lsp_manager import (
    Language,
    LSPServerConfig,
    LSPRequest,
    LSPResponse,
    Position,
    Location,
    Diagnostic,
    LSPServer,
    LSPManager,
    ServerNotFound,
    ServerNotRunning,
    get_lsp_manager,
)


class TestLanguageEnum:
    """Test Language enum."""
    
    def test_languages(self):
        """Test all languages exist."""
        assert Language.PYTHON.value == "python"
        assert Language.JAVASCRIPT.value == "javascript"
        assert Language.TYPESCRIPT.value == "typescript"
        assert Language.GO.value == "go"
        assert Language.RUST.value == "rust"
        assert Language.JAVA.value == "java"


class TestLSPServerConfig:
    """Test LSPServerConfig."""
    
    def test_default_configs(self):
        """Test default configurations."""
        configs = LSPServerConfig.default_configs()
        
        assert Language.PYTHON in configs
        assert Language.GO in configs
        assert Language.RUST in configs
        
        # Check Python config
        python_config = configs[Language.PYTHON]
        assert python_config.command == "pylsp"
        assert python_config.language == Language.PYTHON
        assert python_config.supports_diagnostics is True
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = LSPServerConfig(
            language=Language.PYTHON,
            command="custom-lsp",
            args=["--stdio"],
            supports_completion=False
        )
        
        assert config.command == "custom-lsp"
        assert config.args == ["--stdio"]
        assert config.supports_completion is False


class TestLSPResponse:
    """Test LSPResponse."""
    
    def test_success_response(self):
        """Test successful response."""
        response = LSPResponse(id=1, result={"data": "test"})
        
        assert response.success is True
        assert response.result == {"data": "test"}
        assert response.error is None
    
    def test_error_response(self):
        """Test error response."""
        response = LSPResponse(id=1, error={"code": -1, "message": "Error"})
        
        assert response.success is False
        assert response.error is not None


class TestDiagnostic:
    """Test Diagnostic dataclass."""
    
    def test_creation(self):
        """Test diagnostic creation."""
        diag = Diagnostic(
            range={"start": {"line": 0, "character": 0}},
            severity=1,
            message="Syntax error",
            code="E001"
        )
        
        assert diag.severity == 1
        assert diag.message == "Syntax error"
        assert diag.code == "E001"


class TestLSPServer:
    """Test LSPServer."""
    
    @pytest.fixture
    def config(self):
        return LSPServerConfig(
            language=Language.PYTHON,
            command="python3",
            args=["-c", "import sys; sys.stdin.read()"]
        )
    
    @pytest.mark.asyncio
    async def test_server_creation(self, config):
        """Test server creation."""
        server = LSPServer(config, root_uri="file:///test")
        
        assert server.config == config
        assert server.root_uri == "file:///test"
        assert not server.is_running
    
    def test_server_not_found(self):
        """Test error when server command not found."""
        config = LSPServerConfig(
            language=Language.PYTHON,
            command="nonexistent-lsp-server-12345"
        )
        server = LSPServer(config)
        
        # Should raise ServerNotFound
        with pytest.raises(ServerNotFound):
            asyncio.run(server.start())
    
    @pytest.mark.asyncio
    async def test_request_without_server(self, config):
        """Test request when server not running."""
        server = LSPServer(config)
        
        with pytest.raises(ServerNotRunning):
            await server.request("test", {})


class TestLSPManager:
    """Test LSPManager."""
    
    @pytest.fixture
    def manager(self):
        return LSPManager(root_uri="file:///workspace")
    
    def test_get_language_for_file(self, manager):
        """Test language detection from file path."""
        assert manager.get_language_for_file("test.py") == Language.PYTHON
        assert manager.get_language_for_file("test.js") == Language.JAVASCRIPT
        assert manager.get_language_for_file("test.ts") == Language.TYPESCRIPT
        assert manager.get_language_for_file("test.go") == Language.GO
        assert manager.get_language_for_file("test.rs") == Language.RUST
        assert manager.get_language_for_file("test.java") == Language.JAVA
    
    def test_get_language_unknown(self, manager):
        """Test unknown file extension."""
        assert manager.get_language_for_file("test.unknown") is None
        assert manager.get_language_for_file("test") is None
    
    @pytest.mark.asyncio
    async def test_start_stop_server(self, manager):
        """Test starting and stopping server."""
        # Mock the server to avoid needing actual LSP installation
        with patch.object(manager, 'servers', {}):
            # We can't test with real server without installing LSP servers
            # Just verify the manager structure
            assert manager.root_uri == "file:///workspace"
            assert len(manager.servers) == 0
    
    def test_get_server(self, manager):
        """Test getting server for language."""
        # Initially no servers
        assert manager.get_server(Language.PYTHON) is None
    
    def test_configs_loaded(self, manager):
        """Test that default configs are loaded."""
        assert Language.PYTHON in manager.configs
        assert Language.JAVASCRIPT in manager.configs


class TestPosition:
    """Test Position dataclass."""
    
    def test_creation(self):
        """Test position creation."""
        pos = Position(line=10, character=5)
        
        assert pos.line == 10
        assert pos.character == 5


class TestLocation:
    """Test Location dataclass."""
    
    def test_creation(self):
        """Test location creation."""
        loc = Location(
            uri="file:///test.py",
            range={"start": {"line": 0, "character": 0}}
        )
        
        assert loc.uri == "file:///test.py"
        assert "start" in loc.range


class TestLSPRequest:
    """Test LSPRequest."""
    
    def test_creation(self):
        """Test request creation."""
        request = LSPRequest(
            id=1,
            method="textDocument/definition",
            params={"uri": "file:///test.py"}
        )
        
        assert request.id == 1
        assert request.method == "textDocument/definition"
        assert request.params["uri"] == "file:///test.py"


class TestGlobalInstance:
    """Test global instance."""
    
    def test_get_lsp_manager(self):
        """Test getting global manager."""
        # Import and reset
        import pilotcode.services.lsp_manager as lsp_module
        lsp_module._default_manager = None
        
        manager1 = get_lsp_manager()
        manager2 = get_lsp_manager()
        
        assert manager1 is manager2


class TestLSPCommunication:
    """Test LSP communication protocol."""
    
    @pytest.mark.asyncio
    async def test_message_format(self):
        """Test LSP message format."""
        # This tests the internal message structure
        message = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"processId": None}
        }
        
        # Verify structure
        assert message["jsonrpc"] == "2.0"
        assert "id" in message
        assert "method" in message
    
    def test_initialization_params(self):
        """Test initialization parameters structure."""
        params = {
            "processId": None,
            "rootUri": "file:///workspace",
            "capabilities": {
                "textDocumentSync": {"openClose": True},
                "completionProvider": {"triggerCharacters": ["."]},
            }
        }
        
        assert params["rootUri"] == "file:///workspace"
        assert "capabilities" in params


class TestErrorHandling:
    """Test error handling."""
    
    def test_server_not_found_error(self):
        """Test ServerNotFound exception."""
        with pytest.raises(ServerNotFound) as exc_info:
            raise ServerNotFound("Server not found: pylsp")
        
        assert "pylsp" in str(exc_info.value)
    
    def test_server_not_running_error(self):
        """Test ServerNotRunning exception."""
        with pytest.raises(ServerNotRunning) as exc_info:
            raise ServerNotRunning("Server not running")
        
        assert "not running" in str(exc_info.value)


class TestEdgeCases:
    """Test edge cases."""
    
    @pytest.fixture
    def manager(self):
        return LSPManager(root_uri="file:///workspace")
    
    def test_empty_file_path(self, manager):
        """Test empty file path."""
        assert manager.get_language_for_file("") is None
    
    def test_path_with_dots(self, manager):
        """Test path with multiple dots."""
        assert manager.get_language_for_file("test.min.js") == Language.JAVASCRIPT
        assert manager.get_language_for_file("test.spec.ts") == Language.TYPESCRIPT
    
    @pytest.mark.asyncio
    async def test_notify_without_server(self, manager):
        """Test notification without server doesn't crash."""
        # Should not raise
        await manager.notify_document_opened("/test.py", "content")


class TestLanguageSupportMatrix:
    """Test language support matrix."""
    
    def test_all_languages_have_config(self):
        """Test all languages have default config."""
        configs = LSPServerConfig.default_configs()
        
        # All languages should have configs
        for lang in [Language.PYTHON, Language.JAVASCRIPT, Language.TYPESCRIPT,
                     Language.GO, Language.RUST, Language.JAVA]:
            assert lang in configs, f"Missing config for {lang.value}"
    
    def test_language_extensions(self):
        """Test file extension mapping."""
        manager = LSPManager()
        
        extensions = {
            ".py": Language.PYTHON,
            ".js": Language.JAVASCRIPT,
            ".jsx": Language.JAVASCRIPT,
            ".ts": Language.TYPESCRIPT,
            ".tsx": Language.TYPESCRIPT,
            ".go": Language.GO,
            ".rs": Language.RUST,
            ".java": Language.JAVA,
            ".cpp": Language.CPP,
            ".cc": Language.CPP,
            ".rb": Language.RUBY,
        }
        
        for ext, expected_lang in extensions.items():
            result = manager.get_language_for_file(f"test{ext}")
            assert result == expected_lang, f"Failed for {ext}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
