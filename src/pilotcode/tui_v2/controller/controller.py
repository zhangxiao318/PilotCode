"""TUI Controller - bridges TUI with PilotCode core."""

import asyncio
from typing import AsyncIterator, Optional, Callable
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from pilotcode.query_engine import QueryEngine, QueryEngineConfig
from pilotcode.types.message import (
    UserMessage,
    AssistantMessage,
    ToolUseMessage,
)
from pilotcode.tools.registry import get_all_tools
from pilotcode.tools.base import ToolUseContext

try:
    from pilotcode.tools.bash_tool import is_read_only_command
except ImportError:
    # Fallback if bash_tool is not available
    def is_read_only_command(command: str) -> bool:
        return False


from pilotcode.permissions import get_tool_executor
from pilotcode.state.app_state import AppState
from pilotcode.components.repl import classify_task_complexity
from pilotcode.orchestration.adapter import MissionAdapter
from pilotcode.orchestration.report import (
    format_plan,
    format_progress,
    format_completion,
    format_failure,
    format_task_event,
    _STATE_EMOJI,
)


class ToolDeniedError(Exception):
    """Raised when user denies a tool execution. Stops the current tool batch."""

    def __init__(self, message: str, stop_task: bool = True):
        super().__init__(message)
        self.stop_task = stop_task


class UIMessageType(Enum):
    """UI message types."""

    USER = auto()
    ASSISTANT = auto()
    TOOL_USE = auto()
    TOOL_RESULT = auto()
    SYSTEM = auto()
    ERROR = auto()


@dataclass
class UIMessage:
    """Message for UI display."""

    type: UIMessageType
    content: str
    metadata: dict = None
    is_streaming: bool = False
    is_complete: bool = True

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class TUIController:
    """Controller that bridges TUI with PilotCode core functionality."""

    def __init__(
        self,
        get_app_state: Optional[Callable[[], AppState]] = None,
        set_app_state: Optional[Callable[[Callable[[AppState], AppState]], None]] = None,
        auto_allow: bool = False,
        max_iterations: int = 50,
    ):
        self.get_app_state = get_app_state
        self.set_app_state = set_app_state
        self.auto_allow = auto_allow
        self.max_iterations = max_iterations

        self.query_engine: Optional[QueryEngine] = None
        self.tool_executor = get_tool_executor()
        self._permission_callback: Optional[Callable[[str, dict], asyncio.Future]] = None

        # Session-level permission cache: {tool_name: allowed}
        self._session_permissions: dict[str, bool] = {}

        # Flag to abort the current turn when user denies a tool
        self._abort_current_turn: bool = False

        # Pending notifications from QueryEngine (e.g., auto-compact)
        self._pending_notifications: list[tuple[str, dict]] = []

        self._init_engine()

    # ------------------------------------------------------------------
    # Four-layer rendering helpers
    # ------------------------------------------------------------------

    def _render_status(self, event_type: str, **kwargs) -> None:
        """Status Layer: persistent state indicators (placeholder)."""
        pass

    def _render_conversational_user(self, content: str) -> UIMessage:
        """Conversational Layer: user input."""
        return UIMessage(
            type=UIMessageType.USER,
            content=content,
            is_complete=True,
        )

    def _render_conversational_assistant(
        self, content: str, is_streaming: bool, is_complete: bool
    ) -> UIMessage:
        """Conversational Layer: assistant response."""
        return UIMessage(
            type=UIMessageType.ASSISTANT,
            content=content,
            is_streaming=is_streaming,
            is_complete=is_complete,
        )

    def _render_conversational_tool_use(
        self,
        tool_name: str,
        tool_input: dict,
        tool_use_id: str,
        iteration: int,
        tool_idx: int,
        total_tools: int,
    ) -> UIMessage:
        """Conversational Layer: tool call notification."""
        is_safe = self._is_safe_tool(tool_name, tool_input if isinstance(tool_input, dict) else {})
        return UIMessage(
            type=UIMessageType.TOOL_USE,
            content=f"{tool_name}",
            metadata={
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_use_id": tool_use_id,
                "is_safe": is_safe,
                "turn": iteration,
                "max_turns": self.max_iterations,
                "tool_index": tool_idx,
                "total_tools": total_tools,
            },
            is_complete=False,
        )

    def _render_system(self, event_type: str, content: str = "", **kwargs) -> UIMessage:
        """System Layer: notices, warnings, errors."""
        return UIMessage(
            type=UIMessageType.SYSTEM,
            content=content,
            is_complete=True,
        )

    # ------------------------------------------------------------------

    def _init_engine(self) -> None:
        """Initialize QueryEngine."""

        def _on_notify(event_type: str, payload: dict) -> None:
            self._pending_notifications.append((event_type, payload))

        tools = get_all_tools()
        from pilotcode.utils.config import get_global_config

        global_cfg = get_global_config()
        config = QueryEngineConfig(
            cwd=str(Path.cwd()),
            tools=tools,
            get_app_state=self.get_app_state,
            set_app_state=self.set_app_state,
            auto_compact=True,
            context_window=8000,
            on_notify=_on_notify,
            auto_review=global_cfg.auto_review,
            max_review_iterations=global_cfg.max_review_iterations,
        )
        self.query_engine = QueryEngine(config=config)

        # Setup auto-allow if requested
        if self.auto_allow:
            self._setup_auto_allow(tools)

    def _setup_auto_allow(self, tools) -> None:
        """Setup auto-allow for all tools."""
        from pilotcode.permissions import get_permission_manager, ToolPermission, PermissionLevel

        pm = get_permission_manager()
        for tool in tools:
            pm._permissions[tool.name] = ToolPermission(
                tool_name=tool.name, level=PermissionLevel.ALWAYS_ALLOW
            )

    def set_permission_callback(
        self, callback: Callable[[str, dict], asyncio.Future[bool]]
    ) -> None:
        """Set callback for permission requests.

        The callback receives (tool_name, params) and should return a Future[bool].
        """
        self._permission_callback = callback

    async def _run_pevr_mode(self, text: str) -> AsyncIterator[UIMessage]:
        """Run a complex task in P-EVR orchestration mode.

        1. Plans the mission via LLM
        2. Executes tasks with progress reporting
        3. Returns completion/failure summary
        """
        import asyncio

        cancel_event = asyncio.Event()
        adapter = MissionAdapter(cancel_event=cancel_event)

        mission_displayed = False
        last_progress = ""

        def progress_cb(event_type: str, data: dict) -> None:
            nonlocal mission_displayed, last_progress
            # Buffer events; actual yielding happens in the generator below
            self._pevr_events.append((event_type, data))

        self._pevr_events: list[tuple[str, dict]] = []

        # Start mission execution in background
        mission_task = asyncio.create_task(adapter.run(text, progress_callback=progress_cb))

        yield UIMessage(
            type=UIMessageType.SYSTEM,
            content="Task classified as complex — entering PLAN mode with structured execution.",
        )

        # Poll for progress events while mission runs
        result: dict | None = None
        while not mission_task.done():
            # Drain event buffer
            while self._pevr_events:
                event_type, data = self._pevr_events.pop(0)

                if event_type == "mission:planned" and not mission_displayed:
                    mission_displayed = True
                    # We don't have the mission object here, so show a generic message
                    # The real plan display will come from the final result
                    pass
                elif event_type in (
                    "task:started",
                    "task:verified",
                    "task:rejected",
                    "task:needs_rework",
                ):
                    msg = format_task_event(event_type, data)
                    yield UIMessage(type=UIMessageType.SYSTEM, content=msg)
                elif event_type == "mission:completed":
                    pass  # Will handle after task finishes
                elif event_type == "mission:blocked":
                    msg = format_task_event(event_type, data)
                    yield UIMessage(type=UIMessageType.SYSTEM, content=msg)

            await asyncio.sleep(0.2)

        # Get final result
        try:
            result = mission_task.result()
        except Exception as exc:
            result = {"success": False, "error": str(exc)}

        # Show final summary
        if result and result.get("success"):
            summary = format_completion(result)
            yield UIMessage(type=UIMessageType.ASSISTANT, content=summary)
        else:
            error = result.get("error", "Unknown error") if result else "Mission failed"
            summary = format_failure(result or {}, error)
            yield UIMessage(type=UIMessageType.ERROR, content=summary)

        # Also show the raw conversation response if available
        mission_dict = result.get("mission", {}) if result else {}
        phases = mission_dict.get("phases", [])
        if phases:
            lines = ["📋 Mission Plan Executed:"]
            for p in phases:
                lines.append(f"  • Phase: {p.get('title', 'Untitled')}")
                for t in p.get("tasks", []):
                    state = t.get("state", "unknown")
                    emoji = _STATE_EMOJI.get(state, "❓")
                    lines.append(f"    {emoji} {t.get('title', t.get('id', '?'))}")
            yield UIMessage(type=UIMessageType.SYSTEM, content="\n".join(lines))

    async def submit_message(self, text: str) -> AsyncIterator[UIMessage]:
        """Submit a message and yield UI messages.

        This handles the full flow:
        1. Send message to QueryEngine
        2. Stream back assistant responses
        3. Intercept tool calls and request permission
        4. Execute tools and return results
        5. Continue until complete
        """
        if not self.query_engine:
            yield UIMessage(type=UIMessageType.ERROR, content="Query engine not initialized")
            return

        # Auto-detect task complexity for the first user message
        if len(self.query_engine.messages) == 0:
            mode = await classify_task_complexity(text)
            if mode == "PLAN":
                async for msg in self._run_pevr_mode(text):
                    yield msg
                return

        iteration = 0
        current_prompt = text
        accumulated_content = ""

        while iteration < self.max_iterations:
            iteration += 1
            pending_tools = []

            # Flush any pending notifications from QueryEngine (e.g., auto-compact)
            while self._pending_notifications:
                event_type, payload = self._pending_notifications.pop(0)
                if event_type == "auto_compact":
                    saved = payload.get("tokens_saved", 0)
                    cleared = payload.get("tool_results_cleared", 0)
                    if payload.get("fallback"):
                        content = f"🔄 Auto-compacted context (fallback, ~{saved} tokens saved)"
                    elif cleared > 0:
                        content = f"🔄 Auto-compacted context ({cleared} old tool results cleared, ~{saved} tokens saved)"
                    else:
                        content = f"🔄 Auto-compacted context (~{saved} tokens saved)"
                    yield UIMessage(type=UIMessageType.SYSTEM, content=content)

            async for result in self.query_engine.submit_message(current_prompt):
                msg = result.message

                if isinstance(msg, UserMessage):
                    # -- Conversational Layer: user input --
                    yield self._render_conversational_user(
                        msg.content if isinstance(msg.content, str) else str(msg.content)
                    )

                elif isinstance(msg, AssistantMessage):
                    # Handle streaming vs final message differently
                    if result.is_complete:
                        accumulated_content = msg.content or accumulated_content
                    else:
                        if msg.content:
                            accumulated_content += msg.content

                    # -- Conversational Layer: assistant response --
                    yield self._render_conversational_assistant(
                        accumulated_content,
                        is_streaming=not result.is_complete,
                        is_complete=result.is_complete,
                    )

                elif isinstance(msg, ToolUseMessage):
                    # Collect tool calls for batch processing
                    pending_tools.append(msg)
                    # -- Conversational Layer: tool use --
                    yield self._render_conversational_tool_use(
                        msg.name,
                        msg.input if isinstance(msg.input, dict) else {},
                        msg.tool_use_id,
                        iteration,
                        len(pending_tools),
                        len(pending_tools),
                    )

            # Process all pending tools
            if not pending_tools:
                break

            try:
                for tool_msg in pending_tools:
                    async for ui_msg in self._execute_tool(tool_msg):
                        yield ui_msg
            except ToolDeniedError as e:
                # User denied a tool; stop executing remaining tools in this batch
                if e.stop_task:
                    self._abort_current_turn = True
                    yield UIMessage(
                        type=UIMessageType.SYSTEM,
                        content="⛔ Tool execution denied by user. Task stopped.",
                    )
                    break
                # Otherwise just skip remaining tools and let LLM respond to the error

            if self._abort_current_turn:
                break

            # Continue with empty prompt to get LLM response to tool results
            current_prompt = ""
            accumulated_content = ""
        else:
            # -- System Layer: max iterations reached --
            yield self._render_system(
                "max_iterations_reached",
                content=f"⏹️  Reached maximum tool iterations ({self.max_iterations}). Task paused. Send another message to continue.",
            )

    def _is_safe_tool(self, tool_name: str, params: dict) -> bool:
        """Check if a tool operation is safe (read-only/non-destructive).

        Returns True for:
        - Bash commands that are read-only (ls, cat, date, pwd, etc.)
        - File reading operations
        - Information queries
        """
        from pilotcode.permissions.permission_manager import PermissionManager

        if tool_name in PermissionManager.SAFE_TOOLS:
            return True

        if tool_name == "Bash":
            command = params.get("command", "")
            return is_read_only_command(command)

        return False

    def _normalize_tool_name(self, name: str) -> str:
        """Normalize tool name to ensure consistent cache keys.

        LLM may return tool names as 'bash', 'Bash', or aliases like 'shell'.
        This normalizes them to the canonical tool name.
        """
        from pilotcode.tools.registry import get_all_tools

        # Direct match
        for tool in get_all_tools():
            if tool.name == name:
                return tool.name
            if name in tool.aliases:
                return tool.name

        # Case-insensitive match
        name_lower = name.lower()
        for tool in get_all_tools():
            if tool.name.lower() == name_lower:
                return tool.name
            for alias in tool.aliases:
                if alias.lower() == name_lower:
                    return tool.name

        # Return original if no match found
        return name

    async def _execute_tool(self, tool_msg: ToolUseMessage) -> AsyncIterator[UIMessage]:
        """Execute a tool and yield UI messages."""
        # Normalize tool name for consistent cache keys
        tool_name = self._normalize_tool_name(tool_msg.name)
        params = tool_msg.input if isinstance(tool_msg.input, dict) else {}

        # Check if tool is safe (read-only) - skip permission for safe operations
        is_safe = self._is_safe_tool(tool_name, params)

        # Check session-level permission cache
        if tool_name in self._session_permissions:
            allowed = self._session_permissions[tool_name]
            if not allowed:
                self.query_engine.add_tool_result(
                    tool_msg.tool_use_id, "Tool execution denied by session policy", is_error=True
                )
                yield UIMessage(
                    type=UIMessageType.TOOL_RESULT,
                    content="Denied (session policy)",
                    metadata={"tool_name": tool_name, "error": True},
                    is_complete=True,
                )
                return
            # Allowed by session policy, continue to execute

        # Request permission if:
        # 1. Callback is set AND
        # 2. Not auto-allow AND
        # 3. Tool is not safe (destructive operation) AND
        # 4. No session-level permission set
        elif self._permission_callback and not self.auto_allow and not is_safe:
            # Import here to avoid circular dependency
            from pilotcode.tui_v2.components.permission_inline import PermissionResult

            result = await self._permission_callback(tool_name, params)

            # Update session cache if user chose "Allow for this session"
            if isinstance(result, PermissionResult) and result.for_session:
                self._session_permissions[tool_name] = result.allowed

            # If user denied, stop here and do not execute this tool or subsequent ones
            if isinstance(result, PermissionResult) and not result.allowed:
                self.query_engine.add_tool_result(
                    tool_msg.tool_use_id,
                    "Tool execution denied by user. Proceed with your alternative read-only approach immediately without explaining your plan first.",
                    is_error=True,
                )
                yield UIMessage(
                    type=UIMessageType.TOOL_RESULT,
                    content="Denied (user)",
                    metadata={"tool_name": tool_name, "error": True},
                    is_complete=True,
                )
                # Option 3 (DENY) = skip this batch but let LLM try alternate approaches
                # Option 4 (DENY_SESSION) = stop the entire task
                stop_task = result.for_session
                raise ToolDeniedError(f"User denied tool: {tool_name}", stop_task=stop_task)

        # Execute the tool
        try:
            ctx = ToolUseContext(get_app_state=self.get_app_state, set_app_state=self.set_app_state)

            # Permission already granted by TUI - set permission_manager callback
            # to always allow to avoid double permission prompt from tool_executor
            from pilotcode.permissions.permission_manager import PermissionLevel

            original_callback = self.tool_executor.permission_manager._permission_callback

            async def _always_allow(*args, **kwargs):
                return PermissionLevel.ALLOW

            self.tool_executor.permission_manager.set_permission_callback(_always_allow)

            # TUI v2 uses textual which fully controls the terminal;
            # direct print() would corrupt the UI. We skip real-time bash
            # progress streaming here and rely on the final tool result.
            try:
                result = await self.tool_executor.execute_tool_by_name(tool_name, params, ctx)
            finally:
                # Restore original callback
                self.tool_executor.permission_manager.set_permission_callback(original_callback)

            # Extract output
            if result.success and result.result:
                if hasattr(result.result, "data"):
                    tool_data = result.result.data
                    if hasattr(tool_data, "stdout"):
                        output = tool_data.stdout
                    else:
                        output = str(tool_data)
                else:
                    output = str(result.result)
            else:
                output = result.message or "Tool execution failed"

            # Add result to query engine
            self.query_engine.add_tool_result(
                tool_msg.tool_use_id, output, is_error=not result.success
            )

            # Yield result message
            yield UIMessage(
                type=UIMessageType.TOOL_RESULT,
                content=output[:500] if len(output) > 500 else output,
                metadata={
                    "tool_name": tool_name,
                    "full_output": output,
                    "error": not result.success,
                },
                is_complete=True,
            )

        except Exception as e:
            error_msg = str(e)
            self.query_engine.add_tool_result(tool_msg.tool_use_id, error_msg, is_error=True)
            yield UIMessage(
                type=UIMessageType.ERROR,
                content=error_msg,
                metadata={"tool_name": tool_name},
                is_complete=True,
            )

    def save_session(self, path: str) -> bool:
        """Save current session."""
        if self.query_engine:
            try:
                self.query_engine.save_session(path)
                return True
            except Exception:
                return False
        return False

    def load_session(self, path: str) -> bool:
        """Load session from file."""
        if self.query_engine:
            try:
                return self.query_engine.load_session(path)
            except Exception:
                return False
        return False

    def clear_history(self) -> None:
        """Clear conversation history."""
        if self.query_engine:
            self.query_engine.clear_history()

    def get_token_count(self) -> int:
        """Get current token count."""
        if self.query_engine:
            return self.query_engine.count_tokens()
        return 0
