"""TUI Controller - bridges TUI with PilotCode core."""

import asyncio
from typing import AsyncIterator, Optional, Callable
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from pilotcode.query_engine import QueryEngine, QueryEngineConfig
from pilotcode.types.message import (
    MessageType,
    UserMessage,
    AssistantMessage,
    ToolUseMessage,
    ToolResultMessage,
    SystemMessage,
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


class MessageType(Enum):
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

    type: MessageType
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
        max_iterations: int = 25,
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

        self._init_engine()

    def _init_engine(self) -> None:
        """Initialize QueryEngine."""
        tools = get_all_tools()
        config = QueryEngineConfig(
            cwd=str(Path.cwd()),
            tools=tools,
            get_app_state=self.get_app_state,
            set_app_state=self.set_app_state,
            auto_compact=True,
            max_tokens=8000,
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
            yield UIMessage(type=MessageType.ERROR, content="Query engine not initialized")
            return

        iteration = 0
        current_prompt = text
        accumulated_content = ""

        while iteration < self.max_iterations:
            iteration += 1
            pending_tools = []

            async for result in self.query_engine.submit_message(current_prompt):
                msg = result.message

                if isinstance(msg, UserMessage):
                    # User message - display it
                    yield UIMessage(
                        type=MessageType.USER,
                        content=msg.content if isinstance(msg.content, str) else str(msg.content),
                        is_complete=True,
                    )

                elif isinstance(msg, AssistantMessage):
                    # Handle streaming vs final message differently
                    if result.is_complete:
                        # Final message: QueryEngine returns complete content
                        # Use it directly instead of accumulating
                        accumulated_content = msg.content or accumulated_content
                    else:
                        # Streaming: accumulate content from chunks
                        if msg.content:
                            accumulated_content += msg.content

                    # Yield update for assistant messages
                    yield UIMessage(
                        type=MessageType.ASSISTANT,
                        content=accumulated_content,
                        is_streaming=not result.is_complete,
                        is_complete=result.is_complete,
                    )

                elif isinstance(msg, ToolUseMessage):
                    # Collect tool calls for batch processing
                    pending_tools.append(msg)
                    # Check if tool is safe for visual indication
                    is_safe = self._is_safe_tool(
                        msg.name, msg.input if isinstance(msg.input, dict) else {}
                    )
                    # Add progress info
                    tool_idx = len(pending_tools)
                    progress_info = f"[turn {iteration}/{self.max_iterations}]"
                    yield UIMessage(
                        type=MessageType.TOOL_USE,
                        content=f"{msg.name}",
                        metadata={
                            "tool_name": msg.name,
                            "tool_input": msg.input,
                            "tool_use_id": msg.tool_use_id,
                            "is_safe": is_safe,  # Add safety indicator
                            "turn": iteration,
                            "max_turns": self.max_iterations,
                            "tool_index": tool_idx,
                            "total_tools": len(pending_tools),
                        },
                        is_complete=False,
                    )

            # Process all pending tools
            if not pending_tools:
                break

            for tool_msg in pending_tools:
                async for ui_msg in self._execute_tool(tool_msg):
                    yield ui_msg

            # Continue with empty prompt to get LLM response to tool results
            current_prompt = ""
            accumulated_content = ""

    def _is_safe_tool(self, tool_name: str, params: dict) -> bool:
        """Check if a tool operation is safe (read-only/non-destructive).

        Returns True for:
        - Bash commands that are read-only (ls, cat, date, pwd, etc.)
        - File reading operations
        - Information queries
        """
        if tool_name == "Bash":
            command = params.get("command", "")
            return is_read_only_command(command)

        # Add other safe tool checks here
        # Example: FileRead is always safe
        # if tool_name == "FileRead":
        #     return True

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
                    type=MessageType.TOOL_RESULT,
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
                type=MessageType.TOOL_RESULT,
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
                type=MessageType.ERROR,
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
