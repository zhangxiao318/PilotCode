"""Permission dialog for tool execution."""

from enum import Enum, auto
from typing import Optional
from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Button
from textual.reactive import reactive


class PermissionAction(Enum):
    """Permission action types."""

    ALLOW = auto()
    DENY = auto()
    ALLOW_SESSION = auto()
    DENY_SESSION = auto()

    @staticmethod
    def from_button_id(button_id: str) -> "PermissionAction":
        """Get action from button ID."""
        mapping = {
            "allow": PermissionAction.ALLOW,
            "deny": PermissionAction.DENY,
            "allow_session": PermissionAction.ALLOW_SESSION,
            "deny_session": PermissionAction.DENY_SESSION,
        }
        return mapping.get(button_id, PermissionAction.DENY)


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


class PermissionDialog(ModalScreen[PermissionResult]):
    """Modal dialog for requesting tool execution permission."""

    DEFAULT_CSS = """
    PermissionDialog {
        align: center middle;
        background: $background 80%;
    }
    PermissionDialog > Vertical {
        width: 70;
        height: auto;
        max-height: 25;
        background: $surface;
        border: solid $warning;
        padding: 1 2;
    }
    PermissionDialog Static {
        height: auto;
        padding: 1 0;
    }
    PermissionDialog .title {
        text-style: bold;
        color: $warning;
        text-align: center;
    }
    PermissionDialog .tool-name {
        text-style: bold;
        color: $primary;
    }
    PermissionDialog .params {
        color: $text-muted;
        margin-left: 2;
    }
    PermissionDialog .hint {
        color: $text-muted;
        text-align: center;
        text-style: italic;
    }
    PermissionDialog Button {
        width: 1fr;
        margin: 1 0;
    }
    PermissionDialog Button.success {
        background: $success;
    }
    PermissionDialog Button.error {
        background: $error;
    }
    PermissionDialog Button.primary {
        background: $primary;
    }
    PermissionDialog Button.warning {
        background: $warning;
        color: $text;
    }
    PermissionDialog Button:focus {
        text-style: bold reverse;
    }
    """

    def __init__(self, tool_name: str, params: dict, **kwargs):
        super().__init__(**kwargs)
        self.tool_name = tool_name
        self.params = params
        self._on_dismiss: Optional[callable] = None
        self._focused_button: int = 0

    def set_on_dismiss(self, callback: callable) -> None:
        """Set callback to be called when dialog is dismissed."""
        self._on_dismiss = callback

    def compose(self):
        """Compose the dialog."""
        with Vertical():
            yield Static("⚠️  Tool Execution Request", classes="title")
            yield Static(f"Tool: {self.tool_name}", classes="tool-name")

            # Show relevant params
            yield Static("Parameters:")
            params_text = self._format_params()
            yield Static(params_text, classes="params")

            yield Static("Allow this tool to execute?")

            # Buttons in 2x2 grid
            with Horizontal():
                yield Button("✓ Allow (y)", variant="success", id="allow")
                yield Button("✓ Allow for Session (s)", variant="primary", id="allow_session")
            with Horizontal():
                yield Button("✗ Deny (n)", variant="error", id="deny")
                yield Button("✗ Deny for Session (e)", variant="warning", id="deny_session")

            yield Static("[Tab] Navigate  [Enter] Select  [y/n/s/e] Shortcut", classes="hint")

    def _format_params(self) -> str:
        """Format parameters for display."""
        lines = []

        # Show most important params first
        priority_keys = ["command", "path", "pattern", "question", "url"]
        shown = set()

        for key in priority_keys:
            if key in self.params:
                value = self.params[key]
                # Truncate long values
                if isinstance(value, str) and len(value) > 50:
                    value = value[:47] + "..."
                lines.append(f"  {key}: {value}")
                shown.add(key)

        # Show remaining params
        for key, value in self.params.items():
            if key not in shown:
                if isinstance(value, str) and len(value) > 50:
                    value = value[:47] + "..."
                lines.append(f"  {key}: {value}")

        # Limit total lines
        if len(lines) > 6:
            lines = lines[:6]
            lines.append("  ...")

        return "\n".join(lines) if lines else "  (no parameters)"

    def on_mount(self):
        """Focus first button on mount."""
        buttons = self.query(Button)
        if buttons:
            buttons[0].focus()

    def _dismiss_with_action(self, action: PermissionAction):
        """Dismiss dialog with action."""
        result = PermissionResult(action, self.tool_name)
        if self._on_dismiss:
            self._on_dismiss(result)
        self.dismiss(result)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        action = PermissionAction.from_button_id(event.button.id)
        self._dismiss_with_action(action)

    def on_key(self, event) -> None:
        """Handle keyboard shortcuts."""
        key = event.key.lower()

        if key == "y":
            self._dismiss_with_action(PermissionAction.ALLOW)
        elif key == "n":
            self._dismiss_with_action(PermissionAction.DENY)
        elif key == "s":
            self._dismiss_with_action(PermissionAction.ALLOW_SESSION)
        elif key == "e":
            self._dismiss_with_action(PermissionAction.DENY_SESSION)
        elif key == "escape":
            self._dismiss_with_action(PermissionAction.DENY)
