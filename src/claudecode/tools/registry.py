"""Tool registry for managing tools."""

from typing import Any, TYPE_CHECKING
from .base import Tool, Tools, tool_matches_name
from ..types.permissions import ToolPermissionContext

if TYPE_CHECKING:
    pass


class ToolRegistry:
    """Registry for tools."""
    
    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._aliases: dict[str, str] = {}  # alias -> name
    
    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
        
        # Register aliases
        for alias in tool.aliases:
            self._aliases[alias] = tool.name
    
    def get(self, name: str) -> Tool | None:
        """Get tool by name or alias."""
        if name in self._tools:
            return self._tools[name]
        if name in self._aliases:
            return self._tools[self._aliases[name]]
        return None
    
    def get_all(self) -> Tools:
        """Get all registered tools."""
        return list(self._tools.values())
    
    def has_tool(self, name: str) -> bool:
        """Check if tool exists."""
        return name in self._tools or name in self._aliases
    
    def filter_by_permission(self, permission_context: ToolPermissionContext) -> Tools:
        """Filter tools based on permission context."""
        # TODO: Implement permission-based filtering
        return self.get_all()


# Global registry instance
_global_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """Get global tool registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry


def register_tool(tool: Tool) -> Tool:
    """Register a tool to the global registry."""
    registry = get_tool_registry()
    registry.register(tool)
    return tool


def get_all_tools() -> Tools:
    """Get all tools from global registry."""
    return get_tool_registry().get_all()


def get_tool_by_name(name: str) -> Tool | None:
    """Get tool by name from global registry."""
    return get_tool_registry().get(name)


def assemble_tool_pool(
    permission_context: ToolPermissionContext,
    mcp_tools: Tools | None = None
) -> Tools:
    """Assemble tool pool from built-in and MCP tools."""
    registry = get_tool_registry()
    
    # Get built-in tools
    built_in_tools = registry.filter_by_permission(permission_context)
    
    # Get MCP tools
    mcp_tools = mcp_tools or []
    
    # Filter MCP tools by deny rules
    # TODO: Implement filtering
    allowed_mcp_tools = mcp_tools
    
    # Merge tools, built-in takes precedence
    tool_map: dict[str, Tool] = {}
    for tool in allowed_mcp_tools:
        tool_map[tool.name] = tool
    for tool in built_in_tools:
        tool_map[tool.name] = tool
    
    return list(tool_map.values())
