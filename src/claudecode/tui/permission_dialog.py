"""Permission dialogs for tool execution."""

from enum import Enum
from dataclasses import dataclass
from typing import Callable

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.layout import Layout
from rich.align import Align
from prompt_toolkit import prompt
from prompt_toolkit.styles import Style


class PermissionType(Enum):
    """Types of permission requests."""
    BASH = "bash"
    FILE_WRITE = "file_write"
    FILE_EDIT = "file_edit"
    FILE_DELETE = "file_delete"
    MCP = "mcp"
    SKILL = "skill"
    CONFIG = "config"


class PermissionResult(Enum):
    """Result of permission request."""
    ALLOW = "allow"
    DENY = "deny"
    ALWAYS_ALLOW = "always_allow"  # Allow and remember
    VIEW = "view"  # View more details


@dataclass
class PermissionRequest:
    """Permission request details."""
    permission_type: PermissionType
    title: str
    description: str
    details: dict
    tool_name: str
    tool_input: dict


class PermissionDialog:
    """Interactive permission dialog."""
    
    def __init__(self, console: Console | None = None):
        self.console = console or Console()
        self._always_allow: set[str] = set()
        self._deny_patterns: list[str] = []
    
    def _format_bash_details(self, details: dict) -> str:
        """Format bash command details."""
        command = details.get("command", "")
        timeout = details.get("timeout", 60)
        description = details.get("description", "")
        
        text = Text()
        text.append("Command: ", style="bold cyan")
        text.append(f"{command}\n", style="yellow")
        
        if description:
            text.append("Description: ", style="bold")
            text.append(f"{description}\n")
        
        text.append("Timeout: ", style="bold")
        text.append(f"{timeout}s")
        
        return text
    
    def _format_file_details(self, details: dict, operation: str) -> str:
        """Format file operation details."""
        path = details.get("path", "")
        
        text = Text()
        text.append(f"Operation: ", style="bold")
        text.append(f"{operation}\n", style="yellow")
        text.append("Path: ", style="bold cyan")
        text.append(f"{path}\n", style="green")
        
        if "content" in details and len(str(details["content"])) < 500:
            text.append("\nContent preview:\n", style="bold")
            content = str(details["content"])[:200]
            text.append(content, style="dim")
        
        return text
    
    def _format_edit_details(self, details: dict) -> str:
        """Format file edit details."""
        path = details.get("path", "")
        old_string = details.get("old_string", "")
        new_string = details.get("new_string", "")
        
        text = Text()
        text.append("File: ", style="bold cyan")
        text.append(f"{path}\n\n", style="green")
        
        text.append("─" * 40 + "\n", style="dim")
        text.append("OLD:\n", style="bold red")
        text.append(old_string[:200] + "\n" if len(old_string) > 200 else old_string + "\n", style="red")
        text.append("─" * 40 + "\n", style="dim")
        text.append("NEW:\n", style="bold green")
        text.append(new_string[:200] + "\n" if len(new_string) > 200 else new_string + "\n", style="green")
        text.append("─" * 40, style="dim")
        
        return text
    
    def _format_mcp_details(self, details: dict) -> str:
        """Format MCP tool details."""
        server = details.get("server", "")
        tool = details.get("tool", "")
        
        text = Text()
        text.append("MCP Server: ", style="bold cyan")
        text.append(f"{server}\n", style="green")
        text.append("Tool: ", style="bold cyan")
        text.append(f"{tool}\n", style="yellow")
        
        if "arguments" in details:
            text.append("\nArguments:\n", style="bold")
            import json
            args = json.dumps(details["arguments"], indent=2)
            text.append(args[:300], style="dim")
        
        return text
    
    def _render_request(self, request: PermissionRequest) -> Panel:
        """Render permission request panel."""
        # Format details based on type
        if request.permission_type == PermissionType.BASH:
            details_text = self._format_bash_details(request.details)
        elif request.permission_type == PermissionType.FILE_WRITE:
            details_text = self._format_file_details(request.details, "Write File")
        elif request.permission_type == PermissionType.FILE_EDIT:
            details_text = self._format_edit_details(request.details)
        elif request.permission_type == PermissionType.MCP:
            details_text = self._format_mcp_details(request.details)
        else:
            details_text = Text(str(request.details))
        
        # Build content
        content = Text()
        content.append(request.description + "\n\n", style="bold")
        content.append(details_text)
        
        # Determine color based on permission type
        colors = {
            PermissionType.BASH: "red",
            PermissionType.FILE_WRITE: "yellow",
            PermissionType.FILE_EDIT: "blue",
            PermissionType.FILE_DELETE: "red",
            PermissionType.MCP: "magenta",
            PermissionType.SKILL: "green",
            PermissionType.CONFIG: "cyan",
        }
        border_color = colors.get(request.permission_type, "white")
        
        return Panel(
            content,
            title=f"[bold]{request.title}[/bold]",
            border_style=border_color,
            padding=(1, 2),
        )
    
    def request_permission(
        self,
        request: PermissionRequest,
        timeout: int | None = None,
    ) -> PermissionResult:
        """Show permission dialog and get user response."""
        # Check always allow
        tool_key = f"{request.permission_type.value}:{request.tool_name}"
        if tool_key in self._always_allow:
            return PermissionResult.ALLOW
        
        # Render request
        panel = self._render_request(request)
        self.console.print(panel)
        
        # Show options
        self.console.print("\n[bold]Options:[/bold]")
        self.console.print("  [y] Allow once")
        self.console.print("  [n] Deny")
        self.console.print("  [a] Always allow")
        self.console.print("  [v] View more details")
        
        # Get user input
        style = Style.from_dict({
            'prompt': 'bold cyan',
        })
        
        while True:
            try:
                choice = prompt(
                    "\nChoice (y/n/a/v): ",
                    style=style,
                ).strip().lower()
                
                if choice in ('y', 'yes', ''):
                    return PermissionResult.ALLOW
                elif choice in ('n', 'no'):
                    return PermissionResult.DENY
                elif choice == 'a':
                    self._always_allow.add(tool_key)
                    return PermissionResult.ALWAYS_ALLOW
                elif choice == 'v':
                    self._show_details(request)
                    continue
                else:
                    self.console.print("[red]Invalid choice. Please try again.[/red]")
                    
            except KeyboardInterrupt:
                return PermissionResult.DENY
            except EOFError:
                return PermissionResult.DENY
    
    def _show_details(self, request: PermissionRequest):
        """Show detailed information."""
        import json
        
        self.console.print("\n[bold]Full Details:[/bold]")
        self.console.print(f"Tool: {request.tool_name}")
        self.console.print(f"Type: {request.permission_type.value}")
        self.console.print("\nInput:")
        self.console.print(json.dumps(request.tool_input, indent=2), style="dim")
    
    def quick_confirm(
        self,
        message: str,
        default: bool = False,
    ) -> bool:
        """Quick yes/no confirmation."""
        default_str = "Y/n" if default else "y/N"
        
        try:
            response = prompt(
                f"{message} [{default_str}]: ",
            ).strip().lower()
            
            if not response:
                return default
            return response in ('y', 'yes')
        except (KeyboardInterrupt, EOFError):
            return False


# Global dialog instance
_dialog: PermissionDialog | None = None


def get_permission_dialog() -> PermissionDialog:
    """Get global permission dialog."""
    global _dialog
    if _dialog is None:
        _dialog = PermissionDialog()
    return _dialog


def show_bash_permission(
    command: str,
    description: str | None = None,
    timeout: int = 60,
) -> PermissionResult:
    """Show bash permission dialog."""
    request = PermissionRequest(
        permission_type=PermissionType.BASH,
        title="⚠️  Bash Command Permission",
        description="The agent wants to execute a bash command:",
        details={
            "command": command,
            "description": description,
            "timeout": timeout,
        },
        tool_name="Bash",
        tool_input={"command": command, "timeout": timeout},
    )
    return get_permission_dialog().request_permission(request)


def show_file_write_permission(
    path: str,
    content: str | None = None,
) -> PermissionResult:
    """Show file write permission dialog."""
    request = PermissionRequest(
        permission_type=PermissionType.FILE_WRITE,
        title="📝 File Write Permission",
        description="The agent wants to write to a file:",
        details={"path": path, "content": content},
        tool_name="FileWrite",
        tool_input={"path": path, "content": content},
    )
    return get_permission_dialog().request_permission(request)


def show_file_edit_permission(
    path: str,
    old_string: str,
    new_string: str,
) -> PermissionResult:
    """Show file edit permission dialog."""
    request = PermissionRequest(
        permission_type=PermissionType.FILE_EDIT,
        title="✏️  File Edit Permission",
        description="The agent wants to edit a file:",
        details={"path": path, "old_string": old_string, "new_string": new_string},
        tool_name="FileEdit",
        tool_input={"path": path, "old_string": old_string, "new_string": new_string},
    )
    return get_permission_dialog().request_permission(request)


def show_mcp_permission(
    server: str,
    tool: str,
    arguments: dict,
) -> PermissionResult:
    """Show MCP permission dialog."""
    request = PermissionRequest(
        permission_type=PermissionType.MCP,
        title="🔌 MCP Tool Permission",
        description="The agent wants to use an MCP tool:",
        details={"server": server, "tool": tool, "arguments": arguments},
        tool_name=f"MCP:{server}:{tool}",
        tool_input={"server": server, "tool": tool, "arguments": arguments},
    )
    return get_permission_dialog().request_permission(request)
