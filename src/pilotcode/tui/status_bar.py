"""Status bar component for TUI."""

from dataclasses import dataclass, field
from typing import Callable
from datetime import datetime

from rich.console import Console, ConsoleOptions, RenderResult
from rich.text import Text
from rich.style import Style
from rich.align import Align
from rich.panel import Panel
from rich.layout import Layout


@dataclass
class StatusItem:
    """Status bar item."""
    key: str
    value: str
    style: str = "white"
    icon: str | None = None
    priority: int = 0
    
    def render(self) -> Text:
        """Render status item."""
        text = Text()
        if self.icon:
            text.append(f"{self.icon} ", style=self.style)
        text.append(f"{self.key}: ", style="dim")
        text.append(self.value, style=self.style)
        return text


class StatusBar:
    """Status bar for showing system status."""
    
    # Status styles
    STYLES = {
        "normal": Style(color="white", bgcolor="grey19"),
        "insert": Style(color="black", bgcolor="green"),
        "visual": Style(color="black", bgcolor="yellow"),
        "command": Style(color="white", bgcolor="blue"),
        "error": Style(color="white", bgcolor="red"),
        "warning": Style(color="black", bgcolor="yellow"),
    }
    
    def __init__(
        self,
        console: Console | None = None,
        height: int = 1,
    ):
        self.console = console or Console()
        self.height = height
        self._items: dict[str, StatusItem] = {}
        self._mode: str = "normal"
        self._callbacks: list[Callable[[str, str], None]] = []
        self._update_callbacks: list[Callable[[], None]] = []
    
    def register_update_callback(self, callback: Callable[[], None]):
        """Register callback for status updates."""
        self._update_callbacks.append(callback)
    
    def _notify_update(self):
        """Notify update callbacks."""
        for callback in self._update_callbacks:
            try:
                callback()
            except Exception:
                pass
    
    def set_mode(self, mode: str):
        """Set current mode."""
        self._mode = mode
        self._notify_update()
    
    def set_item(
        self,
        key: str,
        value: str,
        style: str = "white",
        icon: str | None = None,
    ):
        """Set a status item."""
        self._items[key] = StatusItem(
            key=key,
            value=value,
            style=style,
            icon=icon,
        )
        self._notify_update()
    
    def remove_item(self, key: str):
        """Remove a status item."""
        if key in self._items:
            del self._items[key]
            self._notify_update()
    
    def update_item(self, key: str, value: str | None = None, style: str | None = None):
        """Update a status item."""
        if key not in self._items:
            return
        
        item = self._items[key]
        if value is not None:
            item.value = value
        if style is not None:
            item.style = style
        
        self._notify_update()
    
    def get_mode_style(self) -> Style:
        """Get style for current mode."""
        return self.STYLES.get(self._mode, self.STYLES["normal"])
    
    def render(self, width: int | None = None) -> Text:
        """Render status bar."""
        if width is None:
            width = self.console.width
        
        # Build left and right sections
        left_items = []
        right_items = []
        
        # Mode indicator (left)
        mode_text = Text(f" {self._mode.upper()} ", style=self.get_mode_style())
        left_items.append(mode_text)
        
        # Standard items
        standard_order = ["agent", "model", "tools", "cost", "tokens"]
        for key in standard_order:
            if key in self._items:
                left_items.append(Text("  "))
                left_items.append(self._items[key].render())
        
        # Right side items
        right_order = ["git", "file", "time"]
        for key in right_order:
            if key in self._items:
                right_items.append(self._items[key].render())
                right_items.append(Text("  "))
        
        # Build full bar
        left_text = Text().join(left_items)
        right_text = Text().join(right_items)
        
        # Calculate spacing
        left_len = len(left_text)
        right_len = len(right_text)
        
        if left_len + right_len < width:
            spacer = Text(" " * (width - left_len - right_len))
            full_text = Text().join([left_text, spacer, right_text])
        else:
            # Truncate if too long
            full_text = left_text[:width]
        
        # Apply background
        full_text.stylize(Style(bgcolor="grey19"))
        
        return full_text
    
    def __rich_console__(
        self,
        console: Console,
        options: ConsoleOptions,
    ) -> RenderResult:
        """Rich console protocol."""
        yield self.render(options.max_width)
    
    def render_panel(self) -> Panel:
        """Render as a panel."""
        return Panel(
            self.render(),
            border_style="dim",
            padding=(0, 0),
        )


class DynamicStatusBar(StatusBar):
    """Status bar with dynamic updates."""
    
    def __init__(self, console: Console | None = None, height: int = 1):
        super().__init__(console, height)
        self._running = False
        self._update_interval = 1.0
    
    def start_updates(self):
        """Start background updates."""
        import threading
        
        self._running = True
        
        def update_loop():
            while self._running:
                # Update time
                self.set_item(
                    "time",
                    datetime.now().strftime("%H:%M:%S"),
                    style="dim",
                )
                self._notify_update()
                
                import time
                time.sleep(self._update_interval)
        
        thread = threading.Thread(target=update_loop, daemon=True)
        thread.start()
    
    def stop_updates(self):
        """Stop background updates."""
        self._running = False
    
    def set_git_status(self, branch: str, dirty: bool = False):
        """Set git status."""
        icon = "●" if dirty else "○"
        style = "yellow" if dirty else "green"
        self.set_item("git", f"{icon} {branch}", style=style)
    
    def set_model(self, model: str):
        """Set current model."""
        self.set_item("model", model, style="cyan", icon="🤖")
    
    def set_cost(self, cost: float, currency: str = "$"):
        """Set session cost."""
        self.set_item("cost", f"{currency}{cost:.4f}", style="green", icon="💰")
    
    def set_tokens(self, input_tokens: int, output_tokens: int):
        """Set token usage."""
        total = input_tokens + output_tokens
        self.set_item("tokens", f"{total:,}", style="blue", icon="📊")
    
    def set_active_agent(self, agent_name: str | None):
        """Set active agent."""
        if agent_name:
            self.set_item("agent", agent_name, style="magenta", icon="🎯")
        else:
            self.remove_item("agent")
    
    def set_current_file(self, file_path: str | None):
        """Set current file."""
        if file_path:
            # Show just filename
            import os
            filename = os.path.basename(file_path)
            self.set_item("file", filename, style="white", icon="📄")
        else:
            self.remove_item("file")


# Global status bar
_status_bar: DynamicStatusBar | None = None


def get_status_bar() -> DynamicStatusBar:
    """Get global status bar."""
    global _status_bar
    if _status_bar is None:
        _status_bar = DynamicStatusBar()
    return _status_bar
