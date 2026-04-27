"""Application state definitions."""

from typing import Any, TYPE_CHECKING
from dataclasses import dataclass, field
from pathlib import Path

from ..types.permissions import ToolPermissionContext

if TYPE_CHECKING:
    from .store import Store


@dataclass
class ModelSettings:
    """Model settings."""

    primary: str = "local/default"
    fallback: str | None = None
    thinking: bool = False
    max_tokens: int = 4096


@dataclass
class MCPSettings:
    """MCP server settings."""

    servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    enabled: bool = True


@dataclass
class Settings:
    """Application settings."""

    verbose: bool = False
    theme: str = "default"
    auto_compact: bool = True
    model: ModelSettings = field(default_factory=ModelSettings)
    mcp: MCPSettings = field(default_factory=MCPSettings)
    allowed_tools: list[str] = field(default_factory=list)


@dataclass
class AppState:
    """Full application state."""

    # Basic settings
    settings: Settings = field(default_factory=Settings)

    # Working directory
    cwd: str = field(default_factory=lambda: str(Path.cwd()))

    # Session info
    session_id: str | None = None
    session_name: str | None = None

    # UI state
    status_line: str | None = None
    verbose: bool = False

    # Permission context
    tool_permission_context: ToolPermissionContext = field(default_factory=ToolPermissionContext)

    # MCP state
    mcp_clients: list[Any] = field(default_factory=list)
    mcp_tools: list[Any] = field(default_factory=list)
    mcp_commands: list[Any] = field(default_factory=list)

    # Messages
    messages: list[Any] = field(default_factory=list)

    # Tasks
    tasks: dict[str, Any] = field(default_factory=dict)

    # Cost tracking
    total_cost_usd: float = 0.0
    total_tokens: int = 0

    # FileEdit compensation lifetime stats (cross-query persistence)
    fileedit_stats: dict[str, Any] = field(default_factory=dict)

    # Version
    version: str = "0.1.0"


def get_default_app_state() -> AppState:
    """Get default application state."""
    return AppState()


def create_store(initial_state: AppState | None = None) -> "Store":
    """Create a state store."""
    from .store import Store

    return Store(initial_state or get_default_app_state())
