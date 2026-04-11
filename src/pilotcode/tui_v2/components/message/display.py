"""Message display components for chat interface."""

from typing import Optional
from textual.widgets import Static, Button, TextArea
from textual.containers import Vertical, ScrollableContainer, Horizontal
from textual.screen import Screen
from textual.reactive import reactive
from textual.message import Message
from rich.console import RenderableType
from rich.markdown import Markdown
from rich.text import Text

from pilotcode.tui_v2.controller.controller import UIMessage, UIMessageType
from pilotcode.types.message import MessageType

# Internal clipboard buffer (fallback when system clipboard is unavailable)
_internal_clipboard: str = ""


def _copy_to_clipboard_impl(text: str) -> bool:
    """Copy text to system clipboard.

    Tries multiple methods in order:
    1. pyperclip (cross-platform)
    2. OSC 52 (terminal clipboard - works over SSH)
    3. xclip (Linux)
    4. pbcopy (macOS)
    5. clip.exe (Windows)
    """
    try:
        import subprocess
        import platform

        # Try pyperclip first (most reliable)
        try:
            import pyperclip

            pyperclip.copy(text)
            return True
        except ImportError:
            pass

        # Try OSC 52 (works over SSH if terminal supports it)
        try:
            _osc52_copy(text)
            return True
        except Exception:
            pass

        # Platform-specific fallbacks
        system = platform.system()
        try:
            if system == "Linux":
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=text.encode(),
                    check=True,
                    capture_output=True,
                )
                return True
            elif system == "Darwin":  # macOS
                subprocess.run(["pbcopy"], input=text.encode(), check=True, capture_output=True)
                return True
            elif system == "Windows":
                subprocess.run(["clip.exe"], input=text.encode(), check=True, capture_output=True)
                return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    except Exception:
        pass

    return False


def _osc52_copy(text: str) -> None:
    """Copy text using OSC 52 escape sequence.

    This works over SSH if the terminal emulator supports it.
    Most modern terminals (iTerm2, Windows Terminal, foot, etc.) support this.
    Xshell may support it with proper configuration.
    """
    import base64
    import sys

    # Encode text to base64
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")

    # OSC 52 sequence: ESC ] 52 ; c ; <base64> BEL
    # c = clipboard selection
    # Using ST (ESC \) as terminator for better compatibility
    osc52 = f"\x1b]52;c;{encoded}\x1b\\"

    # Write to stdout
    sys.stdout.write(osc52)
    sys.stdout.flush()


def copy_to_clipboard(text: str, use_internal: bool = True) -> tuple[bool, bool]:
    """Copy text to clipboard.

    Returns:
        (system_success, used_internal): Whether system clipboard succeeded,
                                          and whether internal buffer was used.
    """
    global _internal_clipboard

    # Always update internal buffer as fallback
    if use_internal:
        _internal_clipboard = text

    # Try system clipboard
    if _copy_to_clipboard_impl(text):
        return True, False

    return False, use_internal


def get_internal_clipboard() -> str:
    """Get the internal clipboard content."""
    return _internal_clipboard


class MessageAction(Message):
    """Message action event."""

    def __init__(self, action: str, message: UIMessage):
        self.action = action
        self.message = message
        super().__init__()


class MessageDisplay(Static):
    """Display a single message with compact styling and actions."""

    DEFAULT_CSS = """
    MessageDisplay {
        height: auto;
        margin: 0;
        padding: 0 1;
        background: transparent;
        color: $text;
    }
    
    MessageDisplay:hover {
        background: $surface-lighten-1;
    }
    
    /* User messages - left aligned with smiley */
    MessageDisplay.user {
        text-align: left;
        background: transparent;
        color: $text;
        padding: 0 1;
        margin: 0;
    }
    
    MessageDisplay.user:hover {
        background: $surface-lighten-1;
    }
    
    /* Assistant messages - left aligned with white dot */
    MessageDisplay.assistant {
        background: transparent;
        color: $text;
        padding: 0 1;
        margin: 0;
    }
    
    MessageDisplay.assistant:hover {
        background: $surface-lighten-1;
    }
    
    /* Tool messages - left aligned with green dot */
    MessageDisplay.tool {
        background: transparent;
        color: $warning;
        padding: 0 1;
        margin: 0;
    }
    
    /* Tool result - left aligned */
    MessageDisplay.tool-result {
        background: transparent;
        color: $success;
        padding: 0 1;
        margin: 0;
    }
    
    /* Error - visible red */
    MessageDisplay.error {
        background: $error 20%;
        border-left: solid $error;
        color: $text;
        padding: 1 2;
        margin: 1 0;
    }
    
    /* System - boxed welcome message, left aligned */
    MessageDisplay.system {
        background: $surface;
        color: $text;
        text-align: left;
        padding: 0;
        margin: 1 0;
    }
    
    /* Action bar - shown on hover/focus */
    MessageDisplay .action-bar {
        display: none;
        height: 1;
        dock: top;
        layer: overlay;
    }
    
    MessageDisplay:hover .action-bar,
    MessageDisplay:focus-within .action-bar {
        display: block;
    }
    
    MessageDisplay .action-bar Static {
        color: $text-muted;
        text-style: dim;
    }
    
    MessageDisplay .action-bar Static:hover {
        color: $primary;
        text-style: bold;
    }
    """

    BINDINGS = [
        ("c", "copy", "Copy"),
        ("y", "yank", "Yank"),
    ]

    message: reactive[Optional[UIMessage]] = reactive(None)

    def __init__(self, message: UIMessage, show_actions: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.message = message
        self.show_actions = show_actions
        self._update_classes()
        self.can_focus = True

    def _update_classes(self):
        """Update CSS classes based on message type."""
        if not self.message:
            return

        # Remove old type classes
        for cls in ["user", "assistant", "tool", "tool-result", "error", "system"]:
            self.remove_class(cls)

        # Add new type class
        type_class = self._get_type_class(self.message.type)
        if type_class:
            self.add_class(type_class)

    def _get_type_class(self, msg_type: MessageType) -> str:
        """Get CSS class for message type."""
        mapping = {
            MessageType.USER: "user",
            MessageType.ASSISTANT: "assistant",
            MessageType.TOOL_USE: "tool",
            MessageType.TOOL_RESULT: "tool-result",
            MessageType.ERROR: "error",
            MessageType.SYSTEM: "system",
        }
        return mapping.get(msg_type, "")

    def _get_header(self) -> str:
        """Get message header (used for non-compact modes)."""
        if not self.message:
            return ""

        headers = {
            MessageType.USER: "You",
            MessageType.ASSISTANT: "🤖",
            MessageType.TOOL_USE: "🔧",
            MessageType.TOOL_RESULT: "📤",
            MessageType.ERROR: "❌",
            MessageType.SYSTEM: "ℹ️",
        }

        return headers.get(self.message.type, "")

    def _format_content(self) -> RenderableType:
        """Format content based on message type."""
        if not self.message:
            return ""

        content = self.message.content or ""

        # Tool messages - green dot prefix
        if self.message.type == MessageType.TOOL_USE:
            tool_name = self.message.metadata.get("tool_name", "Tool")
            is_safe = self.message.metadata.get("is_safe", False)
            safe_marker = "✓" if is_safe else "⚠"
            return Text(f"● {safe_marker} {tool_name}", style="green")

        # Tool result - show output preview
        if self.message.type == MessageType.TOOL_RESULT:
            # Truncate long output
            lines = content.strip().split("\n")
            preview = lines[0][:80] if lines else ""
            if len(lines) > 1 or len(content) > 80:
                preview += " ..."
            return Text(f"→ {preview}", style="dim")

        # User messages - smiley prefix
        if self.message.type == MessageType.USER:
            return Text(f"☺ {content}")

        # Assistant messages - white dot prefix + markdown
        if self.message.type == MessageType.ASSISTANT:
            try:
                # Prepend white dot to content
                marked_content = f"● {content}"
                return Markdown(marked_content)
            except Exception:
                return Text(f"● {content}")

        # System/Error - plain text
        return Text(content)

    def render(self) -> RenderableType:
        """Render the message."""
        if not self.message:
            return Text("")

        try:
            content = self._format_content()
            # All messages left aligned
            return content
        except Exception as e:
            # Fallback to plain text on any error
            return Text(f"[Render Error: {str(e)}]")

    def watch_message(self, message: UIMessage):
        """React to message changes."""
        self._update_classes()
        # Use layout=True to force recalculation of widget size
        # This is critical for streaming updates where content grows
        self.refresh(layout=True)

    def action_copy(self):
        """Copy message content to clipboard."""
        if not self.message:
            return

        content = self.message.content or ""
        system_ok, used_internal = copy_to_clipboard(content)

        if system_ok:
            self.app.notify("📋 Copied to clipboard", severity="information", timeout=2)
        elif used_internal:
            self.app.notify(
                "⚠️ Copied to internal buffer (clipboard unavailable)",
                severity="warning",
                timeout=3,
            )
        else:
            self.app.notify("❌ Failed to copy", severity="error")

    def action_yank(self):
        """Yank (copy) message - vim style alias."""
        self.action_copy()

    def on_click(self, event):
        """Handle click events."""
        import time

        current_time = time.time()

        # Check for double click (within 500ms)
        if hasattr(self, "_last_click_time") and (current_time - self._last_click_time) < 0.5:
            # Double click - open text viewer
            self._open_text_viewer()
            self._last_click_time = 0  # Reset to prevent triple-click
        else:
            # Single click - focus
            self.focus()
            self._last_click_time = current_time

    def _open_text_viewer(self):
        """Open text viewer dialog for mouse selection and copying."""
        if not self.message:
            return

        content = self.message.content or ""
        title = f"Message ({self.message.type.value}) - Double-click to select, Ctrl+C to copy"

        self.app.push_screen(TextViewerDialog(content, title))


class CompactToolDisplay(Static):
    """Compact display for tool execution (combines TOOL_USE and TOOL_RESULT)."""

    DEFAULT_CSS = """
    CompactToolDisplay {
        height: auto;
        padding: 0 2;
        margin: 0;
        color: $text-muted;
        text-style: dim;
    }
    """

    def __init__(self, tool_name: str, command: str, result: str, **kwargs):
        super().__init__(**kwargs)
        self.tool_name = tool_name
        self.command = command
        self.result = result

    def render(self) -> RenderableType:
        """Render compact tool info."""
        text = Text()
        text.append(f"$ {self.command}", style="yellow dim")
        text.append(" → ", style="dim")
        # Show result preview
        result_preview = self.result.strip().split("\n")[0][:60]
        if len(self.result) > 60 or "\n" in self.result:
            result_preview += "..."
        text.append(result_preview, style="green dim")
        return text


class MessageList(ScrollableContainer):
    """Scrollable list of messages with compact styling."""

    DEFAULT_CSS = """
    MessageList {
        width: 100%;
        height: 1fr;
        border: none;
        padding: 0;
        background: $background;
        color: $text;
    }
    MessageList > * {
        margin: 0;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._messages: list[MessageDisplay] = []
        self._streaming_message: Optional[MessageDisplay] = None
        self._pending_tool: Optional[UIMessage] = None

    def add_message(self, message: UIMessage) -> MessageDisplay:
        """Add a message to the list."""
        # Handle streaming updates
        if message.is_streaming and self._streaming_message:
            if (
                self._streaming_message.message
                and self._streaming_message.message.type == message.type
            ):
                self._streaming_message.message = message
                return self._streaming_message

        # Handle streaming completion
        if not message.is_streaming and self._streaming_message:
            if (
                self._streaming_message.message
                and self._streaming_message.message.type == message.type
            ):
                self._streaming_message.message = message
                self._streaming_message = None
                self.scroll_end()
                return self._messages[-1]

        # Store TOOL_USE to potentially combine with result
        if message.type == MessageType.TOOL_USE:
            self._pending_tool = message

        # TOOL_RESULT - check if we can combine with pending tool
        if message.type == MessageType.TOOL_RESULT and self._pending_tool:
            # For now, just show both separately with compact styling
            self._pending_tool = None

        # Create new message display
        display = MessageDisplay(message)
        self._messages.append(display)
        self.mount(display)

        if message.is_streaming:
            self._streaming_message = display

        # Scroll to bottom
        def scroll_to_bottom():
            self.scroll_end(animate=False)

        self.call_after_refresh(scroll_to_bottom)
        return display

    def update_last_message(self, message: UIMessage) -> bool:
        """Update the last message."""
        if not self._messages:
            return False

        self._messages[-1].message = message
        return True

    def clear_messages(self) -> None:
        """Clear all messages from the list."""
        # Remove all message displays
        for display in self._messages:
            display.remove()
        self._messages.clear()
        self._streaming_message = None
        self._pending_tool = None
        self._streaming_message = None
        self._pending_tool = None


class TextViewerDialog(Screen):
    """Modal dialog for viewing and copying message text.

    For SSH/Xshell users:
    - Click "📋 Copy All" to copy (uses OSC 52 if terminal supports it)
    - Click "💾 Save" to save to /tmp/ for downloading via scp
    - Use terminal's own selection if mouse reporting is disabled
    """

    DEFAULT_CSS = """
    TextViewerDialog {
        align: center middle;
    }
    TextViewerDialog > Vertical {
        width: 80;
        height: 80%;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }
    TextViewerDialog #title {
        height: 2;
        content-align: center middle;
        text-style: bold;
        background: $primary;
        color: $text;
    }
    TextViewerDialog #hint {
        height: 1;
        content-align: center middle;
        text-style: dim;
        color: $text-muted;
    }
    TextViewerDialog TextArea {
        height: 1fr;
        border: solid $border;
        background: $background;
        color: $text;
    }
    TextViewerDialog #buttons {
        height: 3;
        dock: bottom;
    }
    TextViewerDialog Button {
        width: 1fr;
    }
    """

    BINDINGS = [
        ("escape", "close", "Close"),
        ("ctrl+c", "copy_close", "Copy & Close"),
    ]

    def __init__(self, content: str, title: str = "Message Content", **kwargs):
        super().__init__(**kwargs)
        self.content = content
        self.title_text = title
        self._saved_file_path: str | None = None

    def compose(self):
        """Compose the dialog."""
        with Vertical():
            yield Static(self.title_text, id="title")
            yield Static("Press 'Copy All' to copy, or 'Save' to download via scp", id="hint")
            text_area = TextArea(text=self.content, read_only=True, show_line_numbers=False)
            text_area.cursor_blink = False
            yield text_area
            with Horizontal(id="buttons"):
                yield Button("📋 Copy All", id="copy", variant="primary")
                yield Button("💾 Save", id="save")
                yield Button("Close (Esc)", id="close")

    def on_mount(self):
        """Focus the text area on mount."""
        text_area = self.query_one(TextArea)
        text_area.focus()

    def action_close(self):
        """Close the dialog."""
        self.app.pop_screen()

    def action_copy_close(self):
        """Copy content and close."""
        self._copy_content()
        self.app.pop_screen()

    def _copy_content(self):
        """Copy content to clipboard."""
        system_ok, used_internal = copy_to_clipboard(self.content)
        if system_ok:
            self.app.notify("📋 Copied to clipboard (OSC 52)", severity="information", timeout=2)
        elif used_internal:
            self.app.notify("⚠️ Copied to internal buffer", severity="warning", timeout=2)
        else:
            self.app.notify("❌ Failed to copy", severity="error")

    def _save_to_file(self):
        """Save content to a file in /tmp for downloading."""

        try:
            # Create a temp file with meaningful name
            timestamp = __import__("time").time()
            filename = f"/tmp/pilotcode_message_{int(timestamp)}.txt"

            with open(filename, "w", encoding="utf-8") as f:
                f.write(self.content)

            self._saved_file_path = filename
            self.app.notify(
                f"💾 Saved to: {filename}\nDownload: scp user@host:{filename} .",
                severity="information",
                timeout=5,
            )
        except Exception as e:
            self.app.notify(f"❌ Failed to save: {e}", severity="error")

    def on_button_pressed(self, event: Button.Pressed):
        """Handle button presses."""
        if event.button.id == "copy":
            self._copy_content()
        elif event.button.id == "save":
            self._save_to_file()
        elif event.button.id == "close":
            self.app.pop_screen()
