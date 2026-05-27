"""Tool registry for managing tools."""

import os
import sys
from typing import TYPE_CHECKING, Any
from .base import Tool, Tools
from ..types.permissions import ToolPermissionContext

if TYPE_CHECKING:
    pass


# Core tools always sent to the LLM (minimal set for maximum utility)
_CORE_TOOL_NAMES: set[str] = {
    "Bash",
    "FileRead",
    "FileEdit",
    "FileWrite",
    "ApplyPatch",
    "Glob",
    "Grep",
    "CodeSearch",
    "AskUser",
}

# Contextually-loaded tool groups
_CONTEXT_TOOL_GROUPS: dict[str, set[str]] = {
    "git": {"Git"},
    "notebook": {"NotebookEdit"},
    "web": {"WebSearch", "WebFetch"},
    "cron": {"Cron"},
    "task": {"Task"},
    "config": {"Config"},
    "agent": {"Agent"},
    "plan": {"PlanMode"},
    "mcp": {"MCP"},
    "worktree": {"Worktree"},
    "message": {"SendMessage", "ReceiveMessage"},
    "lsp": {"LSP"},
    "code_index": {"CodeIndex", "CodeContext"},
    "repl": {"REPL"},
    "skill": {"Skill"},
    "sleep": {"Sleep"},
    "todo": {"Todo"},
    "tool_search": {"ToolSearch"},
    "brief": {"Brief"},
    "smart_edit": {"SmartEditPlanner"},
    "synthetic": {"SyntheticOutput"},
    "remote": {"RemoteTrigger"},
    "browser": {"WebBrowser"},
    "ripgrep": {"Ripgrep"},
    "powershell": {"PowerShell"},
}


# Directories to skip during context detection (case-insensitive)
_SKIP_CONTEXT_DIRS = frozenset(
    {
        "node_modules",
        ".venv",
        "venv",
        "env",
        ".env",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".git",
        ".idea",
        ".vscode",
        ".vs",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "target",
        "bin",
        "obj",
    }
)


def _scan_for_notebooks(cwd: str, max_depth: int = 2) -> bool:
    """Scan for .ipynb files using os.scandir, skipping large directories.

    Returns True if any .ipynb file is found within max_depth levels.
    """
    try:
        with os.scandir(cwd) as it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False):
                    if entry.name.lower() in _SKIP_CONTEXT_DIRS:
                        continue
                    if max_depth > 0:
                        if _scan_for_notebooks(entry.path, max_depth - 1):
                            return True
                elif entry.name.endswith(".ipynb"):
                    return True
    except PermissionError:
        pass
    except OSError:
        pass
    return False


def _detect_context_groups(cwd: str) -> set[str]:
    """Detect which contextual tool groups are relevant for the current workspace."""
    groups: set[str] = set()
    cwd = os.path.abspath(cwd or ".")

    # Git repository
    if os.path.isdir(os.path.join(cwd, ".git")):
        groups.add("git")

    # Node.js / web project
    if os.path.exists(os.path.join(cwd, "package.json")):
        groups.add("web")

    # Jupyter notebooks — use fast os.scandir with skip-dir support
    if _scan_for_notebooks(cwd, max_depth=2):
        groups.add("notebook")

    # Python project (LSP, REPL useful)
    if os.path.exists(os.path.join(cwd, "pyproject.toml")) or os.path.exists(
        os.path.join(cwd, "setup.py")
    ):
        groups.add("lsp")
        groups.add("repl")

    # Large codebase (code indexing useful)
    try:
        dir_count = sum(
            1
            for entry in os.scandir(cwd)
            if entry.is_dir() and entry.name.lower() not in _SKIP_CONTEXT_DIRS
        )
    except Exception:
        dir_count = 0
    if dir_count >= 3:
        groups.add("code_index")

    # Always load some convenience tools
    groups.update({"todo", "config", "task", "sleep", "skill", "brief", "tool_search"})

    # Plan mode always available
    groups.add("plan")

    # MCP if configured (check for mcp_servers in config)
    try:
        from pilotcode.utils.config import get_global_config

        cfg = get_global_config()
        if getattr(cfg, "mcp_servers", None):
            groups.add("mcp")
    except Exception:
        pass

    # PowerShell only on Windows
    if sys.platform == "win32":
        groups.add("powershell")

    return groups


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

    def filter_by_permission(
        self,
        permission_context: ToolPermissionContext,
        permission_manager: Any | None = None,
    ) -> Tools:
        """Filter tools based on permission context.

        Removes tools from the model's view when the permission mode
        indicates they should not be invoked (e.g. 'dontAsk' mode hides
        Bash). This prevents the model from hallucinating disallowed tools.
        """
        all_tools = self.get_all()
        mode = permission_context.mode

        # Fast path: no filtering needed
        if mode in ("default", "acceptEdits", "bypassPermissions", "auto"):
            return all_tools

        # Use PermissionManager to check visibility
        if permission_manager is None:
            try:
                from ..permissions.permission_manager import get_permission_manager

                permission_manager = get_permission_manager()
            except Exception:
                return all_tools

        result: Tools = []
        for tool in all_tools:
            if permission_manager.is_tool_visible(tool.name, mode):
                result.append(tool)

        return result

    def get_core_tools(self, cwd: str = ".") -> Tools:
        """Return core + contextually-relevant tools for the given directory.

        Instead of sending all 50+ tools on every turn, we send ~12 core tools
        plus groups that are actually useful for the current workspace (e.g. Git
        tools only when inside a git repo, NotebookEdit only when .ipynb files
        exist, etc.).
        """
        all_tools = self.get_all()
        name_map = {t.name: t for t in all_tools}

        # Start with core tools
        selected_names = set(_CORE_TOOL_NAMES)

        # Add contextually-relevant groups
        context_groups = _detect_context_groups(cwd)
        for group in context_groups:
            selected_names.update(_CONTEXT_TOOL_GROUPS.get(group, set()))

        # Build ordered list: core first, then extras
        result: Tools = []
        for name in _CORE_TOOL_NAMES:
            if name in name_map:
                result.append(name_map[name])
        for group in context_groups:
            for name in _CONTEXT_TOOL_GROUPS.get(group, set()):
                if name in name_map and name not in _CORE_TOOL_NAMES:
                    result.append(name_map[name])

        return result


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


def get_core_tools(cwd: str = ".") -> Tools:
    """Get core + contextually-relevant tools for the given directory."""
    return get_tool_registry().get_core_tools(cwd)


def assemble_tool_pool(
    permission_context: ToolPermissionContext,
    mcp_tools: Tools | None = None,
    cwd: str = ".",
    use_core_only: bool = True,
) -> Tools:
    """Assemble tool pool from built-in and MCP tools.

    Args:
        permission_context: Permission context for filtering.
        mcp_tools: Optional list of MCP tools.
        cwd: Current working directory for context detection.
        use_core_only: If True, only send core + context tools (~15-25)
            instead of all registered tools (~50+).
    """
    registry = get_tool_registry()

    # Get built-in tools (core or all)
    if use_core_only:
        built_in_tools = registry.get_core_tools(cwd)
    else:
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
