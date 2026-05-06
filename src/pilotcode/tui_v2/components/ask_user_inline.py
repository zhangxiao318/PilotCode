"""Inline ask user component for TUI v2."""

import asyncio
from typing import Optional
from textual.widgets import Static, Input
from textual.containers import Vertical
from textual.reactive import reactive
from textual.message import Message


class AskUserResponded(Message):
    """Message sent when user responds to an ask user request."""

    def __init__(self, response: str):
        self.response = response
        super().__init__()


class InlineAskUserRequest(Vertical):
    """Inline ask user request displayed in message list.

    Shows a question (and optional options) with an input field
    for the user to respond. Uses the same async polling pattern
    as InlinePermissionRequest for cross-loop compatibility.
    """

    can_focus = True
    can_focus_children = True  # Input needs focus

    DEFAULT_CSS = """
    InlineAskUserRequest {
        height: auto;
        margin: 0;
        padding: 0 1;
        background: transparent;
        border: solid $primary;
    }
    InlineAskUserRequest:focus {
        border: solid $success;
    }
    InlineAskUserRequest .question {
        height: auto;
        text-style: bold;
        color: $primary;
    }
    InlineAskUserRequest .options {
        height: auto;
        color: $text-muted;
        padding-left: 2;
    }
    InlineAskUserRequest .hint {
        height: auto;
        color: $text-muted;
        text-style: dim;
        margin-top: 1;
    }
    InlineAskUserRequest .answered {
        height: auto;
        color: $success;
    }
    """

    question: reactive[str] = reactive("")
    options: reactive[list[str]] = reactive([])
    answered: reactive[bool] = reactive(False)

    def __init__(self, question: str, options: list[str] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.question = question
        self.options = options or []
        self._response: Optional[str] = None
        self._answered_flag = False
        self._input: Optional[Input] = None

    def compose(self):
        """Compose the ask user widget."""
        yield Static(f"❓ {self.question}", classes="question")

        if self.options:
            for i, option in enumerate(self.options, 1):
                yield Static(f"  {i}. {option}", classes="options")
            yield Static(
                "Type your answer or press the option number",
                classes="hint",
            )
        else:
            yield Static("Type your answer and press Enter", classes="hint")

        self._input = Input(placeholder="Your answer...")
        yield self._input

    def on_mount(self):
        """Focus the input on mount."""
        if self._input:
            self._input.focus()

    def on_input_submitted(self, event: Input.Submitted):
        """Handle Enter key in input.

        If options are provided and the input is a valid option number,
        map it to the corresponding option text.
        """
        if self.answered:
            return
        value = event.value.strip()
        # Check if input is a numeric option selection
        if self.options and value.isdigit():
            idx = int(value) - 1
            if 0 <= idx < len(self.options):
                self._respond(self.options[idx])
                return
        self._respond(value)

    def _respond(self, response: str):
        """Record response and update UI."""
        self.answered = True
        self._answered_flag = True
        self._response = response

        try:
            self.remove_children()
            self.mount(Static(f"✓ You: {response}", classes="answered"))
        except Exception:
            pass  # Widget might be detached

        self.post_message(AskUserResponded(response))

    async def wait_for_response(self) -> str:
        """Wait for user response using polling for cross-loop compatibility."""
        while not self._answered_flag:
            await asyncio.sleep(0.05)  # Short sleep to yield control
        return self._response or ""
