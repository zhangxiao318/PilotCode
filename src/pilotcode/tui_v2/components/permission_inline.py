"""Inline permission request component for tool execution."""

import asyncio
from enum import Enum, auto
from typing import Optional, Callable
from textual.widgets import Static, Button
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive
from textual.message import Message


class PermissionAction(Enum):
    """Permission action types."""
    ALLOW = auto()
    DENY = auto()
    ALLOW_SESSION = auto()
    DENY_SESSION = auto()


class PermissionResult:
    """Result of permission request."""
    
    def __init__(self, action: PermissionAction, tool_name: str):
        self.action = action
        self.tool_name = tool_name
    
    @property
    def allowed(self) -> bool:
        """Whether the action is allowed."""
        return self.action in (PermissionAction.ALLOW, PermissionAction.ALLOW_SESSION)
    
    @property
    def for_session(self) -> bool:
        """Whether this applies for the entire session."""
        return self.action in (PermissionAction.ALLOW_SESSION, PermissionAction.DENY_SESSION)


class PermissionResponded(Message):
    """Message sent when permission is responded."""
    
    def __init__(self, result: PermissionResult):
        self.result = result
        super().__init__()


class InlinePermissionRequest(Vertical):
    """Inline permission request displayed in message list."""
    
    # Ensure this widget can receive focus
    can_focus = True
    can_focus_children = False  # We want key events on this widget, not children
    
    DEFAULT_CSS = """
    InlinePermissionRequest {
        height: auto;
        margin: 0;
        padding: 0 1;
        background: transparent;
        border: solid $warning;
    }
    InlinePermissionRequest:focus {
        border: solid $success;
    }
    InlinePermissionRequest .header {
        height: 1;
        text-style: bold;
        color: $warning;
    }
    InlinePermissionRequest .description {
        height: auto;
        color: $text-muted;
        text-style: dim;
    }
    InlinePermissionRequest .risk-box {
        height: auto;
        background: $surface;
        padding: 0 1;
        margin: 1 0;
    }
    InlinePermissionRequest .risk-title {
        text-style: bold;
        color: $warning;
    }
    InlinePermissionRequest .risk-text {
        color: $text-muted;
        text-style: dim;
    }
    InlinePermissionRequest .params {
        height: auto;
        color: $text-muted;
        padding-left: 2;
    }
    InlinePermissionRequest .options {
        height: 1;
        color: $text;
        text-style: bold;
        margin-top: 1;
    }
    InlinePermissionRequest .answered {
        height: 1;
        color: $success;
        text-style: bold;
    }
    """
    
    tool_name: reactive[str] = reactive("")
    params: reactive[dict] = reactive({})
    answered: reactive[bool] = reactive(False)
    
    def __init__(self, tool_name: str, params: dict, **kwargs):
        super().__init__(**kwargs)
        self.tool_name = tool_name
        self.params = params
        self._result: Optional[PermissionResult] = None
        self._answered_flag = False  # Simple flag for cross-loop detection
    
    def compose(self):
        """Compose the permission request - compact inline style."""
        # Compact header line
        yield Static(f"⚠️  {self.tool_name}: requires permission", classes="header")
        
        # Risk info (one line)
        risk_text = self._get_risk_text(self.tool_name, self.params)
        yield Static(risk_text, classes="risk-text")
        
        # Parameters (if any)
        params_text = self._format_params()
        if params_text:
            yield Static(params_text, classes="params")
        
        # Options - keyboard only
        yield Static("[1] Allow once  [2] Allow for this session  [3] Reject  [4] Reject, tell the model what to do instead", classes="options")
    
    def _get_tool_description(self, tool_name: str) -> str:
        """Get description for tool."""
        descriptions = {
            "bash": "This tool executes shell commands on your system.",
            "read_file": "This tool reads file contents from your system.",
            "write_file": "This tool writes or creates files on your system.",
            "search": "This tool searches for files and patterns.",
            "edit_file": "This tool modifies existing files.",
            "delete_file": "This tool deletes files from your system.",
            "web_search": "This tool searches the web for information.",
            "web_fetch": "This tool fetches content from URLs.",
        }
        return descriptions.get(tool_name, f"This tool ({tool_name}) will perform an operation on your system.")
    
    def _get_risk_text(self, tool_name: str, params: dict) -> str:
        """Get compact risk assessment text."""
        risk_levels = {
            "bash": "Risk: HIGH - Can execute arbitrary commands",
            "write_file": "Risk: HIGH - Can create/overwrite files",
            "edit_file": "Risk: MEDIUM - Can modify file contents",
            "delete_file": "Risk: HIGH - Can delete files",
            "read_file": "Risk: LOW - Read-only access",
            "search": "Risk: LOW - Filesystem search",
            "web_search": "Risk: LOW - External API call",
            "web_fetch": "Risk: LOW - External data fetch",
        }
        return risk_levels.get(tool_name, "Risk: MEDIUM - Review carefully")
    
    def _format_params(self) -> str:
        """Format parameters for display."""
        lines = []
        
        # Show most important params first
        priority_keys = ["command", "path", "file_path", "content", "pattern", "question", "url"]
        shown = set()
        
        for key in priority_keys:
            if key in self.params:
                value = self.params[key]
                if isinstance(value, str):
                    # Truncate long values
                    if len(value) > 60:
                        value = value[:57] + "..."
                    # Escape newlines for display
                    value = value.replace("\n", "\\n")
                lines.append(f"  {key}: {value}")
                shown.add(key)
        
        # Show remaining params (limited)
        for key, value in self.params.items():
            if key not in shown and len(lines) < 5:
                if isinstance(value, str):
                    if len(value) > 60:
                        value = value[:57] + "..."
                    value = value.replace("\n", "\\n")
                lines.append(f"  {key}: {value}")
        
        return "\n".join(lines)
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if self.answered:
            return
        
        button_id = event.button.id
        if button_id == "allow":
            action = PermissionAction.ALLOW
        elif button_id == "allow_session":
            action = PermissionAction.ALLOW_SESSION
        elif button_id == "deny":
            action = PermissionAction.DENY
        elif button_id == "deny_session":
            action = PermissionAction.DENY_SESSION
        else:
            action = PermissionAction.DENY
        
        self._respond(action)
    
    def on_key(self, event) -> None:
        """Handle keyboard shortcuts."""
        if self.answered:
            return
        
        key = str(event.key)
        if key == "1":
            self._respond(PermissionAction.ALLOW)
        elif key == "2":
            self._respond(PermissionAction.ALLOW_SESSION)
        elif key == "3":
            self._respond(PermissionAction.DENY)
        elif key == "4":
            self._respond(PermissionAction.DENY_SESSION)
    
    def _respond(self, action: PermissionAction) -> None:
        """Respond to permission request."""
        self.answered = True
        self._answered_flag = True
        self._result = PermissionResult(action, self.tool_name)
        
        # Update UI to show answered state
        try:
            self.remove_children()
            action_names = {
                PermissionAction.ALLOW: "✓ Allowed (once)",
                PermissionAction.ALLOW_SESSION: "✓ Allowed for this session",
                PermissionAction.DENY: "✗ Rejected",
                PermissionAction.DENY_SESSION: "✗ Rejected, telling model...",
            }
            self.mount(Static(action_names[action], classes="answered"))
        except Exception:
            pass  # Widget might be detached
        
        # Post message to parent (for any additional handling)
        self.post_message(PermissionResponded(self._result))
    
    def get_result(self) -> Optional[PermissionResult]:
        """Get the permission result."""
        return self._result
    
    async def wait_for_response(self) -> PermissionResult:
        """Wait for user response using polling for cross-loop compatibility."""
        while not self._answered_flag:
            await asyncio.sleep(0.05)  # Short sleep to yield control
        return self._result
