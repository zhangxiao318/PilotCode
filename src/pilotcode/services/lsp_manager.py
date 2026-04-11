"""LSP Manager - Complete Language Server Protocol management.

This module provides:
1. Multi-language LSP server management
2. Automatic server lifecycle (start/stop/restart)
3. Request routing and response handling
4. Workspace synchronization
5. Diagnostics aggregation
6. Symbol resolution across servers

Features:
- Support for Python, JavaScript/TypeScript, Go, Rust, Java
- Automatic server installation detection
- Workspace/didChange notification
- Diagnostics collection
- Code actions
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from enum import Enum
import logging

# Configure logging
logger = logging.getLogger(__name__)


class LSPError(Exception):
    """Base exception for LSP errors."""

    pass


class ServerNotFound(LSPError):
    """Raised when LSP server is not found."""

    pass


class ServerNotRunning(LSPError):
    """Raised when server is not running."""

    pass


class RequestTimeout(LSPError):
    """Raised when request times out."""

    pass


class Language(Enum):
    """Supported programming languages."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    RUST = "rust"
    JAVA = "java"
    CPP = "cpp"
    RUBY = "ruby"


@dataclass
class LSPServerConfig:
    """Configuration for an LSP server."""

    language: Language
    command: str
    args: list[str] = field(default_factory=list)
    initialization_options: dict[str, Any] = field(default_factory=dict)

    # Server capabilities
    supports_diagnostics: bool = True
    supports_completion: bool = True
    supports_definition: bool = True
    supports_references: bool = True
    supports_hover: bool = True
    supports_rename: bool = True
    supports_formatting: bool = True
    supports_code_actions: bool = True

    # Auto-detect if available
    auto_detect: bool = True

    @classmethod
    def default_configs(cls) -> dict[Language, LSPServerConfig]:
        """Get default configurations for all languages."""
        return {
            Language.PYTHON: cls(
                language=Language.PYTHON,
                command="pylsp",
                args=[],
                supports_diagnostics=True,
                supports_completion=True,
            ),
            Language.JAVASCRIPT: cls(
                language=Language.JAVASCRIPT,
                command="typescript-language-server",
                args=["--stdio"],
            ),
            Language.TYPESCRIPT: cls(
                language=Language.TYPESCRIPT,
                command="typescript-language-server",
                args=["--stdio"],
            ),
            Language.GO: cls(
                language=Language.GO,
                command="gopls",
                args=[],
            ),
            Language.RUST: cls(
                language=Language.RUST,
                command="rust-analyzer",
                args=[],
            ),
            Language.JAVA: cls(
                language=Language.JAVA,
                command="jdtls",
                args=[],
            ),
        }


@dataclass
class LSPRequest:
    """An LSP request."""

    id: int
    method: str
    params: dict[str, Any]


@dataclass
class LSPResponse:
    """An LSP response."""

    id: int
    result: Any = None
    error: Optional[dict[str, Any]] = None

    @property
    def success(self) -> bool:
        return self.error is None


@dataclass
class Position:
    """Position in a document."""

    line: int  # 0-indexed
    character: int  # 0-indexed


@dataclass
class Location:
    """Location in a document."""

    uri: str
    range: dict[str, Any]


@dataclass
class Diagnostic:
    """LSP diagnostic."""

    range: dict[str, Any]
    severity: int  # 1=Error, 2=Warning, 3=Info, 4=Hint
    message: str
    code: Optional[str] = None
    source: Optional[str] = None


class LSPServer:
    """Manages a single LSP server process."""

    def __init__(self, config: LSPServerConfig, root_uri: str = ""):
        self.config = config
        self.root_uri = root_uri
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 0
        self.pending_requests: dict[int, asyncio.Future] = {}
        self._running = False
        self._reader_task: Optional[asyncio.Task] = None
        self.capabilities: dict[str, Any] = {}

        # Diagnostics storage
        self.diagnostics: dict[str, list[Diagnostic]] = {}

    async def start(self) -> bool:
        """Start the LSP server."""
        if self._running:
            return True

        # Check if command exists
        if not shutil.which(self.config.command):
            raise ServerNotFound(
                f"LSP server not found: {self.config.command}. "
                f"Please install it for {self.config.language.value} support."
            )

        try:
            # Start process
            self.process = subprocess.Popen(
                [self.config.command] + self.config.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self._running = True

            # Start reader task
            self._reader_task = asyncio.create_task(self._read_responses())

            # Send initialize request
            initialized = await self._initialize()
            if not initialized:
                await self.stop()
                return False

            logger.info(
                f"LSP server {self.config.command} started for {self.config.language.value}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to start LSP server: {e}")
            self._running = False
            return False

    async def stop(self) -> None:
        """Stop the LSP server."""
        if not self._running:
            return

        self._running = False

        # Cancel reader task
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        # Terminate process
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(asyncio.to_thread(self.process.wait), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
            except Exception:
                pass

        self.process = None
        logger.info(f"LSP server {self.config.command} stopped")

    async def restart(self) -> bool:
        """Restart the LSP server."""
        await self.stop()
        return await self.start()

    async def _initialize(self) -> bool:
        """Send initialize request."""
        init_params = {
            "processId": None,
            "rootUri": self.root_uri,
            "capabilities": {
                "textDocumentSync": {
                    "openClose": True,
                    "change": 2,  # Incremental
                },
                "completionProvider": {
                    "triggerCharacters": [".", ":", ">"],
                },
                "hoverProvider": True,
                "definitionProvider": True,
                "referencesProvider": True,
                "documentSymbolProvider": True,
                "codeActionProvider": True,
                "renameProvider": True,
                "diagnosticProvider": {
                    "interFileDependencies": True,
                    "workspaceDiagnostics": True,
                },
            },
        }

        try:
            response = await self.request("initialize", init_params, timeout=30.0)
            if response.success and response.result:
                self.capabilities = response.result.get("capabilities", {})

                # Send initialized notification
                await self.notify("initialized", {})
                return True
        except Exception as e:
            logger.error(f"Initialize failed: {e}")

        return False

    async def request(
        self, method: str, params: dict[str, Any], timeout: float = 10.0
    ) -> LSPResponse:
        """Send a request to the server."""
        if not self._running or not self.process:
            raise ServerNotRunning(f"Server {self.config.command} is not running")

        # Generate request ID
        self.request_id += 1
        request_id = self.request_id

        # Create request
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        # Create future for response
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self.pending_requests[request_id] = future

        try:
            # Send request
            await self._send_message(request)

            # Wait for response
            response_data = await asyncio.wait_for(future, timeout=timeout)

            return LSPResponse(
                id=response_data.get("id", request_id),
                result=response_data.get("result"),
                error=response_data.get("error"),
            )

        except asyncio.TimeoutError:
            raise RequestTimeout(f"Request {method} timed out after {timeout}s")
        finally:
            self.pending_requests.pop(request_id, None)

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        """Send a notification (no response expected)."""
        if not self._running or not self.process:
            return

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        await self._send_message(notification)

    async def _send_message(self, message: dict[str, Any]) -> None:
        """Send a message to the server."""
        if not self.process or not self.process.stdin:
            return

        data = json.dumps(message)
        header = f"Content-Length: {len(data)}\r\n\r\n"
        full_message = header + data

        # Write in executor to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._write_to_stdin, full_message.encode("utf-8"))

    def _write_to_stdin(self, data: bytes) -> None:
        """Write data to stdin (sync)."""
        if self.process and self.process.stdin:
            self.process.stdin.write(data)
            self.process.stdin.flush()

    async def _read_responses(self) -> None:
        """Read responses from server."""
        if not self.process or not self.process.stdout:
            return

        while self._running:
            try:
                response = await self._read_message()
                if response:
                    await self._handle_message(response)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error reading response: {e}")
                await asyncio.sleep(0.1)

    async def _read_message(self) -> Optional[dict[str, Any]]:
        """Read a single LSP message."""
        if not self.process or not self.process.stdout:
            return None

        try:
            # Read headers
            headers = {}
            while True:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, self.process.stdout.readline
                )

                if not line:
                    return None

                line = line.decode("utf-8").strip()

                if not line:
                    break

                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.strip().lower()] = value.strip()

            # Get content length
            content_length = int(headers.get("content-length", 0))
            if content_length == 0:
                return None

            # Read content
            content = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: (
                    self.process.stdout.read(content_length)
                    if self.process and self.process.stdout
                    else b""
                ),
            )

            return json.loads(content.decode("utf-8"))

        except Exception as e:
            logger.error(f"Error reading message: {e}")
            return None

    async def _handle_message(self, message: dict[str, Any]) -> None:
        """Handle incoming message."""
        # Check if it's a response
        if "id" in message:
            request_id = message["id"]
            if request_id in self.pending_requests:
                future = self.pending_requests[request_id]
                if not future.done():
                    future.set_result(message)

        # Check if it's a notification
        elif "method" in message:
            await self._handle_notification(message)

    async def _handle_notification(self, message: dict[str, Any]) -> None:
        """Handle server notification."""
        method = message.get("method", "")
        params = message.get("params", {})

        if method == "textDocument/publishDiagnostics":
            await self._handle_diagnostics(params)

    async def _handle_diagnostics(self, params: dict[str, Any]) -> None:
        """Handle diagnostics notification."""
        uri = params.get("uri", "")
        diagnostics_data = params.get("diagnostics", [])

        diagnostics = []
        for d in diagnostics_data:
            diagnostic = Diagnostic(
                range=d.get("range", {}),
                severity=d.get("severity", 1),
                message=d.get("message", ""),
                code=str(d.get("code")) if d.get("code") else None,
                source=d.get("source"),
            )
            diagnostics.append(diagnostic)

        self.diagnostics[uri] = diagnostics

    @property
    def is_running(self) -> bool:
        return self._running and self.process is not None


class LSPManager:
    """Manages multiple LSP servers for different languages."""

    def __init__(self, root_uri: str = ""):
        self.root_uri = root_uri
        self.servers: dict[Language, LSPServer] = {}
        self.configs = LSPServerConfig.default_configs()

    async def start_server(self, language: Language) -> bool:
        """Start LSP server for a language."""
        if language in self.servers:
            return self.servers[language].is_running

        if language not in self.configs:
            logger.warning(f"No LSP config for {language.value}")
            return False

        config = self.configs[language]
        server = LSPServer(config, self.root_uri)

        try:
            success = await server.start()
            if success:
                self.servers[language] = server
                return True
        except ServerNotFound as e:
            logger.warning(str(e))

        return False

    async def stop_server(self, language: Language) -> None:
        """Stop LSP server for a language."""
        if language in self.servers:
            await self.servers[language].stop()
            del self.servers[language]

    async def stop_all(self) -> None:
        """Stop all LSP servers."""
        for language in list(self.servers.keys()):
            await self.stop_server(language)

    def get_server(self, language: Language) -> Optional[LSPServer]:
        """Get server for a language."""
        return self.servers.get(language)

    def get_language_for_file(self, file_path: str) -> Optional[Language]:
        """Determine language from file extension."""
        ext = Path(file_path).suffix.lower()

        mapping = {
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

        return mapping.get(ext)

    async def get_definition(
        self, file_path: str, line: int, character: int
    ) -> Optional[list[Location]]:
        """Get definition for symbol at position."""
        language = self.get_language_for_file(file_path)
        if not language:
            return None

        server = self.servers.get(language)
        if not server or not server.is_running:
            return None

        if not server.config.supports_definition:
            return None

        uri = f"file://{file_path}"

        try:
            response = await server.request(
                "textDocument/definition",
                {
                    "textDocument": {"uri": uri},
                    "position": {"line": line, "character": character},
                },
            )

            if response.success and response.result:
                results = response.result
                if not isinstance(results, list):
                    results = [results]

                return [Location(uri=r.get("uri", ""), range=r.get("range", {})) for r in results]
        except Exception as e:
            logger.error(f"Definition request failed: {e}")

        return None

    async def get_references(
        self, file_path: str, line: int, character: int, include_declaration: bool = True
    ) -> Optional[list[Location]]:
        """Get references for symbol at position."""
        language = self.get_language_for_file(file_path)
        if not language:
            return None

        server = self.servers.get(language)
        if not server or not server.is_running:
            return None

        if not server.config.supports_references:
            return None

        uri = f"file://{file_path}"

        try:
            response = await server.request(
                "textDocument/references",
                {
                    "textDocument": {"uri": uri},
                    "position": {"line": line, "character": character},
                    "context": {"includeDeclaration": include_declaration},
                },
            )

            if response.success and response.result:
                return [
                    Location(uri=r.get("uri", ""), range=r.get("range", {}))
                    for r in response.result
                ]
        except Exception as e:
            logger.error(f"References request failed: {e}")

        return None

    async def get_hover(self, file_path: str, line: int, character: int) -> Optional[str]:
        """Get hover information."""
        language = self.get_language_for_file(file_path)
        if not language:
            return None

        server = self.servers.get(language)
        if not server or not server.is_running:
            return None

        if not server.config.supports_hover:
            return None

        uri = f"file://{file_path}"

        try:
            response = await server.request(
                "textDocument/hover",
                {
                    "textDocument": {"uri": uri},
                    "position": {"line": line, "character": character},
                },
            )

            if response.success and response.result:
                contents = response.result.get("contents", {})
                if isinstance(contents, str):
                    return contents
                elif isinstance(contents, dict):
                    return contents.get("value", "")
                elif isinstance(contents, list) and contents:
                    return (
                        contents[0].get("value", "")
                        if isinstance(contents[0], dict)
                        else str(contents[0])
                    )
        except Exception as e:
            logger.error(f"Hover request failed: {e}")

        return None

    async def notify_document_opened(self, file_path: str, content: str) -> None:
        """Notify server that document was opened."""
        language = self.get_language_for_file(file_path)
        if not language:
            return

        server = self.servers.get(language)
        if not server or not server.is_running:
            return

        uri = f"file://{file_path}"
        language_id = language.value

        await server.notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": language_id,
                    "version": 1,
                    "text": content,
                }
            },
        )

    async def notify_document_changed(
        self, file_path: str, changes: list[dict[str, Any]], version: int
    ) -> None:
        """Notify server of document changes."""
        language = self.get_language_for_file(file_path)
        if not language:
            return

        server = self.servers.get(language)
        if not server or not server.is_running:
            return

        uri = f"file://{file_path}"

        await server.notify(
            "textDocument/didChange",
            {
                "textDocument": {"uri": uri, "version": version},
                "contentChanges": changes,
            },
        )

    def get_diagnostics(self, file_path: str) -> list[Diagnostic]:
        """Get diagnostics for a file."""
        language = self.get_language_for_file(file_path)
        if not language:
            return []

        server = self.servers.get(language)
        if not server:
            return []

        uri = f"file://{file_path}"
        return server.diagnostics.get(uri, [])

    def get_running_servers(self) -> list[Language]:
        """Get list of running servers."""
        return [lang for lang, server in self.servers.items() if server.is_running]


# Global instance
_default_manager: Optional[LSPManager] = None


def get_lsp_manager(root_uri: str = "") -> LSPManager:
    """Get global LSP manager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = LSPManager(root_uri)
    return _default_manager
