"""SessionService - shared Controller for the MVC service layer.

Extracts the duplicated business logic from SimpleCLI, TUIController, and
WebServer into a single service class. Communicates with any View through
the three-channel UIProtocol:

    Channel 1 (on_block_event): conversational + system layer lifecycle
    Channel 2 (on_status_update): persistent UI region updates
    Channel 3 (request_permission / request_user_input): interactive callbacks
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from pilotcode.query_engine import QueryEngine, QueryEngineConfig
from pilotcode.types.message import (
    UserMessage,
    AssistantMessage,
    ToolUseMessage,
    SystemMessage,
)
from pilotcode.services.fileedit_compensation import FileEditCompensationTracker
from pilotcode.tools.registry import get_core_tools
from pilotcode.tools.base import ToolUseContext
from pilotcode.permissions import get_tool_executor
from pilotcode.state.app_state import AppState

try:
    from pilotcode.tools.bash_tool import is_read_only_command, execute_bash
except ImportError:

    def is_read_only_command(command: str) -> bool:
        return False

    async def execute_bash(command: str, cwd: str | None = None, **kwargs) -> None:  # type: ignore
        return None


from .protocol import (
    BlockEvent,
    BlockKind,
    BlockPhase,
    StatusUpdate,
    UIProtocol,
)
from .config import SessionConfig, CommandResult, CommandAction

logger = logging.getLogger("pilotcode.ui.session_service")


class SessionService:
    """Shared session processing service -- the Controller in MVC.

    Owns the business logic that is currently duplicated across
    SimpleCLI, TUIController, and WebServer.

    Communicates with any View through the three-channel UIProtocol:
    - Channel 1 (on_block_event): yields BlockEvent for conversational/system rendering
    - Channel 2 (on_status_update): emits StatusUpdate for persistent UI regions
    - Channel 3 (request_permission/request_user_input): interactive callbacks
    """

    def __init__(
        self,
        ui: UIProtocol,
        config: SessionConfig,
        get_app_state: Callable[[], AppState] | None = None,
        set_app_state: Callable[[Callable[[AppState], AppState]], None] | None = None,
    ):
        self.ui = ui
        self.config = config
        self.get_app_state = get_app_state
        self.set_app_state = set_app_state

        self.query_engine: Optional[QueryEngine] = None
        self.tool_executor = get_tool_executor()

        # Session-level permission cache: {tool_name: allowed}
        self._session_permissions: dict[str, bool] = {}

        # Flag to abort the current turn when user denies a tool
        self._abort_current_turn: bool = False

        # Pending notifications from QueryEngine (e.g., auto-compact)
        self._pending_notifications: list[tuple[str, dict]] = []

        # P0: Shared FileEdit compensation tracker
        self._fileedit_tracker = FileEditCompensationTracker(
            get_app_state() if get_app_state else None
        )

        # Session persistence state
        self._session_id: str = ""
        self._session_name: str = ""

        # Block ID counter for unique block identification
        self._block_counter: int = 0

        # Cancel event for mission interruption
        self._cancel_event: asyncio.Event | None = None

        # Last echoed todo/plan status (avoid duplicate echo)
        self._last_todo_plan_echo: str = ""

        # Initialize engine
        self._init_engine()

    # ------------------------------------------------------------------
    # Block ID generation
    # ------------------------------------------------------------------

    def _next_block_id(self, kind: BlockKind) -> str:
        """Generate a unique block ID for the given kind."""
        self._block_counter += 1
        return f"{kind.value}_{self._block_counter}"

    # ------------------------------------------------------------------
    # Engine initialization (extracted from all three UIs)
    # ------------------------------------------------------------------

    def _init_engine(self) -> None:
        """Initialize QueryEngine and session.

        Unified from:
        - simple_cli.py:76-138
        - controller.py:250-282
        - server.py:348-423
        """
        cwd = self.config.cwd or str(Path.cwd())
        resolved_cwd = str(Path(cwd).resolve())
        self.config.cwd = resolved_cwd

        def _on_notify(event_type: str, payload: dict) -> None:
            self._pending_notifications.append((event_type, payload))

        tools = get_core_tools(resolved_cwd)

        from pilotcode.utils.config import get_global_config

        global_cfg = get_global_config()
        engine_config = QueryEngineConfig(
            cwd=resolved_cwd,
            tools=tools,
            get_app_state=self.get_app_state,
            set_app_state=self.set_app_state,
            auto_compact=self.config.auto_compact,
            on_notify=_on_notify,
            auto_review=global_cfg.auto_review,
            max_review_iterations=global_cfg.max_review_iterations,
            max_turns=self.config.max_iterations,
            context_window=self.config.context_window,
            permission_mode=self.config.permission_mode,
        )
        self.query_engine = QueryEngine(config=engine_config)

        # Setup auto-allow if requested
        if self.config.auto_allow:
            self._setup_auto_allow(tools)

        # Initialize session
        self._init_session()

    def _init_session(self) -> None:
        """Create a new session or restore an existing one.

        Behavior controlled by SessionConfig:
        - restore_on_start=True AND --restore flag is set: restore the last session for this project
        - session_id set: restore a specific session by ID
        - both False/empty (default): create a fresh session

        Unified from: controller.py:284-335, simple_cli.py:536-583
        """
        from pilotcode.services.session_persistence import (
            get_session_persistence,
            load_session,
        )

        cwd = self.config.cwd or str(Path.cwd())
        persistence = get_session_persistence()

        # Priority 1: Restore a specific session by ID
        if self.config.session_id:
            result = load_session(self.config.session_id)
            if result:
                messages, metadata = result
                self.query_engine.messages[:] = messages
                self.query_engine._token_mgr.reset_cache()
                self._session_id = self.config.session_id
                self._session_name = metadata.get("name", self.config.session_id)
                restored_cwd = metadata.get("project_path") or cwd
                if restored_cwd:
                    self._update_session_cwd(restored_cwd)
                self._notify_session_change()
                return
            logger.warning(
                "Session %s not found, creating new session",
                self.config.session_id,
            )

        # Priority 2: Restore last session only if explicitly requested (restore_on_start=True)
        # This ensures we only restore when explicitly requested, not unconditionally
        if self.config.restore_on_start:
            last = persistence.get_last_session(project_path=cwd)
            if not last:
                last = persistence.get_last_session(project_path=None)  # fallback: any project
            if last:
                result = load_session(last.session_id)
                if result:
                    messages, metadata = result
                    self.query_engine.messages[:] = messages
                    self.query_engine._token_mgr.reset_cache()
                    self._session_id = last.session_id
                    self._session_name = metadata.get("name", last.session_id)
                    # Sync restored project directory
                    restored_cwd = metadata.get("project_path") or cwd
                    if restored_cwd:
                        self._update_session_cwd(restored_cwd)
                    self._notify_session_change()
                    return

        # Default: create a new session (as expected behavior)
        now = datetime.now()
        self._session_id = f"sess_{now.strftime('%Y%m%d_%H%M%S')}"
        self._session_name = f"Session {now.strftime('%Y-%m-%d %H:%M')}"
        self._notify_session_change()

    def _notify_session_change(self) -> None:
        """Update app_state with session info."""
        if self.set_app_state:

            def _update(state: AppState) -> AppState:
                return replace(
                    state,
                    session_id=self._session_id,
                    session_name=self._session_name,
                )

            self.set_app_state(_update)

    # ------------------------------------------------------------------
    # Auto-allow setup (extracted from SimpleCLI + TUIController)
    # ------------------------------------------------------------------

    def _setup_auto_allow(self, tools: list) -> None:
        """Setup auto-allow for all tools.

        Unified from: simple_cli.py:129-134, controller.py:370-378
        """
        from pilotcode.permissions import get_permission_manager, ToolPermission, PermissionLevel

        pm = get_permission_manager()
        for tool in tools:
            pm._permissions[tool.name] = ToolPermission(
                tool_name=tool.name, level=PermissionLevel.ALWAYS_ALLOW
            )

    # ------------------------------------------------------------------
    # Safe tool check (extracted from SimpleCLI + TUIController)
    # ------------------------------------------------------------------

    def _is_safe_tool(self, tool_name: str, params: dict) -> bool:
        """Check if a tool operation is safe (read-only/non-destructive).

        Unified from: simple_cli.py:390-406, controller.py:1008-1025
        """
        from pilotcode.permissions.permission_manager import PermissionManager

        if tool_name in PermissionManager.SAFE_TOOLS:
            return True

        if tool_name == "Bash":
            command = params.get("command", "")
            return is_read_only_command(command)

        return False

    # ------------------------------------------------------------------
    # Session CWD detection and update (extracted from TUIController + Web)
    # ------------------------------------------------------------------

    def _update_session_cwd(self, new_cwd: str) -> bool:
        """Update the session's working directory across all layers.

        Unified from: controller.py:219-248
        """
        new_cwd = os.path.expanduser(new_cwd)
        new_cwd = str(Path(new_cwd).resolve())
        old_cwd = self.config.cwd or str(Path.cwd())
        if new_cwd == old_cwd:
            return True
        try:
            os.chdir(new_cwd)
        except OSError:
            return False
        self.config.cwd = new_cwd
        if self.query_engine and self.query_engine.config:
            self.query_engine.config = replace(self.query_engine.config, cwd=new_cwd)
        if self.set_app_state:
            self.set_app_state(lambda s: replace(s, cwd=new_cwd))
        return True

    def _detect_and_update_cwd(self, text: str) -> str | None:
        """Detect workspace path in user message and update cwd if found.

        Returns the detected path, or None.
        """
        from pilotcode.components.repl import _extract_target_path

        detected = _extract_target_path(text)
        current_cwd = self.config.cwd or str(Path.cwd())
        if detected and detected != current_cwd:
            if os.path.isdir(detected):
                if self._update_session_cwd(detected):
                    return detected
        return None

    # ------------------------------------------------------------------
    # Main query loop (THE BIGGEST WIN - ~250 lines duplicated 3x -> 1x)
    # ------------------------------------------------------------------

    async def process_query(self, text: str) -> None:
        """Main query loop. Currently duplicated 3x across UIs.

        Instead of yielding events, this method directly calls
        self.ui.on_block_event() / self.ui.on_status_update() so the View
        receives events in real-time without buffering.

        Unified from:
        - simple_cli.py:641-900
        - controller.py:742-1006 (submit_message)
        - server.py:1956-2300 (process_query)
        """
        if not self.query_engine:
            await self.ui.on_error("Query engine not initialized")
            return

        # New user input = fresh context: reset FileEdit failure tracking
        self._fileedit_tracker.reset()
        self._abort_current_turn = False

        # Update processing status
        await self.ui.on_status_update(StatusUpdate(is_processing=True))

        # ! shell escape — execute directly, bypass LLM entirely
        if text.startswith("!"):
            shell_cmd = text[1:].strip()
            if not shell_cmd:
                await self.ui.on_block_event(
                    BlockEvent(
                        block_id=self._next_block_id(BlockKind.SYSTEM),
                        kind=BlockKind.SYSTEM,
                        phase=BlockPhase.CLOSE,
                        content="Empty shell command",
                    )
                )
            else:
                await self.ui.on_block_event(
                    BlockEvent(
                        block_id=self._next_block_id(BlockKind.SYSTEM),
                        kind=BlockKind.SYSTEM,
                        phase=BlockPhase.OPEN,
                        content=f"$ {shell_cmd}",
                    )
                )
                try:
                    proc = await asyncio.create_subprocess_shell(
                        shell_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=self.config.cwd or None,
                    )
                    try:
                        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
                    except asyncio.TimeoutError:
                        proc.kill()
                        output = "Shell command timed out (30s)"
                    else:
                        output = (stdout or stderr or b"").decode("utf-8", errors="replace")
                        if not output.strip():
                            output = "(no output)"
                        if len(output) > 5000:
                            output = output[:5000] + f"\n... (truncated, {len(output)} chars total)"
                except Exception as e:
                    output = f"Shell command failed: {e}"
                await self.ui.on_block_event(
                    BlockEvent(
                        block_id=self._next_block_id(BlockKind.SYSTEM),
                        kind=BlockKind.SYSTEM,
                        phase=BlockPhase.CLOSE,
                        content=output,
                    )
                )
            await self.ui.on_status_update(
                StatusUpdate(
                    is_processing=False,
                    token_count=self.get_token_count(),
                    context_window=self._get_context_window(),
                )
            )
            return

        # Detect CWD from user message
        detected_cwd = self._detect_and_update_cwd(text)
        if detected_cwd:
            await self.ui.on_block_event(
                BlockEvent(
                    block_id=self._next_block_id(BlockKind.SYSTEM),
                    kind=BlockKind.SYSTEM,
                    phase=BlockPhase.CLOSE,
                    content=f"📁 Working directory updated to: {detected_cwd}",
                )
            )

        # Check and compress context if needed
        await self._check_and_compress_context()

        iteration = 0
        max_iterations = self.config.max_iterations
        current_prompt = text
        accumulated_content = ""
        max_reached = False

        try:
            while iteration < max_iterations:
                iteration += 1
                pending_tools: list[ToolUseMessage] = []

                # Flush pending notifications from QueryEngine
                await self._flush_notifications()

                # Create streaming assistant block
                assistant_block_id = self._next_block_id(BlockKind.ASSISTANT)
                await self.ui.on_block_event(
                    BlockEvent(
                        block_id=assistant_block_id,
                        kind=BlockKind.ASSISTANT,
                        phase=BlockPhase.OPEN,
                    )
                )

                # Process through query engine with streaming
                async for result in self.query_engine.submit_message(current_prompt):
                    msg = result.message

                    if isinstance(msg, UserMessage):
                        # Skip user messages in streaming output
                        continue

                    elif isinstance(msg, AssistantMessage):
                        # Handle streaming vs complete message
                        if result.is_complete:
                            if isinstance(msg.content, str) and msg.content:
                                if len(msg.content) >= len(accumulated_content):
                                    accumulated_content = msg.content
                        else:
                            if msg.content:
                                accumulated_content += msg.content

                        # Emit delta for streaming
                        await self.ui.on_block_event(
                            BlockEvent(
                                block_id=assistant_block_id,
                                kind=BlockKind.ASSISTANT,
                                phase=(
                                    BlockPhase.DELTA if not result.is_complete else BlockPhase.CLOSE
                                ),
                                content=accumulated_content,
                            )
                        )

                    elif isinstance(msg, ToolUseMessage):
                        # Collect tool calls for batch processing
                        pending_tools.append(msg)
                        # Emit tool call block
                        tool_block_id = self._next_block_id(BlockKind.TOOL_CALL)
                        await self.ui.on_block_event(
                            BlockEvent(
                                block_id=tool_block_id,
                                kind=BlockKind.TOOL_CALL,
                                phase=BlockPhase.OPEN,
                                content=msg.name,
                                metadata={
                                    "tool_name": msg.name,
                                    "tool_input": msg.input if isinstance(msg.input, dict) else {},
                                    "tool_use_id": msg.tool_use_id,
                                    "iteration": iteration,
                                    "max_iterations": max_iterations,
                                },
                            )
                        )

                    # Handle thinking/reasoning messages
                    elif msg.__class__.__name__ == "ThinkingMessage" or (
                        hasattr(msg, "thinking") and msg.thinking
                    ):
                        thinking_content = getattr(msg, "thinking", "") or (
                            msg.content if hasattr(msg, "content") else ""
                        )
                        if thinking_content:
                            await self.ui.on_block_event(
                                BlockEvent(
                                    block_id=self._next_block_id(BlockKind.THINKING),
                                    kind=BlockKind.THINKING,
                                    phase=BlockPhase.DELTA,
                                    content=thinking_content,
                                )
                            )

                    # Drain event bus for reasoning content (DeepSeek thinking mode)
                    await self._drain_reasoning_events()

                # If no tools to execute, we're done
                if not pending_tools:
                    break

                # Execute all pending tools
                current_prompt = await self._execute_tools(pending_tools)

                if self._abort_current_turn:
                    break

                # Continue loop to get LLM response with tool results
                accumulated_content = ""
            else:
                # Loop exited because max_iterations was reached
                max_reached = True

            if max_reached:
                await self.ui.on_block_event(
                    BlockEvent(
                        block_id=self._next_block_id(BlockKind.SYSTEM),
                        kind=BlockKind.SYSTEM,
                        phase=BlockPhase.CLOSE,
                        content=(
                            f"⏹️  Reached maximum tool iterations ({max_iterations}). "
                            f"Task paused. Send another message to continue."
                        ),
                    )
                )

        except Exception as e:
            logger.exception("Error in process_query")
            await self.ui.on_error(f"Error processing query: {e}")
        finally:
            # Update status
            await self.ui.on_status_update(
                StatusUpdate(
                    is_processing=False,
                    token_count=self.get_token_count(),
                    context_window=self._get_context_window(),
                )
            )

            # Auto-save if enabled
            if self.config.auto_save:
                self._auto_save()

            # Echo todo/plan status if changed (visible across all UIs)
            await self._echo_todo_plan_status()

    async def _echo_todo_plan_status(self) -> None:
        """Echo todo/plan status as SYSTEM block if state changed."""
        status = self._get_todo_plan_status()
        if status and status != self._last_todo_plan_echo:
            self._last_todo_plan_echo = status
            try:
                await self.ui.on_block_event(
                    BlockEvent(
                        block_id=self._next_block_id(BlockKind.SYSTEM),
                        kind=BlockKind.SYSTEM,
                        phase=BlockPhase.CLOSE,
                        content=status,
                    )
                )
            except Exception:
                pass

    def _get_todo_plan_status(self) -> str:
        """Get formatted todo/plan status, or empty string if nothing active.

        Uses session-scoped plan state via self._session_id.
        Todos are project-wide and stored globally.
        """
        lines = []

        # Load project-wide todos
        try:
            from pilotcode.tools.todo_tool import load_todos

            todos = load_todos()
            if todos:
                total = len(todos)
                done = sum(1 for t in todos.values() if t.get("status") == "done")
                lines.append(f"📋 TODO: {done}/{total}    ")
        except Exception:
            pass

        # Load session-scoped plan
        try:
            from pilotcode.tools.plan_mode_tools import get_plan_state

            state = get_plan_state(self._session_id)
            if state.is_active:
                total = len(state.current_plan)
                completed = len(state.completed_steps)
                lines.append(f"▸ Plan: {completed}/{total} steps")
        except Exception:
            pass

        return "".join(lines).rstrip()

    async def _flush_notifications(self) -> None:
        """Flush pending notifications from QueryEngine as SYSTEM blocks."""
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
                await self.ui.on_block_event(
                    BlockEvent(
                        block_id=self._next_block_id(BlockKind.SYSTEM),
                        kind=BlockKind.SYSTEM,
                        phase=BlockPhase.CLOSE,
                        content=content,
                    )
                )
            elif event_type == "system":
                await self.ui.on_block_event(
                    BlockEvent(
                        block_id=self._next_block_id(BlockKind.SYSTEM),
                        kind=BlockKind.SYSTEM,
                        phase=BlockPhase.CLOSE,
                        content=payload.get("text", ""),
                    )
                )

    async def _drain_reasoning_events(self) -> None:
        """Drain event bus for reasoning content (DeepSeek/Qwen3 thinking mode)."""
        if not self.query_engine or not self.query_engine._event_bus:
            return
        reasoning_buffer = ""
        while True:
            event = self.query_engine._event_bus.get_nowait()
            if not event:
                break
            if event.type == "reasoning_delta":
                reasoning_buffer += event.data.get("text", "")
                await self.ui.on_block_event(
                    BlockEvent(
                        block_id=self._next_block_id(BlockKind.THINKING),
                        kind=BlockKind.THINKING,
                        phase=BlockPhase.DELTA,
                        content=reasoning_buffer,
                    )
                )

    # ------------------------------------------------------------------
    # Tool execution (extracted from all three UIs)
    # ------------------------------------------------------------------

    async def _execute_tools(self, pending_tools: list[ToolUseMessage]) -> str:
        """Execute a batch of tools and return the next prompt for verification.

        Returns:
            The verification prompt if compilation check found errors,
            empty string otherwise.
        """
        for tool_msg in pending_tools:
            tool_name = self._normalize_tool_name(tool_msg.name)
            params = tool_msg.input if isinstance(tool_msg.input, dict) else {}
            is_safe = self._is_safe_tool(tool_name, params)

            # Check session-level permission cache
            if tool_name in self._session_permissions:
                allowed = self._session_permissions[tool_name]
                if not allowed:
                    self.query_engine.add_tool_result(
                        tool_msg.tool_use_id,
                        "Tool execution denied by session policy",
                        is_error=True,
                    )
                    await self._emit_tool_result(tool_name, "Denied (session policy)", error=True)
                    continue
                # Allowed by session policy, continue to execute

            # Request permission if not auto-allow and not safe
            elif not self.config.auto_allow and not is_safe:
                perm = await self.ui.request_permission(
                    tool_name, params, risk_level="high" if not is_safe else "low"
                )
                # Update session cache if user chose "Allow for this session"
                if perm.for_session:
                    self._session_permissions[tool_name] = perm.allowed

                if not perm.allowed:
                    denied_msg = (
                        "Tool execution denied by user. Proceed with your alternative "
                        "read-only approach immediately without explaining your plan first."
                    )
                    self.query_engine.add_tool_result(
                        tool_msg.tool_use_id, denied_msg, is_error=True
                    )
                    await self._emit_tool_result(tool_name, "Denied (user)", error=True)
                    # P0: FileEdit compensation tracking
                    self._apply_compensation(tool_name, False, denied_msg)
                    self._abort_current_turn = True
                    break

            # Execute the tool
            try:
                ctx = ToolUseContext(
                    get_app_state=self.get_app_state,
                    set_app_state=self.set_app_state,
                    cwd=self.config.cwd or str(Path.cwd()),
                )

                result = await self.tool_executor.execute_tool_by_name(tool_name, params, ctx)

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

                self.query_engine.add_tool_result(
                    tool_msg.tool_use_id, output, is_error=not result.success
                )
                await self._emit_tool_result(tool_name, output, error=not result.success)
                # P0: FileEdit compensation tracking
                self._apply_compensation(tool_name, result.success, output)

            except Exception as e:
                error_msg = str(e)
                self.query_engine.add_tool_result(tool_msg.tool_use_id, error_msg, is_error=True)
                await self.ui.on_block_event(
                    BlockEvent(
                        block_id=self._next_block_id(BlockKind.SYSTEM),
                        kind=BlockKind.SYSTEM,
                        phase=BlockPhase.CLOSE,
                        content=f"❌ Tool error ({tool_name}): {error_msg}",
                    )
                )
                # P0: FileEdit compensation tracking
                self._apply_compensation(tool_name, False, error_msg)

        # --- Compiler / syntax verification for changed code files ---
        return await self._verify_compilation(pending_tools)

    async def _emit_tool_result(self, tool_name: str, output: str, *, error: bool = False) -> None:
        """Emit a TOOL_RESULT block event and update token count."""
        # Truncate long output for display
        display_output = output[:500] if len(output) > 500 else output
        await self.ui.on_block_event(
            BlockEvent(
                block_id=self._next_block_id(BlockKind.TOOL_RESULT),
                kind=BlockKind.TOOL_RESULT,
                phase=BlockPhase.CLOSE,
                content=display_output,
                metadata={
                    "tool_name": tool_name,
                    "full_output": output,
                    "error": error,
                },
            )
        )
        # Update token count after tool result
        try:
            await self.ui.on_status_update(
                StatusUpdate(
                    token_count=self.get_token_count(),
                    context_window=self._get_context_window(),
                )
            )
        except Exception:
            pass

    def _apply_compensation(self, tool_name: str, success: bool, output: str) -> None:
        """Apply FileEdit compensation tracking.

        Unified from: simple_cli.py:249-256, controller.py:1163-1172
        """
        hint = self._fileedit_tracker.record_result(tool_name, success, output)
        if hint:
            self.query_engine.messages.append(SystemMessage(content=hint))
            # Emit system notification about compensation
            # Note: this is synchronous, so we schedule the block event
            asyncio.ensure_future(
                self.ui.on_block_event(
                    BlockEvent(
                        block_id=self._next_block_id(BlockKind.SYSTEM),
                        kind=BlockKind.SYSTEM,
                        phase=BlockPhase.CLOSE,
                        content="⚠️ FileEdit compensation activated",
                    )
                )
            )

    def _normalize_tool_name(self, name: str) -> str:
        """Normalize tool name to ensure consistent cache keys.

        Unified from: controller.py:1027-1055
        """
        from pilotcode.tools.registry import get_all_tools

        if not isinstance(name, str):
            name = str(name) if name is not None else ""

        for tool in get_all_tools():
            if tool.name == name:
                return tool.name
            if name in tool.aliases:
                return tool.name

        name_lower = name.lower()
        for tool in get_all_tools():
            if tool.name.lower() == name_lower:
                return tool.name
            for alias in tool.aliases:
                if alias.lower() == name_lower:
                    return tool.name

        return name

    # ------------------------------------------------------------------
    # Compiler verification (extracted from all three UIs)
    # ------------------------------------------------------------------

    async def _verify_compilation(self, pending_tools: list[ToolUseMessage]) -> str:
        """Verify compilation for changed code files.

        Unified from:
        - simple_cli.py:801-896
        - controller.py:913-997
        - server.py (similar)

        Returns:
            Verification prompt if errors found, empty string otherwise.
        """
        if not self.config.compilation_verify:
            return ""

        has_compile_command = any(
            tool_msg.name in ("Bash", "bash", "PowerShell", "powershell")
            and any(
                kw
                in (
                    tool_msg.input.get("command", "") + " " + tool_msg.input.get("script", "")
                ).lower()
                for kw in (
                    "gcc",
                    "g++",
                    "make",
                    "cmake",
                    "cl ",
                    "msbuild",
                    "rustc",
                    "cargo",
                    "go build",
                    "javac",
                    "npm run build",
                    "tsc",
                )
            )
            for tool_msg in pending_tools
        )

        changed_files: list[str] = []
        if not has_compile_command:
            for tool_msg in pending_tools:
                if tool_msg.name in (
                    "FileWrite",
                    "write",
                    "FileEdit",
                    "edit",
                    "ApplyPatch",
                    "apply_patch",
                ):
                    path = (
                        tool_msg.input.get("file_path")
                        or tool_msg.input.get("path")
                        or tool_msg.input.get("base_path", "")
                    )
                    if path and not path.endswith((".h", ".hpp")) and path not in changed_files:
                        changed_files.append(path)

        if not changed_files:
            return ""

        from pilotcode.orchestration.task_spec import TaskSpec
        from pilotcode.orchestration.results import ExecutionResult
        from pilotcode.orchestration.verifier.level2_tests import TestRunnerVerifier

        temp_task = TaskSpec(
            id="session_service_verify",
            title="verification",
            objective="verify compilation",
        )
        temp_exec = ExecutionResult(
            task_id="session_service_verify",
            success=True,
            artifacts={
                "changed_files": changed_files,
                "cwd": self.config.cwd or ".",
            },
        )
        verifier = TestRunnerVerifier()
        try:
            has_file_write = any(
                tool_msg.name
                in ("FileWrite", "write", "FileEdit", "edit", "ApplyPatch", "apply_patch")
                for tool_msg in pending_tools
            )
            v_result = await verifier.verify(
                temp_task, temp_exec, skip_project_build=has_file_write
            )
            if not v_result.passed and v_result.feedback:
                return (
                    "[FRAMEWORK VERIFICATION - COMPILE CHECK]\n"
                    f"{v_result.feedback}\n"
                    "Fix these errors before proceeding."
                )
        except Exception:
            pass
        return ""

    # ------------------------------------------------------------------
    # Context management (extracted from SimpleCLI)
    # ------------------------------------------------------------------

    async def _check_and_compress_context(self) -> None:
        """Check if context needs compression and perform it if necessary.

        Unified from: simple_cli.py:975-1029
        """
        if not self.query_engine:
            return

        try:
            from pilotcode.services.token_estimation import estimate_tokens
            from pilotcode.utils.models_config import get_model_limits

            total_tokens = sum(
                estimate_tokens(str(getattr(m, "content", ""))) for m in self.query_engine.messages
            )
            limits = get_model_limits()
            ctx_window = limits.get("context_window", 128_000)
            max_out = limits.get("max_tokens", 4096)
            if max_out <= 0:
                max_out = 4096
            max_out = min(max_out, 32_000)
            usable = max(1, ctx_window - max_out)
            threshold = int(usable * 0.85)

            if total_tokens < threshold:
                return

            await self.ui.on_block_event(
                BlockEvent(
                    block_id=self._next_block_id(BlockKind.SYSTEM),
                    kind=BlockKind.SYSTEM,
                    phase=BlockPhase.CLOSE,
                    content=(
                        f"🔄 Context at {total_tokens}/{ctx_window} tokens "
                        f"({total_tokens * 100 // ctx_window}%), compressing..."
                    ),
                )
            )

            from pilotcode.services.context_compression import get_context_compressor

            compressor = get_context_compressor()
            original_count = len(self.query_engine.messages)
            original_tokens = total_tokens
            self.query_engine.messages = compressor.simple_compact(
                self.query_engine.messages, keep_recent=10
            )
            compressed_count = len(self.query_engine.messages)

            remaining_tokens = sum(
                estimate_tokens(str(getattr(m, "content", ""))) for m in self.query_engine.messages
            )
            tokens_saved = original_tokens - remaining_tokens

            await self.ui.on_block_event(
                BlockEvent(
                    block_id=self._next_block_id(BlockKind.SYSTEM),
                    kind=BlockKind.SYSTEM,
                    phase=BlockPhase.CLOSE,
                    content=f"   Compressed: {original_count} -> {compressed_count} messages (~{tokens_saved} tokens saved)",
                )
            )
        except Exception as e:
            logger.warning("Context compression failed: %s", e)

    # ------------------------------------------------------------------
    # Mission interruption (currently TUI+Web only, now shared)
    # ------------------------------------------------------------------

    def cancel_current_query(self) -> dict | None:
        """Cancel the currently running query.

        Returns partial status if a query was running, or None.
        """
        if self._cancel_event and not self._cancel_event.is_set():
            self._cancel_event.set()
            return {"cancelled": True}
        return None

    # ------------------------------------------------------------------
    # Command dispatch (extracted from all three UIs)
    # ------------------------------------------------------------------

    async def handle_command(self, text: str) -> CommandResult:
        """Unified slash command dispatch.

        Currently duplicated 3x. This method handles:
        1. Built-in commands (/help, /clear, /quit, /save, /load, etc.)
        2. CommandRegistry dispatch
        3. Extension commands (.pilotcode/commands/*.md)
        4. ! shell escape

        Args:
            text: The raw command text (e.g., "/help" or "/model deepseek-v3").

        Returns:
            CommandResult with action for the View to handle.
        """
        parts = text.split()
        if not parts:
            return CommandResult(action=CommandAction.UNKNOWN, message="Empty command")

        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []

        # Built-in commands
        if cmd in ("/quit", "/exit"):
            return CommandResult(action=CommandAction.QUIT, message="Goodbye!")

        if cmd == "/help":
            return CommandResult(
                action=CommandAction.CONTINUE,
                message=self._get_help_text(),
            )

        if cmd == "/clear":
            if self.query_engine:
                self.query_engine.clear_history()
            return CommandResult(
                action=CommandAction.CLEAR,
                message="Conversation history cleared",
            )

        if cmd == "/save":
            arg = args[0] if args else None
            try:
                if arg and (arg.endswith(".json") or "/" in arg or "\\" in arg):
                    self.query_engine.save_session(arg)
                    return CommandResult(
                        action=CommandAction.CONTINUE,
                        message=f"Session saved to {arg}",
                    )
                else:
                    ok = self.query_engine.save_to_storage(name=arg)
                    if ok:
                        return CommandResult(
                            action=CommandAction.CONTINUE,
                            message=f"Session saved (id: {self.query_engine.session_id})",
                        )
                    else:
                        return CommandResult(
                            action=CommandAction.ERROR,
                            message="Failed to save to unified storage",
                        )
            except Exception as e:
                return CommandResult(action=CommandAction.ERROR, message=f"Failed to save: {e}")

        if cmd == "/load":
            arg = args[0] if args else None
            try:
                if arg and (arg.endswith(".json") or "/" in arg or "\\" in arg):
                    if Path(arg).exists():
                        self.query_engine.load_session(arg)
                        msg_count = len(self.query_engine.messages)
                        return CommandResult(
                            action=CommandAction.CONTINUE,
                            message=f"Session loaded from {arg} ({msg_count} messages)",
                        )
                    else:
                        return CommandResult(
                            action=CommandAction.ERROR,
                            message=f"File not found: {arg}",
                        )
                else:
                    sid = arg or self.query_engine.session_id
                    ok = self.query_engine.load_from_storage(session_id=sid)
                    if ok:
                        msg_count = len(self.query_engine.messages)
                        return CommandResult(
                            action=CommandAction.RELOAD,
                            message=f"Session loaded (id: {self.query_engine.session_id}, {msg_count} messages)",
                            session_id=self.query_engine.session_id,
                        )
                    else:
                        return CommandResult(
                            action=CommandAction.ERROR,
                            message=f"Session not found: {arg or 'unified storage'}",
                        )
            except Exception as e:
                return CommandResult(action=CommandAction.ERROR, message=f"Failed to load: {e}")

        if cmd == "/compact":
            if self.query_engine:
                from pilotcode.services.context_compression import get_context_compressor

                original_count = len(self.query_engine.messages)
                compressor = get_context_compressor()
                self.query_engine.messages = compressor.simple_compact(
                    self.query_engine.messages, keep_recent=10
                )
                compressed_count = len(self.query_engine.messages)
                return CommandResult(
                    action=CommandAction.CONTINUE,
                    message=f"Compressed: {original_count} -> {compressed_count} messages",
                )

        # Try CommandRegistry dispatch
        try:
            from pilotcode.commands.base import process_user_input
            from pilotcode.types.command import CommandContext as CmdCtx

            context = CmdCtx(
                cwd=self.config.cwd or str(Path.cwd()),
                query_engine=self.query_engine,
                session_id=self._session_id,
            )
            is_command, result = await process_user_input(text, context)
            if is_command:
                if isinstance(result, str):
                    if result == "__EXIT_TUI__":
                        return CommandResult(action=CommandAction.QUIT, message="Exiting")
                    return CommandResult(action=CommandAction.CONTINUE, message=result)
                return CommandResult(action=CommandAction.EXECUTED)
        except Exception as e:
            logger.warning("Command registry dispatch failed: %s", e)

        # Try extension commands (.pilotcode/commands/*.md)
        ext_result = await self._dispatch_extension_command(cmd.lstrip("/"), args)
        if ext_result is not None:
            return ext_result

        # Try ! shell escape
        if text.startswith("!"):
            return await self._dispatch_shell_escape(text[1:])

        return CommandResult(
            action=CommandAction.UNKNOWN,
            message=f"Unknown command: {cmd}",
        )

    async def _dispatch_extension_command(self, name: str, args: list[str]) -> CommandResult | None:
        """Load and execute .pilotcode/commands/*.md as PromptCommand."""
        md_path = self._find_extension_command(name)
        if not md_path:
            return None

        try:
            prompt_template = md_path.read_text(encoding="utf-8")
            prompt = prompt_template.replace("$ARGUMENTS", " ".join(args))
            await self.process_query(prompt)
            return CommandResult(action=CommandAction.EXECUTED)
        except Exception as e:
            return CommandResult(
                action=CommandAction.ERROR,
                message=f"Extension command error: {e}",
            )

    def _find_extension_command(self, name: str) -> Path | None:
        """Find .md file for an extension command."""
        search_dirs = [
            Path(self.config.cwd) / ".pilotcode" / "commands",
            Path.home() / ".pilotcode" / "commands",
        ]
        for base in search_dirs:
            candidate = base / f"{name}.md"
            if candidate.exists():
                return candidate
            candidate = base / f"{name.replace('/', os.sep)}.md"
            if candidate.exists():
                return candidate
        return None

    async def _dispatch_shell_escape(self, command: str) -> CommandResult:
        """Execute a shell command directly without LLM round-trip."""
        if not command.strip():
            return CommandResult(action=CommandAction.ERROR, message="Empty shell command")
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.config.cwd or None,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            except asyncio.TimeoutError:
                proc.kill()
                return CommandResult(
                    action=CommandAction.ERROR, message="Shell command timed out (30s)"
                )

            output = (stdout or stderr or b"").decode("utf-8", errors="replace")
            if not output.strip():
                output = "(no output)"
            if len(output) > 5000:
                output = output[:5000] + f"\n... (truncated, {len(output)} chars total)"
            return CommandResult(action=CommandAction.CONTINUE, message=output)
        except Exception as e:
            return CommandResult(
                action=CommandAction.ERROR, message=f"Shell command failed: {e}"
            )  # ------------------------------------------------------------------

    # Settings API (View -> Controller reverse channel)
    # ------------------------------------------------------------------

    def set_model(self, model_name: str) -> None:
        """Switch model mid-session. Re-initializes model client."""
        self.config.model_name = model_name
        self._reinit_model_client()

        # Update QueryEngine's cached context_window and max_output_tokens
        # for the new model, so that UIs (e.g. Web UI bottom-right corner)
        # show correct token usage percentages immediately.
        if self.query_engine:
            from pilotcode.utils.models_config import (
                get_model_context_window,
                get_model_max_tokens,
            )

            new_ctx = get_model_context_window(model_name)
            new_max = get_model_max_tokens(model_name)
            if new_ctx > 0:
                self.query_engine.config = replace(self.query_engine.config, context_window=new_ctx)
            if new_max > 0:
                self.query_engine._max_output_tokens = min(new_max, 32_000)
            self.query_engine._usable_context = max(
                1, self.query_engine.config.context_window - self.query_engine._max_output_tokens
            )

        # Notify UI of change (best-effort; skip if no event loop)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self.ui.on_status_update(
                    StatusUpdate(
                        status_text=f"Model: {model_name}",
                        model_name=model_name,
                        token_count=self.get_token_count(),
                        context_window=(
                            self.query_engine.config.context_window if self.query_engine else 0
                        ),
                        max_output_tokens=(
                            self.query_engine._max_output_tokens if self.query_engine else 0
                        ),
                    )
                )
            )
        except RuntimeError:
            # No running event loop -- notification will be picked up
            # on next status update cycle
            logger.debug("set_model: no event loop, skipping UI notification")

    def set_thinking_mode(self, enabled: bool) -> None:
        """Toggle thinking/reasoning mode. Affects next query."""
        self.config.thinking_mode = enabled

    def update_config(self, **kwargs: Any) -> None:
        """Bulk update config. Any SessionConfig field can be passed."""
        changed = self.config.update(**kwargs)
        if changed:
            self._apply_config_changes()

    def _reinit_model_client(self) -> None:
        """Re-initialize the model client after model change."""
        # This will be implemented when model switching is fully supported
        logger.info("Model client re-initialization requested for: %s", self.config.model_name)

    def _apply_config_changes(self) -> None:
        """Apply config changes to QueryEngine."""
        if self.query_engine and self.query_engine.config:
            updates = {}
            if self.config.context_window:
                updates["context_window"] = self.config.context_window
            if self.config.max_iterations:
                updates["max_turns"] = self.config.max_iterations
            if updates:
                self.query_engine.config = replace(self.query_engine.config, **updates)

    async def process_query_with_override(self, text: str, **overrides: Any) -> None:
        """Process a query with temporary config overrides.

        After the query completes, overrides are reverted.
        """
        saved = {}
        for key, value in overrides.items():
            saved[key] = getattr(self.config, key)
            setattr(self.config, key, value)

        self._apply_config_changes()

        try:
            await self.process_query(text)
        finally:
            for key, value in saved.items():
                setattr(self.config, key, value)
            self._apply_config_changes()

            await self.ui.on_status_update(
                StatusUpdate(status_text="Trial mode ended, settings reverted")
            )

    # ------------------------------------------------------------------
    # Session management (extracted from TUIController + WebServer)
    # ------------------------------------------------------------------

    def _auto_save(self) -> None:
        """Auto-save current session to disk."""
        if not self.config.auto_save or not self.query_engine or not self._session_id:
            return
        try:
            from pilotcode.services.session_persistence import get_session_persistence

            persistence = get_session_persistence()
            persistence.save_session(
                session_id=self._session_id,
                messages=self.query_engine.messages,
                name=self._session_name,
                project_path=self.config.cwd or str(Path.cwd()),
            )
        except Exception:
            pass  # Fail silently to not disrupt the user experience

    async def save_session(self, path: str | None = None) -> bool:
        """Save session to file or unified storage."""
        if not self.query_engine:
            return False
        try:
            if path:
                self.query_engine.save_session(path)
                return True
            else:
                return self.query_engine.save_to_storage(name=None)
        except Exception:
            return False

    async def load_session(self, path_or_id: str) -> bool:
        """Load session from file or unified storage."""
        if not self.query_engine:
            return False
        try:
            if path_or_id.endswith(".json") or "/" in path_or_id or "\\" in path_or_id:
                return self.query_engine.load_session(path_or_id)
            else:
                return self.query_engine.load_from_storage(session_id=path_or_id)
        except Exception:
            return False

    def clear_history(self) -> None:
        """Clear conversation history."""
        if self.query_engine:
            self.query_engine.clear_history()

    # ------------------------------------------------------------------
    # Token info (for StatusUpdate)
    # ------------------------------------------------------------------

    def get_token_count(self) -> int:
        """Get current token count."""
        if self.query_engine:
            return self.query_engine.count_tokens()
        return 0

    def get_token_info(self) -> dict[str, int]:
        """Get full token info for status bar display."""
        if not self.query_engine:
            return {"count": 0, "context_window": 0, "max_output_tokens": 0, "usable": 0}
        qe = self.query_engine
        return {
            "count": qe.count_tokens(),
            "context_window": qe.config.context_window,
            "max_output_tokens": qe._max_output_tokens,
            "usable": qe._usable_context,
        }

    def _get_context_window(self) -> int:
        """Get the context window size."""
        if self.query_engine:
            return self.query_engine.config.context_window
        return 0

    # ------------------------------------------------------------------
    # Help text
    # ------------------------------------------------------------------

    def _get_help_text(self) -> str:
        """Get help text for /help command."""
        return (
            "Available Commands:\n"
            "  /help           Show this help message\n"
            "  /save [file]    Save to unified storage, or to file if .json given\n"
            "  /load [id/file] Load from unified storage, or from file if .json given\n"
            "  /clear          Clear conversation history and context\n"
            "  /compact        Manually compress context\n"
            "  /quit or /exit  Exit the application\n"
        )
