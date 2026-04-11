"""LSP types and configuration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum

from pydantic import BaseModel, Field


class LspTransport(str, Enum):
    """LSP transport types."""

    STDIO = "stdio"
    SOCKET = "socket"


class LspServerConfig(BaseModel):
    """Configuration for an LSP server.

    Matches ClaudeCode's LSP server configuration format.
    """

    command: str = Field(description="Command to start the server")
    args: list[str] = Field(default_factory=list, description="Command arguments")
    env: dict[str, str] = Field(default_factory=dict, description="Environment variables")

    # Language mapping
    extensionToLanguage: dict[str, str] = Field(
        default_factory=dict, description="Map file extensions to language IDs"
    )

    # Transport
    transport: LspTransport = Field(default=LspTransport.STDIO)
    port: Optional[int] = Field(None, description="Port for socket transport")

    # Timeouts
    startupTimeout: int = Field(default=30000, description="Startup timeout in ms")
    shutdownTimeout: int = Field(default=5000, description="Shutdown timeout in ms")
    requestTimeout: int = Field(default=10000, description="Request timeout in ms")

    # Restart policy
    restartOnCrash: bool = Field(default=True)
    maxRestarts: int = Field(default=3)

    # Initialization
    initializationOptions: Optional[dict[str, Any]] = Field(None)
    settings: Optional[dict[str, Any]] = Field(None)

    # Workspace
    workspaceFolder: Optional[str] = Field(None)


@dataclass
class LspDiagnostics:
    """LSP diagnostics (errors/warnings)."""

    uri: str
    severity: int  # 1=Error, 2=Warning, 3=Information, 4=Hint
    message: str
    source: Optional[str] = None
    code: Optional[str] = None
    line: int = 0
    character: int = 0


@dataclass
class LspCompletionItem:
    """LSP completion item."""

    label: str
    kind: int  # CompletionItemKind
    detail: Optional[str] = None
    documentation: Optional[str] = None
    insertText: Optional[str] = None


@dataclass
class LspLocation:
    """LSP location (for go-to-definition, etc.)."""

    uri: str
    range: dict[str, Any]  # {start: {line, character}, end: {line, character}}


@dataclass
class LspHover:
    """LSP hover information."""

    contents: str
    range: Optional[dict[str, Any]] = None


@dataclass
class LspServer:
    """Running LSP server instance."""

    name: str
    config: LspServerConfig
    process: Optional[asyncio.subprocess.Process] = None
    client: Optional[Any] = None  # LspClient instance

    # State
    initialized: bool = False
    crashed: bool = False
    restart_count: int = 0

    # Capabilities received from server
    capabilities: dict[str, Any] = field(default_factory=dict)

    # Pending requests
    _pending_requests: dict[int, asyncio.Future] = field(default_factory=dict)
    _request_id: int = field(default=0)

    def get_language_for_file(self, file_path: str) -> Optional[str]:
        """Get language ID for a file path."""
        from pathlib import Path

        ext = Path(file_path).suffix
        return self.config.extensionToLanguage.get(ext)

    def supports_language(self, language_id: str) -> bool:
        """Check if server supports a language."""
        return language_id in self.config.extensionToLanguage.values()


class LspError(Exception):
    """LSP-related error."""

    pass


class LspServerStartError(LspError):
    """Failed to start LSP server."""

    pass


class LspRequestError(LspError):
    """LSP request failed."""

    def __init__(self, message: str, code: Optional[int] = None):
        super().__init__(message)
        self.code = code


class LspTimeoutError(LspError):
    """LSP request timed out."""

    pass
