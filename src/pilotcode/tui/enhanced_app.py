"""Enhanced TUI app for PilotCode with three-layer layout.

Layout structure (from design doc):
- Layer 1: AI Output Area (70% height) - message bubbles, code highlighting, tool results
- Layer 2: Input Area (fixed height, resizable) - multi-line input, toolbar, send/stop buttons
- Layer 3: Status Bar (~40px height) - model info, token usage, quick commands
"""

from __future__ import annotations

import asyncio
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal, Container
from textual.widgets import (
    Static, Button, Label, 
    RichLog, Markdown, ProgressBar,
)
from .unicode_input import UnicodeTextArea
from textual.reactive import reactive
from textual.binding import Binding
from rich.text import Text
from rich.panel import Panel
from rich.syntax import Syntax
from rich.console import Group

from ..tools.registry import get_all_tools
from ..commands.base import process_user_input, CommandContext
from ..query_engine import QueryEngine, QueryEngineConfig
from ..state.app_state import get_default_app_state
from ..state.store import Store, set_global_store
from ..types.message import AssistantMessage
from ..permissions import get_tool_executor
from ..permissions.permission_manager import (
    PermissionRequest,
    PermissionLevel as PL,
    get_permission_manager,
)
from .screens import PermissionModal
from .message_renderer import MessageRenderer, Message, MessageType as RenderMessageType


class TokenUsageBar(Static):
    """Token usage progress bar with color coding."""
    
    DEFAULT_CSS = """
    TokenUsageBar {
        width: 25;
        height: 1;
        content-align: center middle;
    }
    """
    
    current_tokens = reactive(0)
    max_tokens = reactive(262100)
    
    def watch_current_tokens(self, value: int) -> None:
        self.update_display()
    
    def watch_max_tokens(self, value: int) -> None:
        self.update_display()
    
    def update_display(self) -> None:
        """Update the display."""
        percentage = (self.current_tokens / self.max_tokens) * 100 if self.max_tokens > 0 else 0
        
        # Color coding: green < 50%, yellow < 80%, red > 90%
        if percentage < 50:
            color = "green"
            bar_char = "█"
        elif percentage < 80:
            color = "yellow"
            bar_char = "▓"
        else:
            color = "red"
            bar_char = "▒"
        
        # Create mini progress bar
        filled = int(percentage / 10)
        bar = bar_char * filled + "░" * (10 - filled)
        
        text = Text()
        text.append(f"{bar} ", style=color)
        text.append(f"{self.current_tokens/1000:.1f}k", style="white")
        text.append(f"/{self.max_tokens/1000:.1f}k", style="dim")
        
        self.update(text)
    
    def set_usage(self, current: int, max_tokens: int) -> None:
        """Set token usage."""
        self.current_tokens = current
        self.max_tokens = max_tokens


class StatusBarWidget(Static):
    """Status bar with model info, token usage, and tips."""
    
    DEFAULT_CSS = """
    StatusBarWidget {
        height: 1;
        background: $surface-darken-1;
        color: $text-muted;
        padding: 0 1;
    }
    """
    
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_name = "PilotCode 0.2"
        self.connected = True
        self.token_usage = (0, 262100)
        self.tips = "/help: help | /theme: switch theme"
    
    def compose(self) -> ComposeResult:
        with Horizontal():
            # Left: Model info with status indicator
            yield Static(self._render_model(), id="status-model")
            
            # Center: Token usage
            yield TokenUsageBar(id="status-tokens")
            
            # Right: Tips
            yield Static(self.tips, id="status-tips")
    
    def _render_model(self) -> Text:
        """Render model info with connection status."""
        text = Text()
        # Green dot for connected, red for disconnected
        status_color = "green" if self.connected else "red"
        text.append("● ", style=status_color)
        text.append(self.model_name, style="cyan")
        return text
    
    def set_model(self, name: str, connected: bool = True) -> None:
        """Update model info."""
        self.model_name = name
        self.connected = connected
        model_widget = self.query_one("#status-model", Static)
        model_widget.update(self._render_model())
    
    def set_token_usage(self, current: int, max_tokens: int) -> None:
        """Update token usage."""
        token_bar = self.query_one("#status-tokens", TokenUsageBar)
        token_bar.set_usage(current, max_tokens)


class InputArea(Container):
    """Input area with multi-line support and toolbar."""
    
    DEFAULT_CSS = """
    InputArea {
        height: auto;
        max-height: 5;
        border-top: solid $primary-lighten-2;
        padding: 0 1;
    }
    
    #input-toolbar {
        height: 1;
        dock: bottom;
    }
    
    #input-textarea {
        height: 3;
        border: solid $primary;
    }
    
    #input-send-btn {
        width: 8;
    }
    """
    
    is_generating = reactive(False)
    
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._on_submit = None
        self._on_stop = None
    
    def compose(self) -> ComposeResult:
        with Horizontal():
            # Multi-line input
            yield UnicodeTextArea(
                placeholder="Type your message here...\nShift+Enter for new line",
                id="input-textarea",
                show_line_numbers=False,
            )
            
            # Send/Stop button
            yield Button("Send", id="input-send-btn", variant="primary")
        
        # Toolbar
        with Horizontal(id="input-toolbar"):
            yield Button("📎 Attach", id="btn-attach", variant="default")
            yield Button("🤖 Model", id="btn-model", variant="default")
            yield Static("", classes="spacer")
            yield Label("Shift+Enter: newline | Enter: send")
    
    def on_mount(self) -> None:
        textarea = self.query_one("#input-textarea", UnicodeTextArea)
        textarea.focus()
    
    def watch_is_generating(self, generating: bool) -> None:
        """Update UI based on generation state."""
        btn = self.query_one("#input-send-btn", Button)
        if generating:
            btn.label = "Stop"
            btn.variant = "error"
        else:
            btn.label = "Send"
            btn.variant = "primary"
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id
        
        if button_id == "input-send-btn":
            if self.is_generating:
                if self._on_stop:
                    self._on_stop()
            else:
                self._submit_input()
        elif button_id == "btn-attach":
            # TODO: Implement file attachment
            pass
        elif button_id == "btn-model":
            # TODO: Implement model selection
            pass
    
    def _submit_input(self) -> None:
        """Submit input."""
        textarea = self.query_one("#input-textarea", UnicodeTextArea)
        text = textarea.text.strip()
        if text and self._on_submit:
            self._on_submit(text)
            textarea.text = ""
    
    def set_callbacks(self, on_submit=None, on_stop=None) -> None:
        """Set callbacks."""
        self._on_submit = on_submit
        self._on_stop = on_stop
    
    def set_generating(self, generating: bool) -> None:
        """Set generation state."""
        self.is_generating = generating


class ToolExecutionWidget(Static):
    """Widget for displaying tool execution status and results."""
    
    DEFAULT_CSS = """
    ToolExecutionWidget {
        height: auto;
        max-height: 10;
        margin: 1 0;
        padding: 0 1;
    }
    """
    
    def __init__(self, tool_name: str, tool_input: dict, **kwargs) -> None:
        super().__init__(**kwargs)
        self.tool_name = tool_name
        self.tool_input = tool_input
        self.result = None
        self.success = None
        self.expanded = False
    
    def compose(self) -> ComposeResult:
        self._render_pending()
    
    def _render_pending(self) -> None:
        """Render pending tool execution."""
        text = Text()
        text.append("🔧 ", style="yellow")
        text.append(f"Using ", style="dim")
        text.append(self.tool_name, style="cyan bold")
        text.append("...", style="dim")
        self.update(Panel(text, border_style="yellow"))
    
    def set_result(self, result: str, success: bool) -> None:
        """Set execution result."""
        self.result = result
        self.success = success
        self._render_result()
    
    def _render_result(self) -> None:
        """Render tool result."""
        text = Text()
        
        if self.success:
            text.append("✓ ", style="green")
            text.append(f"{self.tool_name}", style="cyan")
            text.append(" succeeded", style="green")
        else:
            text.append("✗ ", style="red")
            text.append(f"{self.tool_name}", style="cyan")
            text.append(" failed", style="red")
        
        # Truncate result if too long
        result_text = self.result
        if len(result_text) > 500:
            result_text = result_text[:500] + "\n... [truncated]"
        
        content = Group(text, Text(result_text, style="dim"))
        border_color = "green" if self.success else "red"
        self.update(Panel(content, border_style=border_color))


class MessageBubble(Static):
    """Message bubble for chat display."""
    
    DEFAULT_CSS = """
    MessageBubble {
        height: auto;
        margin: 1 0;
        padding: 0 1;
    }
    """
    
    def __init__(self, role: str, content: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.role = role
        self.content = content
        self.renderer = MessageRenderer()
    
    def on_mount(self) -> None:
        """Render message on mount."""
        # Convert role to MessageType
        role_map = {
            "user": RenderMessageType.USER,
            "assistant": RenderMessageType.ASSISTANT,
            "system": RenderMessageType.SYSTEM,
            "tool_use": RenderMessageType.TOOL_USE,
            "tool_result": RenderMessageType.TOOL_RESULT,
        }
        msg_type = role_map.get(self.role, RenderMessageType.SYSTEM)
        
        msg = Message(role=msg_type, content=self.content)
        panel = self.renderer.render(msg)
        
        self.update(panel)


class PilotCodeTUI(App):
    """Enhanced PilotCode TUI with three-layer layout."""
    
    CSS = """
    Screen {
        layout: vertical;
    }
    
    #output-area {
        height: 1fr;
        min-height: 10;
        overflow-y: auto;
        border: solid $primary;
        padding: 0 1;
    }
    
    #input-area {
        height: auto;
        max-height: 6;
        dock: bottom;
    }
    
    #status-bar {
        height: 1;
        dock: bottom;
    }
    """
    
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear", "Clear"),
        Binding("escape", "cancel", "Cancel"),
    ]
    
    def __init__(self, store: Store | None = None, tools: list | None = None, auto_allow: bool = False) -> None:
        self.auto_allow = auto_allow
        self._provided_store = store
        self._provided_tools = tools
        self.store = None
        self.query_engine = None
        self.tool_executor = None
        self._current_generation = None
        super().__init__()
    
    def compose(self) -> ComposeResult:
        # Layer 1: Output Area (70% height via 1fr)
        with Vertical(id="output-area"):
            pass
        
        # Layer 2: Input Area
        yield InputArea(id="input-area")
        
        # Layer 3: Status Bar
        yield StatusBarWidget(id="status-bar")
    
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
            self.add_system_message("⚡ Auto-allow mode enabled — all tool executions will be allowed")
        else:
            pm.set_permission_callback(self._permission_callback)
        
        # Setup input callbacks
        input_area = self.query_one("#input-area", InputArea)
        input_area.set_callbacks(
            on_submit=self._on_input_submit,
            on_stop=self._on_stop_generation
        )
        
        # Add welcome message
        self.add_welcome_message()
        
        # Update token display
        self._update_token_display()
    
    async def _permission_callback(self, request: PermissionRequest) -> PL:
        """Handle permission request."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        
        def on_result(result: str) -> None:
            if not future.done():
                future.set_result(result)
        
        self.push_screen(PermissionModal(request), callback=on_result)
        result = await future
        
        choice_map = {
            "y": PL.ALLOW,
            "n": PL.DENY,
            "a": PL.ALLOW,
            "s": PL.ALWAYS_ALLOW,
            "d": PL.NEVER_ALLOW,
        }
        return choice_map.get(result, PL.DENY)
    
    def _on_input_submit(self, text: str) -> None:
        """Handle user input submission."""
        self.add_user_message(text)
        asyncio.create_task(self._process_input(text))
    
    def _on_stop_generation(self) -> None:
        """Stop current generation."""
        if self._current_generation:
            self._current_generation.cancel()
            self._current_generation = None
        
        input_area = self.query_one("#input-area", InputArea)
        input_area.set_generating(False)
    
    async def _process_input(self, text: str) -> None:
        """Process user input."""
        input_area = self.query_one("#input-area", InputArea)
        input_area.set_generating(True)
        
        try:
            context = CommandContext(cwd=self.store.get_state().cwd)
            is_command, result = await process_user_input(text, context)
            
            if is_command:
                self.add_system_message(str(result))
            else:
                # TODO: Stream AI response
                self.add_assistant_message("Processing your request...")
        
        except Exception as e:
            self.add_error_message(str(e))
        
        finally:
            input_area.set_generating(False)
            self._update_token_display()
    
    def _update_token_display(self) -> None:
        """Update token usage display."""
        if self.query_engine:
            token_count = self.query_engine.count_tokens()
            status_bar = self.query_one("#status-bar", StatusBarWidget)
            status_bar.set_token_usage(token_count, 262100)
    
    def add_welcome_message(self) -> None:
        """Add welcome message."""
        welcome_text = """[bold cyan]Welcome to PilotCode![/bold cyan] [dim]v0.2.0[/dim]

[cyan]Your AI Programming Assistant[/cyan]

[dim]Tips:[/dim]
• Type /help for available commands
• Use @ to reference files
• Shift+Enter for new line
"""
        self.add_assistant_message(welcome_text)
    
    def add_user_message(self, text: str) -> None:
        """Add user message."""
        self._add_message_bubble("user", text)
    
    def add_assistant_message(self, text: str) -> None:
        """Add assistant message."""
        self._add_message_bubble("assistant", text)
    
    def add_system_message(self, text: str) -> None:
        """Add system message."""
        self._add_message_bubble("system", text)
    
    def add_error_message(self, text: str) -> None:
        """Add error message."""
        self._add_message_bubble("error", text)
    
    def add_tool_use(self, tool_name: str, tool_input: dict) -> ToolExecutionWidget:
        """Add tool use widget."""
        output_area = self.query_one("#output-area", Vertical)
        widget = ToolExecutionWidget(tool_name, tool_input)
        output_area.mount(widget)
        output_area.scroll_end(animate=False)
        return widget
    
    def _add_message_bubble(self, role: str, content: str) -> None:
        """Add a message bubble."""
        output_area = self.query_one("#output-area", Vertical)
        bubble = MessageBubble(role, content)
        output_area.mount(bubble)
        output_area.scroll_end(animate=False)
    
    def action_clear(self) -> None:
        """Clear output area."""
        output_area = self.query_one("#output-area", Vertical)
        output_area.remove_children()
    
    def action_cancel(self) -> None:
        """Cancel current operation."""
        self._on_stop_generation()


# For backward compatibility
PilotCodeApp = PilotCodeTUI
