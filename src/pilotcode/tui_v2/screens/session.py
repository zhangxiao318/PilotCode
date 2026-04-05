"""Main session screen for chat interface."""

import asyncio
from pathlib import Path
from textual.screen import Screen
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, Header, Footer
from textual.reactive import reactive

from pilotcode.tui_v2.controller.controller import TUIController, UIMessage, MessageType
from pilotcode.tui_v2.components.message.display import MessageList, MessageDisplay
from pilotcode.tui_v2.components.prompt.input import PromptWithMode
from pilotcode.tui_v2.components.status.bar import StatusBar
from pilotcode.tui_v2.components.dialog.permission import PermissionDialog, PermissionResult, PermissionAction
from pilotcode.tui_v2.providers.session import get_session_provider
from pilotcode.state.store import Store, get_store
from pilotcode.commands.base import process_user_input, get_command_registry
from pilotcode.types.command import CommandContext

# Import all commands to ensure they are registered
import pilotcode.commands


class SessionScreen(Screen):
    """Main chat session screen."""
    
    DEFAULT_CSS = """
    SessionScreen {
        layout: vertical;
    }
    SessionScreen Header {
        dock: top;
        height: 1;
        background: $surface;
        color: $text;
        text-style: bold;
    }
    SessionScreen Footer {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
    }
    SessionScreen #main-container {
        width: 100%;
        height: 1fr;
    }
    SessionScreen #message-area {
        width: 100%;
        height: 1fr;
        overflow: auto;
        background: $background;
        color: $text;
    }
    SessionScreen #sidebar {
        width: 0;
        display: none;
    }
    SessionScreen.sidebar-visible #sidebar {
        width: 25;
        display: block;
        background: $surface;
        border-right: solid $border;
    }
    SessionScreen #sidebar-content {
        padding: 1;
    }
    SessionScreen #input-area {
        height: 4;
        dock: bottom;
        background: $surface;
        border-top: solid $border;
    }
    SessionScreen PromptInput {
        background: $surface;
        color: $text;
        border: none;
    }
    SessionScreen PromptInput:focus {
        border: none;
    }
    SessionScreen PromptInput .text-area--cursor {
        background: $primary;
    }
    """
    
    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+s", "save", "Save Session"),
        ("ctrl+l", "clear", "Clear"),
        ("f1", "help", "Help"),
        ("ctrl+b", "toggle_sidebar", "Toggle Sidebar"),
    ]
    
    sidebar_visible: reactive[bool] = reactive(False)
    
    def __init__(self, auto_allow: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.auto_allow = auto_allow
        self.controller: TUIController | None = None
        self.message_list: MessageList | None = None
        self.prompt: PromptWithMode | None = None
        self.status_bar: StatusBar | None = None
        self._processing = False
    
    def compose(self):
        """Compose the screen."""
        yield Header(show_clock=True)
        
        with Horizontal(id="main-container"):
            # Sidebar (hidden by default)
            with Vertical(id="sidebar"):
                yield Static("Sidebar", id="sidebar-content")
            
            # Main message area
            with Vertical(id="message-area"):
                self.message_list = MessageList()
                yield self.message_list
        
        # Input area
        with Vertical(id="input-area"):
            self.prompt = PromptWithMode()
            yield self.prompt
        
        self.status_bar = StatusBar()
        yield self.status_bar
        
        yield Footer()
    
    def on_mount(self):
        """Called when screen is mounted."""
        self._init_controller()
        self._show_welcome()
        
        # Focus prompt
        if self.prompt:
            self.prompt.prompt_input.focus()
    
    def _init_controller(self):
        """Initialize the controller."""
        store = get_store()
        
        self.controller = TUIController(
            get_app_state=store.get_state if store else None,
            set_app_state=lambda f: store.set_state(f) if store else None,
            auto_allow=self.auto_allow
        )
        
        # Set permission callback
        self.controller.set_permission_callback(self._request_permission)
    
    def _show_welcome(self):
        """Show welcome message in a boxed layout with two columns."""
        welcome_text = """┌────────────────────────────────────────────────────────┐
│  Welcome to PilotCode v0.2.0! 🚀                       │
│                                                        │
│  Commands              Tips                            │
│  ──────────────────────────────────────────────────────│
│  /help  - Show cmds    • @filename to ref files       │
│  /save  - Save session • Shift+Enter for new line     │
│  /load  - Load session • Up/Down for history          │
│  /clear - Clear history                                │
│  /quit  - Exit                                         │
└────────────────────────────────────────────────────────┘"""
        
        welcome_msg = UIMessage(
            type=MessageType.SYSTEM,
            content=welcome_text
        )
        if self.message_list:
            self.message_list.add_message(welcome_msg)
    
    async def on_prompt_with_mode_submitted(self, event: PromptWithMode.Submitted):
        """Handle input submission."""
        text = event.text.strip()
        if not text:
            return
        
        # Check for commands
        if text.startswith('/'):
            await self._handle_command(text)
            return
        
        # Show user message immediately for feedback
        if self.message_list:
            user_msg = UIMessage(
                type=MessageType.USER,
                content=text,
                is_complete=True
            )
            self.message_list.add_message(user_msg)
        
        # Process as normal message
        await self._process_message(text)
    
    async def _process_message(self, text: str):
        """Process a user message."""
        if not self.controller or not self.message_list:
            return
        
        self._processing = True
        if self.status_bar:
            self.status_bar.set_processing(True)
        
        try:
            async for msg in self.controller.submit_message(text):
                # Skip user messages as they're already displayed
                if msg.type == MessageType.USER:
                    continue
                
                self.message_list.add_message(msg)
                
                # Update token count
                if self.status_bar:
                    tokens = self.controller.get_token_count()
                    self.status_bar.set_token_count(tokens)
        
        except Exception as e:
            error_msg = UIMessage(
                type=MessageType.ERROR,
                content=f"Error: {str(e)}"
            )
            self.message_list.add_message(error_msg)
        
        finally:
            self._processing = False
            if self.status_bar:
                self.status_bar.set_processing(False)
    
    async def _handle_command(self, text: str):
        """Handle slash commands using the command registry."""
        # Create command context
        from pilotcode.tools.base import ToolUseContext
        
        store = get_store()
        ctx = CommandContext(
            cwd=str(Path.cwd()),
            query_engine=self.controller.query_engine if self.controller else None
        )
        
        try:
            is_command, result = await process_user_input(text, ctx)
            
            if not is_command:
                # Should not happen as we checked for /
                return
            
            # Handle quit command specially
            if isinstance(result, str) and result == "":
                # Check if it was quit command
                cmd_name = text.split()[0][1:].lower()  # Remove / and get name
                if cmd_name in ("quit", "exit", "q"):
                    self.app.exit()
                    return
            
            # Display command result
            if isinstance(result, str):
                msg = UIMessage(
                    type=MessageType.SYSTEM,
                    content=result
                )
                if self.message_list:
                    self.message_list.add_message(msg)
            
            # Handle clear command specially - also clear the message list
            cmd_name = text.split()[0][1:].lower() if text.startswith('/') else ""
            if cmd_name in ("clear", "cls"):
                if self.message_list:
                    self.message_list.clear_messages()
                if self.controller:
                    self.controller.clear_history()
                    
        except SystemExit:
            self.app.exit()
        except Exception as e:
            msg = UIMessage(
                type=MessageType.ERROR,
                content=f"Error executing command: {str(e)}"
            )
            if self.message_list:
                self.message_list.add_message(msg)
    
    async def _request_permission(self, tool_name: str, params: dict) -> PermissionResult:
        """Request permission for tool execution."""
        # Create an event to wait for the result
        permission_event = asyncio.Event()
        permission_result: list[PermissionResult | None] = [None]
        
        def on_dismiss(result: PermissionResult) -> None:
            permission_result[0] = result
            permission_event.set()
        
        # Show permission dialog
        dialog = PermissionDialog(tool_name, params)
        dialog.set_on_dismiss(on_dismiss)
        self.app.push_screen(dialog)
        
        # Wait for the dialog to be dismissed
        await permission_event.wait()
        return permission_result[0] if permission_result[0] is not None else PermissionResult(
            PermissionAction.DENY, tool_name
        )
    
    def watch_sidebar_visible(self, visible: bool):
        """React to sidebar visibility changes."""
        self.set_class(visible, "sidebar-visible")
    
    def action_toggle_sidebar(self):
        """Toggle sidebar visibility."""
        self.sidebar_visible = not self.sidebar_visible
    
    def action_quit(self):
        """Quit the application."""
        self.app.exit()
    
    def action_save(self):
        """Save session."""
        if self.controller:
            success = self.controller.save_session('session.json')
            if self.status_bar:
                self.status_bar.set_status(
                    "Session saved" if success else "Save failed"
                )
    
    def action_clear(self):
        """Clear conversation."""
        if self.message_list:
            self.message_list.clear_messages()
        if self.controller:
            self.controller.clear_history()
        if self.status_bar:
            self.status_bar.set_status("Conversation cleared")
    
    def action_help(self):
        """Show help."""
        self._handle_command('/help')
