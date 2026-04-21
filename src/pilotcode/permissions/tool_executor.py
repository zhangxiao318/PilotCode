"""Safe tool executor with permission checking."""

import asyncio
from typing import Any, Callable
from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .permission_manager import (
    get_permission_manager,
    PermissionRequest,
    PermissionLevel,
)
from ..tools.base import Tool, ToolUseContext, ToolResult
from ..tools.registry import get_all_tools


async def _default_allow_callback(*args, **kwargs) -> dict:
    return {"behavior": "allow"}


@dataclass
class ToolExecutionResult:
    """Result of tool execution with metadata."""

    success: bool
    result: ToolResult | None
    permission_granted: bool
    message: str
    tool_name: str


class ToolExecutor:
    """Executes tools with permission checking and user interaction."""

    def __init__(self, console: Console | None = None):
        self.console = console or Console()
        self.permission_manager = get_permission_manager()

    def _format_permission_request(self, request: PermissionRequest) -> Panel:
        """Format permission request for display."""
        risk_colors = {"low": "green", "medium": "yellow", "high": "orange", "critical": "red"}
        color = risk_colors.get(request.risk_level, "yellow")

        content = Text()
        content.append("Tool: ", style="bold")
        content.append(f"{request.tool_name}\n", style="cyan")
        content.append("Risk: ", style="bold")
        content.append(f"{request.risk_level.upper()}\n", style=f"bold {color}")

        content.append("\nDetails:\n", style="bold")
        for key, value in request.tool_input.items():
            content.append(f"  {key}: ", style="dim")
            if isinstance(value, str) and len(value) > 100:
                content.append(f"{value[:100]}...\n", style="white")
            else:
                content.append(f"{value}\n", style="white")

        return Panel(
            content,
            title=f"[bold {color}]⚠️  Permission Required[/bold {color}]",
            border_style=color,
            padding=(1, 2),
        )

    def _sync_permission_prompt(self, request: PermissionRequest) -> str:
        """Synchronous permission prompt - runs in executor."""
        self.console.print()
        self.console.print(self._format_permission_request(request))

        self.console.print("\n[bold]Options:[/bold]")
        self.console.print("  [y] Yes - Allow this once")
        self.console.print("  [n] No - Deny this once")
        self.console.print("  [a] Always - Allow for this session")
        self.console.print("  [s] Session - Always allow this specific action")
        self.console.print("  [d] Don't ask again - Never allow this")

        while True:
            try:
                # Use standard input() wrapped in executor for async compatibility
                choice = input("\nChoice [y/n/a/s/d]: ").strip().lower()

                if choice in ("y", "yes", ""):
                    return "y"
                elif choice in ("n", "no"):
                    return "n"
                elif choice == "a":
                    return "a"
                elif choice == "s":
                    return "s"
                elif choice == "d":
                    return "d"
                else:
                    self.console.print(
                        "[yellow]Invalid choice. Please enter y, n, a, s, or d.[/yellow]"
                    )
            except (KeyboardInterrupt, EOFError):
                return "n"

    async def _interactive_permission_prompt(self, request: PermissionRequest) -> PermissionLevel:
        """Show interactive permission prompt and get user choice."""
        # Run synchronous input in executor to avoid blocking event loop
        loop = asyncio.get_event_loop()
        choice = await loop.run_in_executor(None, self._sync_permission_prompt, request)

        # Map choice to permission level
        choice_map = {
            "y": PermissionLevel.ALLOW,
            "n": PermissionLevel.DENY,
            "a": PermissionLevel.ALLOW,
            "s": PermissionLevel.ALWAYS_ALLOW,
            "d": PermissionLevel.NEVER_ALLOW,
        }
        return choice_map.get(choice, PermissionLevel.DENY)

    def _normalize_tool_input(self, tool_name: str, tool_input: dict) -> dict:
        """Normalize tool input field names to match Pydantic models."""
        normalized = tool_input.copy()

        # FileWrite/FileRead/FileEdit: map 'path' to 'file_path'
        if tool_name in ("FileWrite", "FileRead", "FileEdit"):
            if "path" in normalized and "file_path" not in normalized:
                normalized["file_path"] = normalized.pop("path")

        return normalized

    async def execute_tool(
        self,
        tool: Tool,
        tool_input: dict,
        context: ToolUseContext,
        can_use_tool_callback: Callable | None = None,
        on_progress: Callable[[Any], None] | None = None,
    ) -> ToolExecutionResult:
        """Execute a tool with permission checking."""
        tool_name = tool.name

        # Normalize field names (handle LLM using different field names)
        tool_input = self._normalize_tool_input(tool_name, tool_input)

        # Check if permission is already granted
        is_permitted, reason = self.permission_manager.check_permission(tool_name, tool_input)

        if not is_permitted:
            # Need to ask for permission
            # Only set default callback if no custom callback is already set
            if self.permission_manager._permission_callback is None:
                self.permission_manager.set_permission_callback(self._interactive_permission_prompt)
                print(f"[ToolExecutor] Using default permission prompt")
            else:
                print(f"[ToolExecutor] Using custom permission callback")

            is_granted, level = await self.permission_manager.request_permission(
                tool_name, tool_input
            )

            if not is_granted:
                return ToolExecutionResult(
                    success=False,
                    result=None,
                    permission_granted=False,
                    message=f"Permission denied by user ({level.value})",
                    tool_name=tool_name,
                )

        # Permission granted, execute the tool
        try:
            self.console.print(f"[dim][T] Executing {tool_name}...[/dim]")

            # Validate input if validation function exists
            if tool.validate_input:
                input_valid, validation_error = await tool.validate_input(
                    tool.input_schema(**tool_input), context
                )
                if not input_valid:
                    return ToolExecutionResult(
                        success=False,
                        result=None,
                        permission_granted=True,
                        message=f"Validation failed: {validation_error}",
                        tool_name=tool_name,
                    )

            # Parse input through schema
            try:
                parsed_input = tool.input_schema(**tool_input)
            except Exception as e:
                return ToolExecutionResult(
                    success=False,
                    result=None,
                    permission_granted=True,
                    message=f"Invalid input: {str(e)}",
                    tool_name=tool_name,
                )

            result = await tool.call(
                parsed_input,
                context,
                can_use_tool_callback or _default_allow_callback,
                None,
                on_progress or (lambda x: None),
            )

            if result.is_error:
                return ToolExecutionResult(
                    success=False,
                    result=result,
                    permission_granted=True,
                    message=f"Tool execution failed: {result.error}",
                    tool_name=tool_name,
                )

            return ToolExecutionResult(
                success=True,
                result=result,
                permission_granted=True,
                message="Success",
                tool_name=tool_name,
            )

        except Exception as e:
            return ToolExecutionResult(
                success=False,
                result=None,
                permission_granted=True,
                message=f"Exception: {str(e)}",
                tool_name=tool_name,
            )

    async def execute_tool_by_name(
        self,
        tool_name: str,
        tool_input: dict,
        context: ToolUseContext,
        on_progress: Callable[[Any], None] | None = None,
    ) -> ToolExecutionResult:
        """Execute a tool by name with permission checking."""
        all_tools = get_all_tools()
        tool = None
        for t in all_tools:
            if t.name == tool_name or tool_name in t.aliases:
                tool = t
                break

        if tool is None:
            return ToolExecutionResult(
                success=False,
                result=None,
                permission_granted=False,
                message=f"Tool '{tool_name}' not found",
                tool_name=tool_name,
            )

        return await self.execute_tool(tool, tool_input, context, on_progress=on_progress)


# Global instance
_tool_executor: ToolExecutor | None = None


def get_tool_executor(console: Console | None = None) -> ToolExecutor:
    """Get global tool executor."""
    global _tool_executor
    if _tool_executor is None:
        _tool_executor = ToolExecutor(console)
    return _tool_executor
