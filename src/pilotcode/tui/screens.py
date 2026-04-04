"""Modal screens for the TUI."""

from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Button, Label
from textual.reactive import reactive

from ..permissions.permission_manager import PermissionRequest


class PermissionModal(ModalScreen[str]):
    """Modal screen for permission prompts."""

    CSS = """
    PermissionModal {
        align: center middle;
    }
    #dialog {
        width: 80;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #title {
        text-align: center;
        text-style: bold;
    }
    #risk {
        text-align: center;
        text-style: bold;
        margin: 1 0;
    }
    #details {
        margin: 1 0;
    }
    #buttons {
        height: auto;
        align: center middle;
    }
    Button {
        margin: 0 1;
    }
    """

    def __init__(self, request: PermissionRequest):
        self.request = request
        super().__init__()

    def compose(self):
        with Vertical(id="dialog"):
            yield Label("⚠️  Permission Required", id="title")

            risk = self.request.risk_level
            if risk in ("high", "critical"):
                risk_style = "red"
            elif risk == "medium":
                risk_style = "yellow"
            else:
                risk_style = "green"
            yield Label(f"Risk: {risk.upper()}", id="risk", classes=risk_style)

            details = []
            for k, v in self.request.tool_input.items():
                val = str(v)
                if len(val) > 120:
                    val = val[:120] + "..."
                details.append(f"[b]{k}:[/b] {val}")
            yield Static("\n".join(details), id="details")

            with Horizontal(id="buttons"):
                yield Button("Yes (y)", variant="success", id="btn-y")
                yield Button("No (n)", variant="error", id="btn-n")
                yield Button("Always (a)", id="btn-a")
                yield Button("Always this (s)", id="btn-s")
                yield Button("Never (d)", variant="primary", id="btn-d")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        mapping = {
            "btn-y": "y",
            "btn-n": "n",
            "btn-a": "a",
            "btn-s": "s",
            "btn-d": "d",
        }
        self.dismiss(mapping.get(event.button.id, "n"))

    def on_key(self, event):
        key = event.key.lower()
        if key in ("y", "n", "a", "s", "d"):
            self.dismiss(key)
