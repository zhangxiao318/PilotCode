"""LSP (Language Server Protocol) support for plugins.

Allows plugins to provide language servers for enhanced code intelligence.

Example:
    from pilotcode.plugins.lsp import LSPManager

    manager = LSPManager()
    await manager.start_server("typescript", {
        "command": "typescript-language-server",
        "args": ["--stdio"],
        "extensionToLanguage": {".ts": "typescript"}
    })
"""

from .manager import LSPManager, get_lsp_manager
from .types import LspServerConfig, LspServer, LspDiagnostics, LspTransport
from .client import LspClient

__all__ = [
    "LSPManager",
    "get_lsp_manager",
    "LspServerConfig",
    "LspServer",
    "LspDiagnostics",
    "LspTransport",
    "LspClient",
]
