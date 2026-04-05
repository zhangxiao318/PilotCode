"""Main session screen for chat interface."""

import asyncio
from pathlib import Path
from textual.screen import Screen
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, Header, Footer
from textual.reactive import reactive

from pilotcode.tui_v2.controller.controller import TUIController, UIMessage, MessageType
from pilotcode.tui_v2.components.message.display import MessageDisplay
from pilotcode.tui_v2.components.message.virtual_list import HybridMessageList
from pilotcode.tui_v2.components.prompt.input import PromptWithMode
from pilotcode.tui_v2.components.status.bar import StatusBar
from pilotcode.tui_v2.components.dialog.permission import PermissionDialog, PermissionResult, PermissionAction
from pilotcode.tui_v2.components.search_bar import SearchBar, SearchMode, SearchNavigate
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
        height: auto;
        min-height: 3;
        dock: bottom;
        background: $surface;
        border-top: solid $border;
    }
    """
    
    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+s", "save", "Save Session"),
        ("ctrl+l", "clear", "Clear"),
        ("f1", "help", "Help"),
        ("ctrl+b", "toggle_sidebar", "Toggle Sidebar"),
        ("ctrl+y", "copy_last_assistant", "Copy Last Assistant"),
        ("ctrl+o", "copy_last_code", "Copy Last Code Block"),
        ("ctrl+f", "toggle_search", "Search"),
    ]
    
    sidebar_visible: reactive[bool] = reactive(False)
    
    def __init__(self, auto_allow: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.auto_allow = auto_allow
        self.controller: TUIController | None = None
        self.message_list: HybridMessageList | None = None
        self.prompt: PromptWithMode | None = None
        self.status_bar: StatusBar | None = None
        self.search_bar: SearchBar | None = None
        self._processing = False
        self._search_active = False
        self._search_results: list[tuple[int, int, int]] = []  # (msg_idx, start, end)
    
    def compose(self):
        """Compose the screen."""
        yield Header(show_clock=True)
        
        with Horizontal(id="main-container"):
            # Sidebar (hidden by default)
            with Vertical(id="sidebar"):
                yield Static("Sidebar", id="sidebar-content")
            
            # Main message area
            with Vertical(id="message-area"):
                self.message_list = HybridMessageList()
                yield self.message_list
        
        # Search bar (hidden by default)
        self.search_bar = SearchBar()
        yield self.search_bar
        
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
    
    def _copy_to_clipboard(self, text: str) -> bool:
        """Copy text to clipboard using system tools."""
        import subprocess
        import platform
        
        system = platform.system()
        try:
            if system == "Linux":
                subprocess.run(
                    ['xclip', '-selection', 'clipboard'],
                    input=text.encode(),
                    check=True,
                    capture_output=True
                )
                return True
            elif system == "Darwin":  # macOS
                subprocess.run(
                    ['pbcopy'],
                    input=text.encode(),
                    check=True,
                    capture_output=True
                )
                return True
            elif system == "Windows":
                subprocess.run(
                    ['clip.exe'],
                    input=text.encode(),
                    check=True,
                    capture_output=True
                )
                return True
        except Exception:
            pass
        return False
    
    def action_copy_last_assistant(self):
        """Copy the last assistant message to clipboard."""
        if not self.message_list or not self.message_list._messages:
            self.notify("No messages to copy", severity="warning")
            return
        
        # Find last assistant message
        for display in reversed(self.message_list._messages):
            if display.message and display.message.type == MessageType.ASSISTANT:
                content = display.message.content or ""
                if self._copy_to_clipboard(content):
                    self.notify("📋 Last assistant message copied!", severity="information", timeout=2)
                else:
                    self.notify("⚠️ Failed to copy to clipboard", severity="error")
                return
        
        self.notify("No assistant message found", severity="warning")
    
    def action_copy_last_code(self):
        """Copy the last code block from assistant messages."""
        if not self.message_list or not self.message_list._messages:
            self.notify("No messages to copy", severity="warning")
            return
        
        import re
        
        # Find last code block in assistant messages
        for display in reversed(self.message_list._messages):
            if display.message and display.message.type == MessageType.ASSISTANT:
                content = display.message.content or ""
                # Match code blocks: ```language\ncode\n```
                code_blocks = re.findall(r'```(?:\w+)?\n(.*?)\n```', content, re.DOTALL)
                if code_blocks:
                    code = code_blocks[-1]  # Get last code block
                    if self._copy_to_clipboard(code):
                        self.notify("📋 Last code block copied!", severity="information", timeout=2)
                    else:
                        self.notify("⚠️ Failed to copy to clipboard", severity="error")
                    return
        
        self.notify("No code block found", severity="warning")
    def action_copy_last_code(self):
        """Copy the last code block from assistant messages."""
        if not self.message_list or not self.message_list._messages:
            self.notify("No messages to copy", severity="warning")
            return
        
        import re
        
        # Find last code block in assistant messages
        for display in reversed(self.message_list._messages):
            if display.message and display.message.type == MessageType.ASSISTANT:
                content = display.message.content or ""
                # Match code blocks: ```language\ncode\n```
                code_blocks = re.findall(r'```(?:\w+)?\n(.*?)\n```', content, re.DOTALL)
                if code_blocks:
                    code = code_blocks[-1]  # Get last code block
                    if self._copy_to_clipboard(code):
                        self.notify("📋 Last code block copied!", severity="information", timeout=2)
                    else:
                        self.notify("⚠️ Failed to copy to clipboard", severity="error")
                    return
        
        self.notify("No code block found", severity="warning")
    
    def action_toggle_search(self):
        """Toggle search bar."""
        if self.search_bar:
            self.search_bar.toggle()
    
    def action_next_match(self):
        """Go to next search match."""
        if self.search_bar and self._search_active:
            self.search_bar.action_next()
    
    def action_previous_match(self):
        """Go to previous search match."""
        if self.search_bar and self._search_active:
            self.search_bar.action_previous()
    
    def on_search_mode(self, event: SearchMode):
        """Handle search mode toggle."""
        self._search_active = event.active
        if event.active:
            # Set up search callbacks
            if self.search_bar:
                self.search_bar.set_search_callback(self._perform_search)
                self.search_bar.set_navigate_callback(self._navigate_to_match)
        else:
            # Clear search
            self._search_results = []
    
    def on_search_navigate(self, event: SearchNavigate):
        """Handle search navigation."""
        pass  # Navigation handled by search bar callback
    
    def _perform_search(self, query: str) -> list[tuple[int, int, int]]:
        """Perform search across messages.
        
        Returns list of (message_index, start_offset, end_offset) tuples.
        """
        if not query or not self.message_list:
            return []
        
        import re
        results = []
        
        for idx, display in enumerate(self.message_list._messages):
            if not display.message:
                continue
            
            content = display.message.content or ""
            # Simple case-insensitive search
            pattern = re.compile(re.escape(query), re.IGNORECASE)
            
            for match in pattern.finditer(content):
                results.append((idx, match.start(), match.end()))
        
        self._search_results = results
        return results
    
    def _navigate_to_match(self, match_index: int):
        """Navigate to a specific search match."""
        if not self._search_results or match_index >= len(self._search_results):
            return
        
        msg_idx, _, _ = self._search_results[match_index]
        
        # Scroll to message
        if self.message_list and hasattr(self.message_list, '_messages'):
            if msg_idx < len(self.message_list._messages):
                # In a real implementation, you'd scroll to the specific message
                # For now, just scroll to bottom if it's the last message
                if msg_idx == len(self.message_list._messages) - 1:
                    self.message_list.scroll_to_bottom()
