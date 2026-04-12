"""REPL for PilotCode - Programming Assistant with Tool Support."""

import asyncio
import os
import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.status import Status
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style

from ..tools.registry import get_all_tools
from ..tools.base import ToolUseContext
from ..commands.base import process_user_input, CommandContext
from ..query_engine import QueryEngine, QueryEngineConfig
from ..state.app_state import get_default_app_state, AppState
from ..state.store import Store, set_global_store
from ..utils.config import get_global_config
from ..types.message import AssistantMessage, ToolUseMessage
from ..permissions import get_tool_executor


class REPL:
    """Programming Assistant REPL with full tool support."""

    # Default max iterations for tool calls (configurable via env var)
    DEFAULT_MAX_ITERATIONS = 25

    def __init__(self, auto_allow: bool = False, max_iterations: int | None = None):
        self.console = Console()
        self.store = Store(get_default_app_state())
        set_global_store(self.store)

        # Allow override via parameter or environment variable
        if max_iterations is not None:
            self.max_iterations = max_iterations
        else:
            env_limit = os.environ.get("PILOTCODE_MAX_ITERATIONS")
            self.max_iterations = int(env_limit) if env_limit else self.DEFAULT_MAX_ITERATIONS

        get_global_config()
        self.store.set_state(lambda s: s)

        self.session = PromptSession(
            message="❯ ", style=Style.from_dict({"prompt": "#00aa00 bold"})
        )

        # Enable all tools
        tools = get_all_tools()
        self.query_engine = QueryEngine(
            QueryEngineConfig(
                cwd=self.store.get_state().cwd,
                tools=tools,
                get_app_state=self.store.get_state,
                set_app_state=lambda f: self.store.set_state(f),
            )
        )

        # Set up tool executor with our console
        self.tool_executor = get_tool_executor(self.console)

        # Auto-allow mode for testing
        self.auto_allow = auto_allow
        if auto_allow:
            # Grant all permissions automatically
            from ..permissions import get_permission_manager, PermissionLevel, ToolPermission

            pm = get_permission_manager()
            for tool in tools:
                pm._permissions[tool.name] = ToolPermission(
                    tool_name=tool.name, level=PermissionLevel.ALWAYS_ALLOW
                )
            self.console.print(
                "[dim]⚡ Auto-allow mode enabled - all tool executions will be allowed[/dim]\n"
            )

        self.running = True

    def print_header(self) -> None:
        """Print welcome header."""
        self.console.print(
            Panel.fit(
                "[bold cyan]PilotCode[/bold cyan] [dim]v0.2.0[/dim]\n"
                "[cyan]AI Programming Assistant[/cyan]\n"
                "[dim]Type /help for commands, or ask me to write code![/dim]",
                border_style="cyan",
            )
        )
        self.console.print("\n[bold green]💡 Tips:[/bold green]")
        self.console.print("  • 'Create a Python script that...'")
        self.console.print("  • 'Fix the bug in this code...'")
        self.console.print("  • 'Write tests for...'")
        self.console.print("  • Tools: FileRead, FileWrite, FileEdit, Bash, Glob, Grep")
        self.console.print("  • I will ask for permission before making changes\n")

    async def handle_command(self, input_text: str) -> bool:
        """Handle slash commands."""
        context = CommandContext(cwd=self.store.get_state().cwd, query_engine=self.query_engine)
        is_command, result = await process_user_input(input_text, context)
        if is_command:
            self.console.print(result)
            return True
        return False

    async def process_response(self, prompt: str) -> None:
        """Process a prompt through the LLM with tool support."""
        full_content = ""
        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1
            pending_tools = []

            # Show status with progress indicator
            status_text = (
                f"[cyan]Thinking...[/cyan] [dim](turn {iteration}/{self.max_iterations})[/dim]"
            )
            with Status(status_text, console=self.console, spinner="dots"):
                try:
                    async for result in self.query_engine.submit_message(prompt):
                        msg = result.message

                        if isinstance(msg, AssistantMessage):
                            if isinstance(msg.content, str):
                                if result.is_complete:
                                    # Final message: use it if non-empty, otherwise keep accumulated
                                    # If final message is shorter than accumulated, use accumulated
                                    # (handles case where accumulated has more detail)
                                    if msg.content and len(msg.content) >= len(full_content):
                                        full_content = msg.content
                                    # else: keep accumulated full_content
                                else:
                                    # Streaming: accumulate content
                                    if msg.content:
                                        full_content += msg.content

                        elif isinstance(msg, ToolUseMessage):
                            pending_tools.append(msg)

                except Exception as e:
                    self.console.print(f"[red]Error: {e}[/red]")
                    return

            # Display the assistant's response
            if full_content:
                self.console.print()
                self.console.print(Markdown(full_content))
                full_content = ""  # Reset for next iteration
                # Ensure output is flushed and visible before showing prompt
                self.console.print()  # Extra blank line for readability
                sys.stdout.flush()  # Force flush on Windows
            # else: no content to display

            # Execute pending tools
            if not pending_tools:
                # No tools to execute, we're done
                break

            for tool_idx, tool_msg in enumerate(pending_tools, 1):
                tool_progress = f"[turn {iteration}/{self.max_iterations}]"
                if len(pending_tools) > 1:
                    tool_progress += f" [tool {tool_idx}/{len(pending_tools)}]"
                self.console.print(f"\n[dim]🔧 {tool_progress} {tool_msg.name}[/dim]")

                # Execute with permission
                context = ToolUseContext(
                    get_app_state=self.store.get_state,
                    set_app_state=lambda f: self.store.set_state(f),
                )

                exec_result = await self.tool_executor.execute_tool_by_name(
                    tool_msg.name, tool_msg.input, context
                )

                # Add result to conversation
                result_content = ""
                if exec_result.success and exec_result.result:
                    result_content = (
                        str(exec_result.result.data) if exec_result.result.data else "Success"
                    )
                    self.console.print(f"[dim]✓ {tool_msg.name} completed[/dim]")
                else:
                    result_content = exec_result.message
                    self.console.print(f"[red]✗ {exec_result.message}[/red]")

                # Add to query engine history
                self.query_engine.add_tool_result(
                    tool_msg.tool_use_id, result_content, is_error=not exec_result.success
                )
                # Ensure tool output is visible
                sys.stdout.flush()

            # Continue the conversation with tool results
            prompt = "Please continue based on the tool results above."

        if iteration >= self.max_iterations:
            self.console.print(
                f"[yellow]⚠️ Reached maximum tool execution rounds ({self.max_iterations})[/yellow]"
            )
            self.console.print(
                "[dim]💡 Tip: Set PILOTCODE_MAX_ITERATIONS=50 to increase limit[/dim]"
            )

        # Ensure content is visible above the prompt on Windows
        # Use standard print to ensure compatibility with prompt_toolkit
        print("\n" * 2, end="", flush=True)

    async def run(self) -> None:
        """Run the REPL."""
        self.print_header()

        while self.running:
            try:
                user_input = await self.session.prompt_async()
                user_input = user_input.strip()

                if not user_input:
                    continue

                if await self.handle_command(user_input):
                    continue

                await self.process_response(user_input)

            except KeyboardInterrupt:
                self.console.print("\n[yellow]Use /quit to exit[/yellow]")
                continue
            except EOFError:
                break
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")
                import traceback

                traceback.print_exc()
                continue

        self.console.print("\n[dim]Goodbye! 👋[/dim]")


def run_repl(auto_allow: bool = False, max_iterations: int | None = None) -> None:
    """Run the REPL.

    Args:
        auto_allow: Automatically allow all tool executions
        max_iterations: Maximum tool execution rounds per query (default: 25)
    """
    repl = REPL(auto_allow=auto_allow, max_iterations=max_iterations)
    asyncio.run(repl.run())


async def run_headless(
    prompt: str,
    auto_allow: bool = False,
    json_mode: bool = False,
    max_iterations: int = 25,
    initial_messages: list | None = None,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Run a single prompt in headless mode and return structured output.

    Returns a dict with keys:
        - response: final assistant text
        - tool_calls: list of executed tools with results
        - success: bool
    """
    import json as json_mod
    from ..permissions import get_permission_manager, PermissionLevel, ToolPermission

    import sys

    print(f"[run_headless] Starting with cwd={cwd}", file=sys.stderr)

    # Create initial state with correct cwd
    from ..state.app_state import AppState

    initial_state = AppState(cwd=cwd or str(os.getcwd()))
    store = Store(initial_state)
    set_global_store(store)

    working_dir = store.get_state().cwd
    print(f"[run_headless] Working dir: {working_dir}", file=sys.stderr)

    tools = get_all_tools()
    query_engine = QueryEngine(
        QueryEngineConfig(
            cwd=working_dir,
            tools=tools,
            get_app_state=store.get_state,
            set_app_state=lambda f: store.set_state(f),
        )
    )

    # Load initial messages if provided (for session continuity)
    if initial_messages:
        query_engine.messages = initial_messages

    tool_executor = get_tool_executor()

    if auto_allow:
        pm = get_permission_manager()
        for tool in tools:
            pm._permissions[tool.name] = ToolPermission(
                tool_name=tool.name, level=PermissionLevel.ALWAYS_ALLOW
            )

    tool_calls_log: list[dict[str, Any]] = []
    response_text = ""
    success = True

    try:
        current_prompt = prompt
        turn = 0
        for _ in range(max_iterations):
            turn += 1
            pending_tools: list[ToolUseMessage] = []

            async for result in query_engine.submit_message(current_prompt):
                msg = result.message
                if isinstance(msg, AssistantMessage):
                    if isinstance(msg.content, str):
                        if result.is_complete:
                            # Final message: use it if non-empty and longer than accumulated
                            # This handles case where accumulated content has more detail
                            if msg.content and len(msg.content) >= len(response_text):
                                response_text = msg.content
                            # else: keep accumulated response_text
                        else:
                            # Accumulate streaming content
                            if msg.content:
                                response_text += msg.content
                elif isinstance(msg, ToolUseMessage):
                    pending_tools.append(msg)

            if not pending_tools:
                break

            for tool_idx, tool_msg in enumerate(pending_tools, 1):
                if not json_mode:
                    tool_progress = f"[turn {turn}/{max_iterations}]"
                    if len(pending_tools) > 1:
                        tool_progress += f" [tool {tool_idx}/{len(pending_tools)}]"
                    print(f"🔧 {tool_progress} {tool_msg.name}", flush=True)
                context = ToolUseContext(
                    get_app_state=store.get_state, set_app_state=lambda f: store.set_state(f)
                )
                exec_result = await tool_executor.execute_tool_by_name(
                    tool_msg.name, tool_msg.input, context
                )
                result_content = ""
                if exec_result.success and exec_result.result:
                    result_content = (
                        str(exec_result.result.data) if exec_result.result.data else "Success"
                    )
                else:
                    result_content = exec_result.message
                    success = False

                tool_calls_log.append(
                    {
                        "tool": tool_msg.name,
                        "input": tool_msg.input,
                        "success": exec_result.success,
                        "result": result_content,
                    }
                )

                query_engine.add_tool_result(
                    tool_msg.tool_use_id, result_content, is_error=not exec_result.success
                )

            current_prompt = "Please continue based on the tool results above."
    except Exception as e:
        success = False
        response_text = f"Error: {e}"

    # Convert Pydantic messages to plain dicts for JSON serialization
    serializable_messages = []
    for msg in query_engine.messages:
        if hasattr(msg, "model_dump"):
            # Use mode='json' to convert UUID/datetime to strings
            serializable_messages.append(msg.model_dump(mode="json"))
        elif hasattr(msg, "dict"):
            d = msg.dict()
            # Convert UUID and datetime to strings
            for k, v in d.items():
                if hasattr(v, "__str__") and not isinstance(v, (str, int, float, bool, list, dict)):
                    d[k] = str(v)
            serializable_messages.append(d)
        elif isinstance(msg, dict):
            serializable_messages.append(msg)
        else:
            serializable_messages.append(
                {
                    "type": str(getattr(msg, "type", "unknown")),
                    "content": str(getattr(msg, "content", "")),
                }
            )

    output = {
        "response": response_text,
        "tool_calls": tool_calls_log,
        "success": success,
        "messages": serializable_messages,  # Include full message history for session persistence
    }

    if json_mode:
        print(json_mod.dumps(output, indent=2, default=str))
    else:
        print(response_text)

    return output
