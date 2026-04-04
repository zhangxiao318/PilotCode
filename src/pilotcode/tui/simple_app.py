"""Simple, clean TUI for PilotCode - Claude Code style.

Design principles:
- Use terminal's default background (for Xshell compatibility)
- Clean, minimal layout
- Proper Rich rendering
- Simple input at bottom
"""

from __future__ import annotations

import asyncio
from typing import Any
import signal

from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Input, Static, RichLog
from textual.reactive import reactive
from textual.binding import Binding
from rich.text import Text
from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax

from ..tools.registry import get_all_tools
from ..tools.base import ToolUseContext
from ..commands.base import process_user_input, CommandContext
from ..query_engine import QueryEngine, QueryEngineConfig
from ..state.app_state import get_default_app_state
from ..state.store import Store, set_global_store
from ..permissions import get_tool_executor
from ..permissions.permission_manager import (
    PermissionRequest,
    PermissionLevel as PL,
    get_permission_manager,
)
from ..types.message import AssistantMessage, ToolUseMessage
from .screens import PermissionModal
from .message_renderer import MessageRenderer, Message, MessageType as RenderMessageType


class SimpleTUI(App):
    """Simple, clean TUI using terminal default colors for Xshell compatibility."""
    
    # Use terminal's default background (no explicit background color)
    # This ensures Xshell uses its own configured background
    CSS = """
    Screen {
        layout: vertical;
    }
    
    #main-container {
        width: 100%;
        height: 100%;
    }
    
    #messages {
        height: 1fr;
        width: 100%;
        border: none;
        padding: 0 1;
    }
    
    #input-area {
        height: auto;
        width: 100%;
        border-top: solid $primary-darken-2;
        padding: 0 1;
    }
    
    #user-input {
        width: 100%;
        height: 1;
        border: none;
        padding: 0;
    }
    
    #user-input:focus {
        border: none;
    }
    
    #status-bar {
        height: 1;
        width: 100%;
        color: $text-muted;
        padding: 0 1;
        border: none;
    }
    
    /* Ensure RichLog uses terminal default */
    RichLog {
        border: none;
    }
    
    /* Input widget */
    Input {
        border: none;
        padding: 0;
    }
    
    Input:focus {
        border: none;
    }
    
    /* Remove any explicit backgrounds */
    Static {
        border: none;
    }
    """
    
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear", "Clear"),
    ]
    
    def __init__(self, store: Store | None = None, tools: list | None = None, auto_allow: bool = False):
        self._provided_store = store
        self._provided_tools = tools
        self.auto_allow = auto_allow
        self.store = None
        self.query_engine = None
        self.tool_executor = None
        self.renderer = MessageRenderer()
        super().__init__()
    
    def compose(self) -> ComposeResult:
        with Vertical(id="main-container"):
            # Messages area
            yield RichLog(id="messages", highlight=True, markup=True)
            
            # Input area
            with Horizontal(id="input-area"):
                yield Input(placeholder="Type a message...", id="user-input")
            
            # Status bar
            yield Static("Ready — Type /help for commands", id="status-bar")
    
    async def on_mount(self) -> None:
        """Initialize application."""
        # State
        if self._provided_store is not None:
            self.store = self._provided_store
        else:
            self.store = Store(get_default_app_state())
        set_global_store(self.store)
        
        # Query engine
        tools = self._provided_tools if self._provided_tools is not None else get_all_tools()
        self.query_engine = QueryEngine(QueryEngineConfig(
            cwd=self.store.get_state().cwd,
            tools=tools,
            get_app_state=self.store.get_state,
            set_app_state=lambda f: self.store.set_state(f)
        ))
        
        # Tool executor
        self.tool_executor = get_tool_executor()
        
        # Setup permissions
        pm = get_permission_manager()
        if self.auto_allow:
            from ..permissions.permission_manager import ToolPermission
            for tool in tools:
                pm._permissions[tool.name] = ToolPermission(
                    tool_name=tool.name,
                    level=PL.ALWAYS_ALLOW
                )
            self.add_system_message("Auto-allow mode enabled — all tool executions will be allowed")
        else:
            pm.set_permission_callback(self._permission_callback)
        
        # Show welcome
        self._show_welcome()
        
        # Focus input
        self.query_one("#user-input", Input).focus()
    
    def _show_welcome(self) -> None:
        """Show welcome message."""
        messages = self.query_one("#messages", RichLog)
        
        welcome = Text()
        welcome.append("PilotCode ", style="bold cyan")
        welcome.append("v0.2.0\n", style="dim")
        welcome.append("Your AI Programming Assistant\n\n", style="cyan")
        welcome.append("Tips:\n", style="dim")
        welcome.append("  • Type ", style="dim")
        welcome.append("/help", style="cyan")
        welcome.append(" for available commands\n", style="dim")
        welcome.append("  • Use ", style="dim")
        welcome.append("@", style="cyan")
        welcome.append(" to reference files\n", style="dim")
        welcome.append("  • Press ", style="dim")
        welcome.append("Ctrl+C", style="cyan")
        welcome.append(" to quit\n", style="dim")
        
        messages.write(welcome)
        messages.write("")
    
    def add_user_message(self, content: str) -> None:
        """Add user message."""
        messages = self.query_one("#messages", RichLog)
        
        text = Text()
        text.append("You ", style="bold blue")
        text.append("› ", style="dim")
        text.append(content)
        
        messages.write(text)
        messages.write("")
    
    def add_system_message(self, content: str) -> None:
        """Add system message."""
        messages = self.query_one("#messages", RichLog)
        
        text = Text()
        text.append("ℹ ", style="dim")
        text.append(content, style="dim")
        
        messages.write(text)
        messages.write("")
    
    def add_assistant_message(self, content: str) -> None:
        """Add assistant message."""
        messages = self.query_one("#messages", RichLog)
        
        msg = Message(role=RenderMessageType.ASSISTANT, content=content)
        panel = self.renderer.render(msg)
        
        messages.write(panel)
        messages.write("")
    
    def add_tool_use(self, tool_name: str, tool_input: dict) -> None:
        """Add tool use message."""
        messages = self.query_one("#messages", RichLog)
        
        text = Text()
        text.append("  ▶ ", style="dim yellow")
        text.append(f"{tool_name}", style="yellow")
        
        if tool_input:
            params = list(tool_input.keys())
            if params:
                text.append(f" ({', '.join(params)})", style="dim")
        
        messages.write(text)
    
    def add_tool_result(self, content: str, success: bool = True) -> None:
        """Add tool result."""
        messages = self.query_one("#messages", RichLog)
        
        icon = "✓" if success else "✗"
        color = "green" if success else "red"
        
        text = Text()
        text.append(f"  {icon} ", style=color)
        
        lines = content.strip().split('\n')
        if len(lines) > 3 or len(content) > 200:
            preview = '\n'.join(lines[:3])[:200]
            text.append(f"{preview}...", style="dim")
        else:
            text.append(content, style="dim")
        
        messages.write(text)
        messages.write("")
    
    def update_status(self, text: str) -> None:
        """Update status bar."""
        status = self.query_one("#status-bar", Static)
        status.update(Text(text, style="dim cyan"))
    
    async def _permission_callback(self, request: PermissionRequest) -> PL:
        """Handle permission request."""
        # Show permission request in message area for visibility
        self.add_system_message(f"Permission request: {request.tool_name} - Press y/n/a/s/d")
        
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        
        def on_result(result: str) -> None:
            if not future.done():
                future.set_result(result)
        
        # Push the modal screen
        self.push_screen(PermissionModal(request), callback=on_result)
        
        # Wait for result
        result = await future
        
        choice_map = {
            "y": PL.ALLOW,
            "n": PL.DENY,
            "a": PL.ALLOW,
            "s": PL.ALWAYS_ALLOW,
            "d": PL.NEVER_ALLOW,
        }
        return choice_map.get(result, PL.DENY)
    
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user input."""
        input_widget = self.query_one("#user-input", Input)
        text = event.value.strip()
        
        if not text:
            return
        
        input_widget.value = ""
        input_widget.disabled = True
        self.update_status("Thinking...")
        
        # Check for commands
        if text.startswith('/'):
            context = CommandContext(cwd=self.store.get_state().cwd)
            is_command, result = await process_user_input(text, context)
            if is_command:
                self.add_system_message(result if isinstance(result, str) else str(result))
                input_widget.disabled = False
                input_widget.focus()
                self.update_status("Ready")
                return
        
        # Add user message
        self.add_user_message(text)
        
        # Process through query engine
        await self._run_llm_turn(text)
        
        input_widget.disabled = False
        input_widget.focus()
        self.update_status("Ready")
    
    async def _run_llm_turn(self, prompt: str) -> None:
        """Run one LLM turn with tool support."""
        max_iterations = 10
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            pending_tools = []
            full_content = ""
            
            try:
                async for result in self.query_engine.submit_message(prompt):
                    msg = result.message
                    if isinstance(msg, AssistantMessage) and msg.content:
                        if result.is_complete:
                            full_content = msg.content
                            self.add_assistant_message(full_content)
                        else:
                            # Streaming update - just accumulate
                            full_content += msg.content
                    elif isinstance(msg, ToolUseMessage):
                        pending_tools.append(msg)
            except Exception as e:
                self.add_system_message(f"Error: {e}")
                return
            
            if not pending_tools:
                break
            
            # Execute pending tools
            for tool_msg in pending_tools:
                self.add_tool_use(tool_msg.name, tool_msg.input)
                self.update_status(f"Executing {tool_msg.name}...")
                
                ctx = ToolUseContext(
                    get_app_state=self.store.get_state,
                    set_app_state=lambda f: self.store.set_state(f)
                )
                
                try:
                    # Use execute_tool_by_name which handles tool lookup
                    result = await self.tool_executor.execute_tool_by_name(
                        tool_msg.name, 
                        tool_msg.input, 
                        ctx
                    )
                    success = result.success
                    content = result.message or str(result.result)
                    self.add_tool_result(content, success)
                except Exception as e:
                    self.add_tool_result(f"Error: {e}", success=False)
            
            # Continue loop for next LLM response
            prompt = "Please continue based on the tool results."
    
    def action_clear(self) -> None:
        """Clear messages."""
        messages = self.query_one("#messages", RichLog)
        messages.clear()
        self._show_welcome()


def run_simple_tui(store: Store | None = None, tools: list | None = None, auto_allow: bool = False) -> None:
    """Run the simple TUI."""
    app = SimpleTUI(store=store, tools=tools, auto_allow=auto_allow)
    app.run()
