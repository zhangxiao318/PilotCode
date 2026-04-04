"""Textual TUI app for PilotCode."""

import asyncio
from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Input, Static, Button, Label

from ..tools.registry import get_all_tools, get_tool
from ..tools.base import ToolUseContext
from ..commands.base import process_user_input, CommandContext
from ..query_engine import QueryEngine, QueryEngineConfig
from ..state.app_state import get_default_app_state
from ..state.store import Store, set_global_store
from ..utils.config import get_global_config
from ..types.message import AssistantMessage, ToolUseMessage
from ..permissions import get_tool_executor, PermissionLevel
from ..permissions.permission_manager import (
    PermissionRequest,
    PermissionLevel as PL,
    get_permission_manager,
)
from .screens import PermissionModal
from .message_renderer import MessageRenderer, Message, MessageType as RenderMessageType


class PilotCodeApp(App):
    """Main Textual app with three areas:
    - Top: message/output scroll area
    - Middle: user input row
    - Bottom: tooltips / status footer
    """

    CSS = """
    PilotCodeApp {
        layout: vertical;
    }
    #main-scroll {
        height: 1fr;
        overflow-y: scroll;
        border: solid $primary;
    }
    #input-row {
        height: auto;
        max-height: 3;
        border-top: solid $primary-lighten-2;
    }
    #user-input {
        width: 1fr;
    }
    #footer {
        height: auto;
        max-height: 2;
        background: $surface-darken-1;
        color: $text-muted;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear_messages", "Clear"),
    ]

    def __init__(self, auto_allow: bool = False):
        self.auto_allow = auto_allow
        super().__init__()

    def compose(self) -> ComposeResult:
        with Vertical(id="main-scroll"):
            pass
        with Horizontal(id="input-row"):
            yield Input(placeholder="Type /help for commands or ask a question...", id="user-input")
        yield Static("Ready", id="footer")

    async def on_mount(self) -> None:
        # Application state
        self.store = Store(get_default_app_state())
        set_global_store(self.store)
        self.renderer = MessageRenderer()

        # Query engine
        tools = get_all_tools()
        self.query_engine = QueryEngine(QueryEngineConfig(
            cwd=self.store.get_state().cwd,
            tools=tools,
            get_app_state=self.store.get_state,
            set_app_state=lambda f: self.store.set_state(f)
        ))

        # Tool executor (console not used in textual mode)
        self.tool_executor = get_tool_executor()

        # Permissions
        pm = get_permission_manager()
        if self.auto_allow:
            from ..permissions.permission_manager import ToolPermission
            for tool in tools:
                pm._permissions[tool.name] = ToolPermission(
                    tool_name=tool.name,
                    level=PermissionLevel.ALWAYS_ALLOW
                )
            self.add_system_message("⚡ Auto-allow mode enabled — all tool executions will be allowed")
            self.update_footer("Auto-allow mode | /help for commands | Ctrl+C to quit")
        else:
            pm.set_permission_callback(self._permission_callback)
            self.update_footer("Ready | /help for commands | Ctrl+C to quit")

        self.add_welcome_message()

        # Focus input
        self.query_one("#user-input", Input).focus()

    async def _permission_callback(self, request: PermissionRequest) -> PL:
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

    def update_footer(self, text: str) -> None:
        from rich.text import Text
        from rich.align import Align
        footer = self.query_one("#footer", Static)
        footer.update(Align.center(Text(text, style="dim cyan")))

    def add_welcome_message(self) -> None:
        from rich.panel import Panel
        welcome = Panel.fit(
            "[bold cyan]PilotCode[/bold cyan] [dim]v0.2.0[/dim]\n"
            "[cyan]AI Programming Assistant[/cyan]\n"
            "[dim]Type /help for commands, or ask me to write code![/dim]",
            border_style="cyan"
        )
        self.append_message(welcome)

    def append_message(self, renderable) -> Static:
        container = self.query_one("#main-scroll", Vertical)
        static = Static()
        container.mount(static)
        static.update(renderable)
        container.scroll_end(animate=False)
        return static

    def add_user_message(self, text: str) -> None:
        msg = Message(role=RenderMessageType.USER, content=text)
        self.append_message(self.renderer.render(msg))

    def add_system_message(self, text: str) -> None:
        self.append_message(self.renderer.render_system_message(text))

    def add_tool_use_message(self, tool_name: str, tool_input: dict) -> None:
        msg = Message(
            role=RenderMessageType.TOOL_USE,
            content="",
            metadata={"tool_name": tool_name, "tool_input": tool_input}
        )
        self.append_message(self.renderer.render(msg))

    def add_tool_result_message(self, content: str, success: bool) -> None:
        msg = Message(
            role=RenderMessageType.TOOL_RESULT,
            content=content,
            metadata={"success": success}
        )
        self.append_message(self.renderer.render(msg))

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        input_widget = self.query_one("#user-input", Input)
        text = event.value.strip()
        if not text:
            return

        input_widget.value = ""
        input_widget.disabled = True

        self.add_user_message(text)
        await self.process_user_message(text)

        input_widget.disabled = False
        input_widget.focus()

    async def process_user_message(self, text: str) -> None:
        context = CommandContext(cwd=self.store.get_state().cwd)
        is_command, result = await process_user_input(text, context)
        if is_command:
            if isinstance(result, str):
                self.add_system_message(result)
            else:
                self.add_system_message(str(result))
            return

        await self._run_llm_turn(text)

    async def _run_llm_turn(self, prompt: str) -> None:
        max_iterations = 10
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            pending_tools = []
            full_content = ""
            current_ai_static = None

            self.update_footer("Thinking...")

            try:
                async for result in self.query_engine.submit_message(prompt):
                    msg = result.message
                    if isinstance(msg, AssistantMessage) and msg.content:
                        if result.is_complete:
                            full_content = msg.content
                            rendered = self.renderer.render(
                                Message(role=RenderMessageType.ASSISTANT, content=full_content)
                            )
                            if current_ai_static is None:
                                current_ai_static = self.append_message(rendered)
                            else:
                                current_ai_static.update(rendered)
                            current_ai_static = None
                        else:
                            full_content += msg.content
                            rendered = self.renderer.render(
                                Message(role=RenderMessageType.ASSISTANT, content=full_content)
                            )
                            if current_ai_static is None:
                                current_ai_static = self.append_message(rendered)
                            else:
                                current_ai_static.update(rendered)
                            self.query_one("#main-scroll", Vertical).scroll_end(animate=False)
                    elif isinstance(msg, ToolUseMessage):
                        pending_tools.append(msg)
            except Exception as e:
                self.add_system_message(f"Error: {e}")
                return

            if not pending_tools:
                break

            for tool_msg in pending_tools:
                self.add_tool_use_message(tool_msg.name, tool_msg.input)
                self.update_footer(f"Executing {tool_msg.name}...")

                ctx = ToolUseContext(
                    get_app_state=self.store.get_state,
                    set_app_state=lambda f: self.store.set_state(f)
                )

                exec_result = await self.tool_executor.execute_tool_by_name(
                    tool_msg.name,
                    tool_msg.input,
                    ctx
                )

                if exec_result.success and exec_result.result:
                    result_content = str(exec_result.result.data) if exec_result.result.data else "Success"
                    self.add_tool_result_message(result_content, True)
                else:
                    result_content = exec_result.message
                    self.add_tool_result_message(result_content, False)

                self.query_engine.add_tool_result(
                    tool_msg.tool_use_id,
                    result_content,
                    is_error=not exec_result.success
                )

            prompt = "Please continue based on the tool results above."

        if iteration >= max_iterations:
            self.add_system_message("⚠️ Reached maximum tool execution rounds")

        self.update_footer("Ready | /help for commands | Ctrl+C to quit")

    def action_clear_messages(self) -> None:
        container = self.query_one("#main-scroll", Vertical)
        container.remove_children()
        self.add_welcome_message()
