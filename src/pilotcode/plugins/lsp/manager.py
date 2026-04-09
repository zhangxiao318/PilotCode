"""LSP Manager for handling multiple language servers."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional

from .types import LspServerConfig, LspServer, LspDiagnostics
from .client import LspClient


class LSPManager:
    """Manages LSP servers from plugins.
    
    Handles:
    - Starting/stopping servers
    - Routing requests to appropriate server
    - Auto-restarting crashed servers
    - File type detection
    """
    
    def __init__(self):
        self._servers: dict[str, LspServer] = {}
        self._clients: dict[str, LspClient] = {}
        self._file_server_map: dict[str, str] = {}  # ext -> server name
        self._language_server_map: dict[str, str] = {}  # language -> server name
        
    async def start_server(
        self,
        name: str,
        config: LspServerConfig,
    ) -> LspServer:
        """Start an LSP server.
        
        Args:
            name: Server name/identifier
            config: Server configuration
            
        Returns:
            Running server instance
        """
        # Stop existing if running
        if name in self._servers:
            await self.stop_server(name)
        
        # Create client
        client = LspClient(config)
        
        # Start
        try:
            success = await client.start()
            if not success:
                raise LspError(f"Failed to start LSP server: {name}")
        except Exception as e:
            raise LspError(f"Failed to start LSP server {name}: {e}")
        
        # Create server instance
        server = LspServer(
            name=name,
            config=config,
            client=client,
            initialized=True,
        )
        
        self._servers[name] = server
        self._clients[name] = client
        
        # Update mappings
        for ext, lang in config.extensionToLanguage.items():
            self._file_server_map[ext] = name
            self._language_server_map[lang] = name
        
        return server
    
    async def stop_server(self, name: str) -> None:
        """Stop an LSP server."""
        if name in self._clients:
            client = self._clients[name]
            await client.stop()
            del self._clients[name]
        
        if name in self._servers:
            del self._servers[name]
    
    async def stop_all(self) -> None:
        """Stop all LSP servers."""
        for name in list(self._servers.keys()):
            await self.stop_server(name)
    
    async def restart_server(self, name: str) -> LspServer:
        """Restart an LSP server."""
        if name not in self._servers:
            raise LspError(f"Server not found: {name}")
        
        config = self._servers[name].config
        await self.stop_server(name)
        return await self.start_server(name, config)
    
    def get_server_for_file(self, file_path: str) -> Optional[LspServer]:
        """Get the appropriate server for a file."""
        ext = Path(file_path).suffix
        
        # Find by extension
        server_name = self._file_server_map.get(ext)
        if server_name:
            return self._servers.get(server_name)
        
        return None
    
    def get_server_for_language(self, language_id: str) -> Optional[LspServer]:
        """Get server by language ID."""
        server_name = self._language_server_map.get(language_id)
        if server_name:
            return self._servers.get(server_name)
        return None
    
    def list_servers(self) -> list[LspServer]:
        """List all running servers."""
        return list(self._servers.values())
    
    def get_server(self, name: str) -> Optional[LspServer]:
        """Get server by name."""
        return self._servers.get(name)
    
    # Convenience methods for common operations
    
    async def did_open(self, file_path: str, text: str) -> bool:
        """Notify appropriate server that file was opened."""
        server = self.get_server_for_file(file_path)
        if not server or not server.client:
            return False
        
        uri = f"file://{Path(file_path).absolute()}"
        lang = server.get_language_for_file(file_path) or "text"
        
        try:
            await server.client.textDocument_didOpen(
                uri=uri,
                language_id=lang,
                version=1,
                text=text,
            )
            return True
        except Exception:
            return False
    
    async def did_change(
        self,
        file_path: str,
        version: int,
        changes: list[dict],
    ) -> bool:
        """Notify appropriate server that file changed."""
        server = self.get_server_for_file(file_path)
        if not server or not server.client:
            return False
        
        uri = f"file://{Path(file_path).absolute()}"
        
        try:
            await server.client.textDocument_didChange(uri, version, changes)
            return True
        except Exception:
            return False
    
    async def get_completions(
        self,
        file_path: str,
        line: int,
        character: int,
    ) -> list[Any]:
        """Get completions at position."""
        server = self.get_server_for_file(file_path)
        if not server or not server.client:
            return []
        
        uri = f"file://{Path(file_path).absolute()}"
        
        try:
            return await server.client.textDocument_completion(uri, line, character)
        except Exception:
            return []
    
    async def get_hover(
        self,
        file_path: str,
        line: int,
        character: int,
    ) -> Optional[Any]:
        """Get hover information at position."""
        server = self.get_server_for_file(file_path)
        if not server or not server.client:
            return None
        
        uri = f"file://{Path(file_path).absolute()}"
        
        try:
            return await server.client.textDocument_hover(uri, line, character)
        except Exception:
            return None
    
    async def go_to_definition(
        self,
        file_path: str,
        line: int,
        character: int,
    ) -> list[Any]:
        """Go to definition."""
        server = self.get_server_for_file(file_path)
        if not server or not server.client:
            return []
        
        uri = f"file://{Path(file_path).absolute()}"
        
        try:
            return await server.client.textDocument_definition(uri, line, character)
        except Exception:
            return []
    
    async def format_document(self, file_path: str) -> list[dict]:
        """Format document."""
        server = self.get_server_for_file(file_path)
        if not server or not server.client:
            return []
        
        uri = f"file://{Path(file_path).absolute()}"
        
        try:
            return await server.client.textDocument_formatting(uri)
        except Exception:
            return []
    
    # Plugin integration
    
    async def load_plugin_servers(
        self,
        lsp_servers: dict[str, LspServerConfig],
    ) -> dict[str, bool]:
        """Load LSP servers from a plugin.
        
        Args:
            lsp_servers: Dict of server name -> config
            
        Returns:
            Dict of server name -> success
        """
        results = {}
        
        for name, config in lsp_servers.items():
            try:
                await self.start_server(name, config)
                results[name] = True
            except Exception as e:
                print(f"Failed to start LSP server {name}: {e}")
                results[name] = False
        
        return results
    
    async def unload_plugin_servers(self, plugin_name: str) -> None:
        """Unload all servers from a plugin.
        
        Args:
            plugin_name: Name of the plugin
        """
        # Find servers started by this plugin
        # (in real implementation, track plugin ownership)
        pass


class LspError(Exception):
    """LSP error."""
    pass


# Global instance
_lsp_manager: Optional[LSPManager] = None


def get_lsp_manager() -> LSPManager:
    """Get global LSP manager instance."""
    global _lsp_manager
    if _lsp_manager is None:
        _lsp_manager = LSPManager()
    return _lsp_manager
