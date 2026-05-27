"""TUI Controller - bridges TUI with PilotCode core.

Refactored to use SessionService for core business logic while keeping
TUI-specific concerns (UIMessage generation, P-EVR orchestration,
permission callbacks) in this controller layer.

The SessionService handles:
- QueryEngine initialization
- Session lifecycle (create/restore/auto-save)
- Main query loop (streaming, tool execution, compilation verification)
- Context compression
- Command dispatch
- FileEdit compensation tracking

The TUIController adds:
- UIMessage type conversion (BlockEvent -> UIMessage)
- P-EVR orchestration mode
- Permission/ask-user callbacks (async Textual widgets)
- Session fork management
- Token info for StatusBar
"""

import asyncio
import os
from collections import deque
from datetime import datetime, timezone
from typing import AsyncIterator, Optional, Callable
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from pilotcode.types.message import (
    UserMessage,
    AssistantMessage,
    SystemMessage,
)
from pilotcode.ui.protocol import (
    BlockEvent,
    BlockKind,
    BlockPhase,
    StatusUpdate,
    PermissionResult as ProtocolPermissionResult,
)
from pilotcode.ui.config import SessionConfig
from pilotcode.ui.session_service import SessionService
from pilotcode.state.app_state import AppState


class ToolDeniedError(Exception):
    """Raised when user denies a tool execution. Stops the current tool batch."""

    def __init__(self, message: str, stop_task: bool = True):
        super().__init__(message)
        self.stop_task = stop_task


class UIMessageType(Enum):
    """UI message types."""

    USER = auto()
    ASSISTANT = auto()
    THINKING = auto()
    REASONING = auto()
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


class TUIProtocol:
    """UIProtocol adapter that collects BlockEvents and converts them to UIMessages.

    Instead of directly rendering, this adapter collects events during
    SessionService.process_query() and makes them available as UIMessages
    for the TUI's AsyncIterator-based interface.
    """

    def __init__(self):
        self._collected_messages: list[UIMessage] = []
        self._permission_future: asyncio.Future | None = None
        self._ask_user_future: asyncio.Future | None = None

    def reset(self):
        """Clear collected messages for a new query."""
        self._collected_messages.clear()

    @property
    def collected_messages(self) -> list[UIMessage]:
        """Get messages collected during the last query."""
        return self._collected_messages

    async def on_block_event(self, event: BlockEvent) -> None:
        """Convert BlockEvent to UIMessage and collect it."""
        if event.kind == BlockKind.ASSISTANT:
            self._collected_messages.append(
                UIMessage(
                    type=UIMessageType.ASSISTANT,
                    content=event.content,
                    is_streaming=(event.phase == BlockPhase.DELTA),
                    is_complete=(event.phase == BlockPhase.CLOSE),
                )
            )

        elif event.kind == BlockKind.THINKING:
            self._collected_messages.append(
                UIMessage(
                    type=UIMessageType.THINKING,
                    content=event.content,
                    is_complete=True,
                )
            )

        elif event.kind == BlockKind.TOOL_CALL:
            if event.phase == BlockPhase.OPEN:
                tool_name = event.metadata.get("tool_name", event.content)
                tool_input = event.metadata.get("tool_input", {})
                tool_use_id = event.metadata.get("tool_use_id", "")
                iteration = event.metadata.get("iteration", 1)
                max_iterations = event.metadata.get("max_iterations", 50)
                self._collected_messages.append(
                    UIMessage(
                        type=UIMessageType.TOOL_USE,
                        content=tool_name,
                        metadata={
                            "tool_name": tool_name,
                            "tool_input": tool_input,
                            "tool_use_id": tool_use_id,
                            "is_safe": False,  # Will be set by controller
                            "turn": iteration,
                            "max_turns": max_iterations,
                        },
                        is_complete=False,
                    )
                )

        elif event.kind == BlockKind.TOOL_RESULT:
            if event.phase == BlockPhase.CLOSE:
                tool_name = event.metadata.get("tool_name", "")
                error = event.metadata.get("error", False)
                self._collected_messages.append(
                    UIMessage(
                        type=UIMessageType.TOOL_RESULT,
                        content=event.content,
                        metadata={"tool_name": tool_name, "error": error},
                        is_complete=True,
                    )
                )

        elif event.kind == BlockKind.SYSTEM:
            if event.phase == BlockPhase.CLOSE and event.content:
                self._collected_messages.append(
                    UIMessage(
                        type=UIMessageType.SYSTEM,
                        content=event.content,
                        is_complete=True,
                    )
                )

        elif event.kind == BlockKind.PLAN_PROGRESS:
            if event.content:
                self._collected_messages.append(
                    UIMessage(
                        type=UIMessageType.SYSTEM,
                        content=event.content,
                        is_complete=True,
                    )
                )

    async def on_status_update(self, update: StatusUpdate) -> None:
        """Status updates are handled by the controller directly."""
        pass

    async def request_permission(
        self, tool_name: str, params: dict, risk_level: str
    ) -> ProtocolPermissionResult:
        """Request permission via the callback set by TUIController."""
        if self._permission_callback:
            result = await self._permission_callback(tool_name, params)
            # Convert TUI PermissionResult to Protocol PermissionResult
            if isinstance(result, ProtocolPermissionResult):
                return result
            # Handle TUI's own PermissionResult type
            if hasattr(result, "allowed"):
                return ProtocolPermissionResult(
                    allowed=result.allowed,
                    for_session=getattr(result, "for_session", False),
                )
            # Handle bool return
            if isinstance(result, bool):
                return ProtocolPermissionResult(allowed=result)
        return ProtocolPermissionResult(allowed=False)

    async def request_user_input(self, question: str, options: list[str] | None = None) -> str:
        """Request user input via the callback set by TUIController."""
        if self._ask_user_callback:
            return await self._ask_user_callback(question, options)
        return ""

    async def on_error(self, error: str) -> None:
        """Collect error as UIMessage."""
        self._collected_messages.append(
            UIMessage(
                type=UIMessageType.ERROR,
                content=error,
                is_complete=True,
            )
        )

    # Callback setters (called by TUIController)
    _permission_callback: Callable | None = None
    _ask_user_callback: Callable | None = None


class TUIController:
    """Controller that bridges TUI with PilotCode core functionality.

    Uses SessionService for core business logic. Adds TUI-specific:
    - UIMessage generation for Textual widgets
    - P-EVR orchestration mode
    - Permission/ask-user async callbacks
    - Session fork management
    - Token info for StatusBar
    """

    def __init__(
        self,
        get_app_state: Optional[Callable[[], AppState]] = None,
        set_app_state: Optional[Callable[[Callable[[AppState], AppState]], None]] = None,
        auto_allow: bool = False,
        max_iterations: int = 50,
        session_options: dict | None = None,
    ):
        self.get_app_state = get_app_state
        self.set_app_state = set_app_state
        self.auto_allow = auto_allow
        self.max_iterations = max_iterations
        self.session_options = session_options or {}

        # Create the TUI protocol adapter
        self._tui_protocol = TUIProtocol()

        # Create session config from constructor params
        session_config = SessionConfig(
            cwd=self.session_options.get("cwd", str(Path.cwd())),
            auto_allow=auto_allow,
            max_iterations=max_iterations,
            auto_save=True,
            auto_compact=True,
            restore_on_start=self.session_options.get("restore", False),
            session_id=self.session_options.get("session_id", ""),
        )

        # Create SessionService (handles all core business logic)
        self._service = SessionService(
            ui=self._tui_protocol,
            config=session_config,
            get_app_state=get_app_state,
            set_app_state=set_app_state,
        )

        # Expose query_engine for backward compatibility
        # (TUI session screen accesses it directly)
        self.query_engine = self._service.query_engine
        self._session_id = self._service._session_id
        self._session_name = self._service._session_name

        # P-EVR mode state (TUI-specific)
        self._current_mission: dict | None = None
        self._last_pevr_empty: bool = False

    # ------------------------------------------------------------------
    # Backward-compatible properties
    # ------------------------------------------------------------------

    @property
    def tool_executor(self):
        """Access tool executor from SessionService."""
        return self._service.tool_executor

    @property
    def _fileedit_tracker(self):
        """Access FileEdit tracker from SessionService."""
        return self._service._fileedit_tracker

    @property
    def _session_permissions(self):
        """Access session permissions from SessionService."""
        return self._service._session_permissions

    # ------------------------------------------------------------------
    # Callback registration (TUI-specific)
    # ------------------------------------------------------------------

    def set_permission_callback(
        self, callback: Callable[[str, dict], asyncio.Future[bool]]
    ) -> None:
        """Set callback for permission requests."""
        self._tui_protocol._permission_callback = callback

    def set_ask_user_callback(
        self, callback: Callable[[str, list[str] | None], asyncio.Future[str]]
    ) -> None:
        """Set callback for ask user input requests."""
        self._tui_protocol._ask_user_callback = callback

    # ------------------------------------------------------------------
    # Main query interface (kept as AsyncIterator[UIMessage] for TUI)
    # ------------------------------------------------------------------

    async def submit_message(self, text: str, force_plan: bool = False) -> AsyncIterator[UIMessage]:
        """Submit a message and yield UI messages.

        For P-EVR mode, delegates to _run_pevr_mode (TUI-specific).
        For normal mode, delegates to SessionService.process_query()
        and collects the resulting UIMessages.
        """
        if not self.query_engine:
            yield UIMessage(type=UIMessageType.ERROR, content="Query engine not initialized")
            return

        # P-EVR mode: only when explicitly requested via /plan
        if force_plan:
            async for msg in self._run_pevr_mode(text):
                yield msg
            if getattr(self, "_last_pevr_empty", False):
                delattr(self, "_last_pevr_empty")
            else:
                return

        # Detect CWD from user message
        from pilotcode.components.repl import _extract_target_path

        detected_cwd = _extract_target_path(text)
        current_cwd = self.session_options.get("cwd", str(Path.cwd()))
        if detected_cwd and detected_cwd != current_cwd:
            if os.path.isdir(detected_cwd):
                if self._service._update_session_cwd(detected_cwd):
                    yield UIMessage(
                        type=UIMessageType.SYSTEM,
                        content=f"📁 Working directory updated to: {detected_cwd}",
                    )

        # Run query via SessionService
        self._tui_protocol.reset()
        await self._service.process_query(text)

        # Yield collected UIMessages
        for msg in self._tui_protocol.collected_messages:
            yield msg

        # Sync query_engine reference
        self.query_engine = self._service.query_engine
        self._session_id = self._service._session_id
        self._session_name = self._service._session_name

    # ------------------------------------------------------------------
    # P-EVR orchestration (TUI-specific, kept in controller)
    # ------------------------------------------------------------------

    @property
    def current_mission(self) -> dict | None:
        """Get current mission tracking info, or None if no mission running."""
        return self._current_mission

    def cancel_mission(self) -> dict | None:
        """Cancel the currently running mission."""
        mission = self._current_mission
        if mission is None:
            return None

        cancel_event = mission.get("cancel_event")
        if cancel_event and not cancel_event.is_set():
            cancel_event.set()
            mission["cancelled"] = True

        return {
            "cancelled": True,
            "partial_tasks": mission.get("partial_tasks", []),
        }

    async def _run_pevr_mode(self, text: str) -> AsyncIterator[UIMessage]:
        """Run a complex task in P-EVR orchestration mode.

        This is TUI-specific and kept in the controller because it uses
        the UIMessage AsyncIterator pattern directly.
        """
        from pilotcode.orchestration.adapter import MissionAdapter
        from pilotcode.orchestration.report import format_failure, format_task_event, _STATE_EMOJI

        cancel_event = asyncio.Event()
        self._current_mission = {
            "cancel_event": cancel_event,
            "mission_task": None,
            "partial_tasks": [],
            "cancelled": False,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        ctx_window = self.query_engine.config.context_window if self.query_engine else 128_000
        cwd = self.session_options.get("cwd", str(Path.cwd()))
        adapter = MissionAdapter(
            cancel_event=cancel_event,
            context_budget=ctx_window,
            cwd=cwd,
        )

        mission_displayed = False
        worker_buffer = ""
        worker_streaming = False
        current_task_id = ""
        tool_use_counter = 0

        def progress_cb(event_type: str, data: dict) -> None:
            self._pevr_events.append((event_type, data))

        self._pevr_events: deque[tuple[str, dict]] = deque()

        mission_task = asyncio.create_task(
            adapter.run(text, progress_callback=progress_cb, cwd=cwd)
        )
        self._current_mission["mission_task"] = mission_task

        yield UIMessage(
            type=UIMessageType.SYSTEM,
            content="Task classified as complex — entering PLAN mode with structured execution.",
        )

        result: dict | None = None
        while not mission_task.done():
            if self._current_mission.get("cancelled"):
                mission_task.cancel()
                try:
                    await mission_task
                except (asyncio.CancelledError, Exception):
                    pass
                yield UIMessage(
                    type=UIMessageType.SYSTEM,
                    content="⏸  Mission interrupted by user.",
                )
                partial_tasks = self._current_mission.get("partial_tasks", [])
                if partial_tasks:
                    done = sum(1 for t in partial_tasks if t.get("done"))
                    failed = sum(1 for t in partial_tasks if t.get("failed"))
                    yield UIMessage(
                        type=UIMessageType.SYSTEM,
                        content=f"Partial progress: {done} completed, {failed} failed, "
                        f"{len(partial_tasks) - done - failed} pending.",
                    )
                break

            while self._pevr_events:
                event_type, data = self._pevr_events.popleft()

                if event_type == "mission:planned" and not mission_displayed:
                    mission_displayed = True
                    from pilotcode.orchestration.report import format_plan
                    from pilotcode.orchestration.task_spec import Mission, Phase, TaskSpec

                    display_mission = Mission(
                        mission_id=data.get("mission_id", ""),
                        title=data.get("title", "Untitled Mission"),
                        requirement="",
                    )
                    for pd in data.get("phases", []):
                        phase = Phase(
                            phase_id=pd.get("phase_id", ""),
                            title=pd.get("title", ""),
                            description=pd.get("description", ""),
                            tasks=[TaskSpec.from_dict(t) for t in pd.get("tasks", [])],
                        )
                        display_mission.phases.append(phase)
                    plan_text = format_plan(display_mission)
                    yield UIMessage(type=UIMessageType.SYSTEM, content=plan_text)
                elif event_type in ("task:started", "task:rejected", "task:needs_rework"):
                    worker_buffer = ""
                    worker_streaming = False
                    msg = format_task_event(event_type, data)
                    yield UIMessage(type=UIMessageType.SYSTEM, content=msg)
                    current_task_id = data.get("task_id", "")
                elif event_type == "task:verified":
                    worker_buffer = ""
                    worker_streaming = False
                    msg = format_task_event(event_type, data)
                    yield UIMessage(type=UIMessageType.SYSTEM, content=msg)
                elif event_type == "worker:text_delta":
                    chunk = data.get("content", "")
                    if chunk:
                        worker_buffer += chunk
                        worker_streaming = True
                elif event_type == "worker:turn_complete":
                    worker_buffer = ""
                    worker_streaming = False
                elif event_type == "worker:tool_start":
                    if worker_streaming and worker_buffer:
                        yield UIMessage(
                            type=UIMessageType.ASSISTANT,
                            content=worker_buffer,
                            is_streaming=False,
                            is_complete=True,
                        )
                        worker_buffer = ""
                        worker_streaming = False
                    tool_name = data.get("tool_name", "tool")
                    params = data.get("params", {})
                    tool_use_counter += 1
                    yield UIMessage(
                        type=UIMessageType.TOOL_USE,
                        content=tool_name,
                        metadata={
                            "tool_name": tool_name,
                            "tool_input": params,
                            "tool_use_id": f"{current_task_id}_{tool_name}_{tool_use_counter}",
                        },
                        is_complete=False,
                    )
                elif event_type == "worker:tool_result":
                    tool_name = data.get("tool_name", "tool")
                    success = data.get("success", False)
                    summary = data.get("summary", "")
                    summary_oneline = summary.replace("\n", " ").replace("\r", "")
                    if len(summary_oneline) > 200:
                        summary_oneline = summary_oneline[:197] + "..."
                    yield UIMessage(
                        type=UIMessageType.TOOL_RESULT,
                        content=summary_oneline,
                        metadata={"tool_name": tool_name, "error": not success},
                        is_complete=True,
                    )
                elif event_type == "mission:completed":
                    pass
                elif event_type == "mission:blocked":
                    msg = format_task_event(event_type, data)
                    yield UIMessage(type=UIMessageType.SYSTEM, content=msg)
                elif event_type in (
                    "task:exception",
                    "task:timeout",
                    "task:max_rework_exceeded",
                    "task:cancelled_dependency_failure",
                ):
                    msg = format_task_event(event_type, data)
                    yield UIMessage(type=UIMessageType.ERROR, content=msg)

            await asyncio.sleep(0.2)

        # Get final result
        full_report = ""
        try:
            result = mission_task.result()
        except Exception as exc:
            result = {"success": False, "error": str(exc)}

        try:
            report_parts: list[str] = []
            snapshot = result.get("snapshot", {}) if result else {}
            total = snapshot.get("total_tasks", 0)
            completed = snapshot.get("completed_tasks", 0)
            failed = snapshot.get("failed_tasks", 0)

            self._last_pevr_empty = total == 0

            if result and result.get("success"):
                if total == 0:
                    report_parts.append(
                        "⚠️  Planner produced no actionable tasks for this request. "
                        "Switching to direct response mode."
                    )
                else:
                    report_parts.append(
                        f"🏁 Mission Complete  |  {completed}/{total} tasks  |  {failed} failed"
                    )
            else:
                error = result.get("error", "Unknown error") if result else "Mission failed"
                report_parts.append(format_failure(result or {}, error))

            task_outputs = result.get("task_outputs", {})
            if task_outputs:
                lines = ["📊 Analysis Results:"]
                for tid, tdata in task_outputs.items():
                    title = tdata.get("title", tid)
                    output_text = tdata.get("output", "")
                    if output_text:
                        if hasattr(output_text, "output"):
                            output_text = getattr(output_text, "output", "")
                        snippet = str(output_text)[:3000].strip()
                        snippet = __import__("re").sub(r"\n{3,}", "\n\n", snippet)
                        if snippet:
                            lines.append(f"\n**{title}**")
                            lines.append(snippet)
                if len(lines) > 1:
                    report_parts.append("\n".join(lines))

            mission_dict = result.get("mission", {}) if result else {}
            phases = mission_dict.get("phases", [])
            task_states = snapshot.get("task_states", {})
            if phases:
                lines = ["📋 Mission Plan Executed:", ""]
                for p in phases:
                    lines.append(f"- **Phase:** {p.get('title', 'Untitled')}")
                    for t in p.get("tasks", []):
                        task_id = t.get("id", "")
                        state = task_states.get(task_id, "unknown")
                        emoji = _STATE_EMOJI.get(state, "❓")
                        lines.append(f"  - {emoji} {t.get('title', task_id)}")
                    lines.append("")
                report_parts.append("\n".join(lines))

            full_report = "\n\n".join(report_parts)

            if result and result.get("success"):
                yield UIMessage(type=UIMessageType.ASSISTANT, content=full_report)
            else:
                yield UIMessage(type=UIMessageType.ERROR, content=full_report)
        except Exception as exc:
            error_msg = f"Mission report generation failed: {exc}"
            yield UIMessage(type=UIMessageType.ERROR, content=error_msg)
            full_report = error_msg
            self._last_pevr_empty = False
        finally:
            if hasattr(self, "_current_mission"):
                delattr(self, "_current_mission")
            if self.query_engine:
                self.query_engine.messages.append(UserMessage(content=text))
                self.query_engine.messages.append(AssistantMessage(content=full_report))
                task_outputs = result.get("task_outputs", {}) if result else {}
                if task_outputs:
                    context_parts = ["[Plan Mode Task Outputs]"]
                    for tid, tdata in list(task_outputs.items())[:5]:
                        title = tdata.get("title", tid)
                        output_text = tdata.get("output") or ""
                        if output_text and not isinstance(output_text, dict):
                            snippet = str(output_text)[:800]
                            context_parts.append(f"Task '{title}': {snippet}")
                    if len(context_parts) > 1:
                        self.query_engine.messages.append(
                            SystemMessage(content="\n".join(context_parts))
                        )
                try:
                    if self.query_engine.count_tokens() > int(
                        self.query_engine._usable_context * 0.85
                    ):
                        await self.query_engine.auto_compact_if_needed()
                except Exception:
                    pass
            if adapter._cwd != cwd:
                if self._service._update_session_cwd(adapter._cwd):
                    yield UIMessage(
                        type=UIMessageType.SYSTEM,
                        content=f"📁 Working directory updated to: {adapter._cwd}",
                    )

    # ------------------------------------------------------------------
    # Session management (delegated to SessionService)
    # ------------------------------------------------------------------

    def _auto_save(self) -> None:
        """Auto-save current session."""
        self._service._auto_save()

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
        self._service.clear_history()

    def reset_session_save_count(self) -> None:
        """Reset the persistence save count for current session."""
        if not self._session_id:
            return
        try:
            from pilotcode.services.session_persistence import get_session_persistence

            persistence = get_session_persistence()
            persistence.reset_save_count(self._session_id)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Token info (for StatusBar)
    # ------------------------------------------------------------------

    def get_token_count(self) -> int:
        """Get current token count."""
        return self._service.get_token_count()

    def get_token_info(self) -> dict[str, int]:
        """Get full token info for status bar display."""
        return self._service.get_token_info()

    # ------------------------------------------------------------------
    # Session CWD update (backward compat)
    # ------------------------------------------------------------------

    def _update_session_cwd(self, new_cwd: str) -> bool:
        """Update the session's working directory."""
        result = self._service._update_session_cwd(new_cwd)
        if result:
            self.session_options["cwd"] = new_cwd
        return result
