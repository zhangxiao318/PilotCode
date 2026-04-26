"""Web server for PilotCode Web UI."""

import sys
import json
import asyncio
import traceback
import logging
import uuid
from pathlib import Path
from typing import Set, Dict, Any
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading

from pilotcode.types.message import SystemMessage

# Suppress websockets verbose logging - only show errors, not warnings
logging.getLogger("websockets").setLevel(logging.ERROR)
logging.getLogger("websockets.server").setLevel(logging.ERROR)
logging.getLogger("websockets.protocol").setLevel(logging.ERROR)

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ------------------------------------------------------------------
# Helper: detect explicit tool-use intent in user query / response
# ------------------------------------------------------------------

TOOL_KEYWORDS = {
    "glob",
    "file read",
    "fileread",
    "grep",
    "search",
    "查找",
    "搜索",
    "读取",
    "read",
    "运行",
    "执行",
    "run",
    "execute",
    "bash",
    "file write",
    "filewrite",
    "edit",
    "修改",
    "写入",
    "写",
    "code index",
    "codeindex",
    "git status",
    "git log",
    "git diff",
}


def _should_use_tools(query: str, response: str) -> bool:
    """Heuristic: did the user explicitly ask for a tool operation?"""
    q = query.lower()
    # Negative cues — user explicitly says NOT to use tools
    negations = {
        "不要",
        "不用",
        "无需",
        "别",
        "不需要",
        "不要调用",
        "不用重新",
        "do not",
        "don't",
        "no need to",
        "without",
        "无需使用",
    }
    for neg in negations:
        if neg in q:
            return False
    # Explicit tool name mention
    for kw in TOOL_KEYWORDS:
        if kw in q:
            return True
    # Response looks like a pseudo tool-call (model emitted XML-like tags)
    if response and (
        "<parameter>" in response or "<tool_call>" in response or "</tool>" in response
    ):
        return True
    return False


class PermissionRequest:
    """Stores info about a permission request."""

    def __init__(self, request_id: str, tool_name: str, tool_input: dict, risk_level: str):
        self.request_id = request_id
        self.tool_name = tool_name
        self.tool_input = tool_input
        self.risk_level = risk_level
        self.for_session = False


class PermissionRequestManager:
    """Manages pending permission requests for WebSocket clients."""

    def __init__(self):
        self._pending: Dict[str, asyncio.Future] = {}
        self._request_info: Dict[str, PermissionRequest] = {}

    def create_request(
        self, tool_name: str, tool_input: dict, risk_level: str
    ) -> tuple[str, asyncio.Future]:
        """Create a new permission request. Returns (request_id, future)."""
        request_id = f"perm_{uuid.uuid4().hex[:12]}"
        future = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future
        self._request_info[request_id] = PermissionRequest(
            request_id, tool_name, tool_input, risk_level
        )
        return request_id, future

    def resolve_request(
        self, request_id: str, granted: bool, for_session: bool = False
    ) -> tuple[bool, PermissionRequest | None]:
        """Resolve a permission request. Returns (success, request_info)."""
        info = self._request_info.pop(request_id, None)
        if info and for_session:
            info.for_session = True
        future = self._pending.pop(request_id, None)
        if future and not future.done():
            future.set_result((granted, for_session))
            return True, info
        return False, info

    def get_request_info(self, request_id: str) -> PermissionRequest | None:
        """Get request info by id."""
        return self._request_info.get(request_id)

    def cancel_all(self):
        """Cancel all pending requests."""
        for future in self._pending.values():
            if not future.done():
                future.set_exception(asyncio.CancelledError("Server shutting down"))
        self._pending.clear()
        self._request_info.clear()


class UserQuestionRequest:
    """Stores info about a user question request."""

    def __init__(self, request_id: str, question: str, options: list[str] | None):
        self.request_id = request_id
        self.question = question
        self.options = options


class UserQuestionManager:
    """Manages pending user question requests for WebSocket clients."""

    def __init__(self):
        self._pending: Dict[str, asyncio.Future] = {}
        self._request_info: Dict[str, UserQuestionRequest] = {}

    def create_request(
        self, question: str, options: list[str] | None = None
    ) -> tuple[str, asyncio.Future]:
        """Create a new user question request. Returns (request_id, future)."""
        request_id = f"question_{uuid.uuid4().hex[:12]}"
        future = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future
        self._request_info[request_id] = UserQuestionRequest(request_id, question, options)
        return request_id, future

    def resolve_request(
        self, request_id: str, response: str
    ) -> tuple[bool, UserQuestionRequest | None]:
        """Resolve a user question request. Returns (success, request_info)."""
        info = self._request_info.pop(request_id, None)
        future = self._pending.pop(request_id, None)
        if future and not future.done():
            future.set_result(response)
            return True, info
        return False, info

    def cancel_all(self):
        """Cancel all pending requests."""
        for future in self._pending.values():
            if not future.done():
                future.set_exception(asyncio.CancelledError("Server shutting down"))
        self._pending.clear()
        self._request_info.clear()


class WebSocketManager:
    """Manage WebSocket connections and communication with Session-level context."""

    def __init__(self):
        self.clients: Set[Any] = set()
        self.cwd: str = "."
        self.permission_manager = PermissionRequestManager()
        self.question_manager = UserQuestionManager()
        self.current_tasks: Dict[Any, asyncio.Task] = {}  # Track current query tasks per websocket

        # Session-level context management
        # websocket -> session_id (which session this connection is attached to)
        self.client_sessions: Dict[Any, str] = {}
        # session_id -> {query_engine, store, created_at, last_activity}
        self._session_contexts: Dict[str, dict] = {}
        self._session_lock = asyncio.Lock()

        # LoopGuard: detect repetitive tool-call patterns
        from pilotcode.components.repl import LoopGuard

        self.loop_guard = LoopGuard()

    # ------------------------------------------------------------------
    # Session management helpers
    # ------------------------------------------------------------------

    def _generate_session_id(self) -> str:
        return f"sess_{uuid.uuid4().hex[:12]}"

    async def _create_session_context(self, session_id: str) -> dict:
        """Create a new Session context with its own QueryEngine and Store."""
        from dataclasses import replace
        from pilotcode.query_engine import QueryEngine, QueryEngineConfig
        from pilotcode.tools.registry import get_all_tools
        from pilotcode.state.app_state import get_default_app_state
        from pilotcode.state.store import Store
        from pilotcode.utils.config import get_global_config

        store = Store(get_default_app_state())
        store.set_state(lambda s: replace(s, cwd=self.cwd))
        tools = get_all_tools()
        global_cfg = get_global_config()

        def _on_notify(event_type: str, payload: dict) -> None:
            pass  # Notifications are handled per-query in process_query

        query_engine = QueryEngine(
            QueryEngineConfig(
                cwd=self.cwd,
                tools=tools,
                get_app_state=store.get_state,
                set_app_state=lambda f: store.set_state(f),
                on_notify=_on_notify,
                auto_review=global_cfg.auto_review,
                max_review_iterations=global_cfg.max_review_iterations,
            )
        )

        ctx = {
            "session_id": session_id,
            "query_engine": query_engine,
            "store": store,
            "created_at": asyncio.get_event_loop().time(),
            "last_activity": asyncio.get_event_loop().time(),
            "message_count": 0,
        }
        async with self._session_lock:
            self._session_contexts[session_id] = ctx
        print(f"[Session] Created session {session_id}")
        return ctx

    async def _get_or_create_session(self, session_id: str) -> dict:
        """Get existing session or create new one."""
        async with self._session_lock:
            ctx = self._session_contexts.get(session_id)
        if ctx is None:
            ctx = await self._create_session_context(session_id)
        return ctx

    async def _get_session(self, session_id: str) -> dict | None:
        """Get session context if it exists."""
        async with self._session_lock:
            return self._session_contexts.get(session_id)

    async def _delete_session(self, session_id: str) -> bool:
        """Delete a session and its context."""
        async with self._session_lock:
            ctx = self._session_contexts.pop(session_id, None)
        if ctx:
            # Disconnect any websockets attached to this session
            disconnected = []
            for ws, sid in list(self.client_sessions.items()):
                if sid == session_id:
                    self.client_sessions.pop(ws, None)
                    disconnected.append(ws)
            print(f"[Session] Deleted {session_id}, disconnected {len(disconnected)} clients")
            return True
        return False

    async def _list_sessions(self) -> list[dict]:
        """List all active sessions."""
        result = []
        async with self._session_lock:
            for sid, ctx in self._session_contexts.items():
                result.append(
                    {
                        "session_id": sid,
                        "message_count": len(ctx["query_engine"].messages),
                        "created_at": ctx["created_at"],
                        "last_activity": ctx["last_activity"],
                    }
                )
        return result

    def _touch_session(self, session_id: str):
        """Update last activity timestamp for a session."""
        ctx = self._session_contexts.get(session_id)
        if ctx:
            ctx["last_activity"] = asyncio.get_event_loop().time()
            ctx["message_count"] = len(ctx["query_engine"].messages)

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def register(self, websocket):
        """Register a new client."""
        self.clients.add(websocket)
        client_info = getattr(websocket, "remote_address", ("unknown", 0))
        print(f"[WebSocket] Client connected from {client_info}. Total: {len(self.clients)}")

    async def unregister(self, websocket):
        """Unregister a client."""
        self.clients.discard(websocket)
        # Remove connection->session mapping, but DO NOT destroy the session
        self.client_sessions.pop(websocket, None)
        client_info = getattr(websocket, "remote_address", ("unknown", 0))
        print(f"[WebSocket] Client disconnected from {client_info}. Total: {len(self.clients)}")
        # Cancel all pending permissions and questions for this client
        self.permission_manager.cancel_all()
        self.question_manager.cancel_all()

    async def send_to_client(self, websocket, message: dict):
        """Send message to specific client."""
        try:
            await websocket.send(json.dumps(message))
        except websockets.exceptions.ConnectionClosed:
            # Client disconnected, ignore
            pass
        except Exception as e:
            error_str = str(e).lower()
            if "close" in error_str or "connection" in error_str:
                # Client likely disconnected
                pass
            else:
                print(f"[WebSocket] Send error: {e}")

    async def handle_message(self, websocket, message: str):
        """Handle incoming WebSocket message."""
        print(f"[WebSocket] Received message: {message[:100]}...")
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")
            print(f"[WebSocket] Message type: {msg_type}")

            # ------------------------------------------------------------------
            # Session lifecycle management
            # ------------------------------------------------------------------
            if msg_type == "session_create":
                sid = data.get("session_id") or self._generate_session_id()
                await self._get_or_create_session(sid)
                self.client_sessions[websocket] = sid
                await self.send_to_client(
                    websocket,
                    {"type": "session_created", "session_id": sid, "status": "active"},
                )
                print(f"[Session] Client attached to new session {sid}")

            elif msg_type == "session_attach":
                sid = data.get("session_id", "")
                ctx = await self._get_session(sid)
                if ctx is None:
                    # Try to create if not exists (allows re-attaching to saved sessions)
                    ctx = await self._get_or_create_session(sid)
                self.client_sessions[websocket] = sid
                msg_count = len(ctx["query_engine"].messages)
                await self.send_to_client(
                    websocket,
                    {
                        "type": "session_attached",
                        "session_id": sid,
                        "message_count": msg_count,
                        "status": "active",
                    },
                )
                print(f"[Session] Client attached to session {sid} ({msg_count} messages)")

            elif msg_type == "session_list":
                sessions = await self._list_sessions()
                await self.send_to_client(
                    websocket,
                    {"type": "session_list", "sessions": sessions},
                )

            elif msg_type == "session_save":
                sid = self.client_sessions.get(websocket)
                if sid:
                    from pilotcode.services.session_persistence import get_session_persistence
                    from pilotcode.types.message import serialize_messages

                    ctx = await self._get_session(sid)
                    if ctx:
                        persist = get_session_persistence()
                        persist.save_session(
                            session_id=sid,
                            messages=ctx["query_engine"].messages,
                            name=data.get("name", sid),
                            project_path=self.cwd,
                        )
                        await self.send_to_client(
                            websocket,
                            {"type": "session_saved", "session_id": sid},
                        )
                    else:
                        await self.send_to_client(
                            websocket,
                            {"type": "session_error", "error": f"Session not found: {sid}"},
                        )
                else:
                    await self.send_to_client(
                        websocket,
                        {"type": "session_error", "error": "No active session"},
                    )

            elif msg_type == "session_delete":
                sid = data.get("session_id", "")
                success = await self._delete_session(sid)
                await self.send_to_client(
                    websocket,
                    {
                        "type": "session_deleted" if success else "session_error",
                        "session_id": sid,
                    },
                )

            # ------------------------------------------------------------------
            # Query processing (session-aware)
            # ------------------------------------------------------------------
            elif msg_type == "query":
                query = data.get("message", "")
                explicit_sid = data.get("session_id")

                # Determine session: explicit > attached > auto-create
                if explicit_sid:
                    sid = explicit_sid
                    if (
                        websocket not in self.client_sessions
                        or self.client_sessions[websocket] != sid
                    ):
                        self.client_sessions[websocket] = sid
                        await self._get_or_create_session(sid)
                else:
                    sid = self.client_sessions.get(websocket)
                    if not sid:
                        # Check if there's an existing session for this websocket connection
                        # This ensures we reuse the same session for subsequent queries
                        sid = self._generate_session_id()
                        await self._get_or_create_session(sid)
                        self.client_sessions[websocket] = sid
                        await self.send_to_client(
                            websocket,
                            {"type": "session_created", "session_id": sid, "status": "auto"},
                        )

                # Cancel any existing task for this websocket
                if websocket in self.current_tasks:
                    old_task = self.current_tasks[websocket]
                    if not old_task.done():
                        old_task.cancel()
                        print("[Query] Cancelled previous task for client")
                # Process query in background task to avoid blocking message loop
                explicit_mode = data.get("mode")
                task = asyncio.create_task(self.process_query(websocket, sid, query, explicit_mode))
                self.current_tasks[websocket] = task

            elif msg_type == "interrupt":
                print("[WebSocket] Interrupt requested")
                if websocket in self.current_tasks:
                    task = self.current_tasks[websocket]
                    if not task.done():
                        task.cancel()
                        print("[Query] Cancelled task due to interrupt")
                    del self.current_tasks[websocket]
                # Cancel any pending permissions
                self.permission_manager.cancel_all()
                await self.send_to_client(
                    websocket, {"type": "interrupted", "message": "Query interrupted by user"}
                )

            elif msg_type == "permission_response":
                request_id = data.get("request_id", "")
                granted = data.get("granted", False)
                for_session = data.get("for_session", False)
                print(
                    f"[WebSocket] Permission response received: {request_id} = {granted}, for_session={for_session}"
                )
                print(
                    f"[WebSocket] Pending requests before: {list(self.permission_manager._pending.keys())}"
                )

                # Resolve the request
                future = self.permission_manager._pending.get(request_id)
                print(
                    f"[WebSocket] Future for {request_id}: {future}, done={future.done() if future else 'None'}"
                )

                success, info = self.permission_manager.resolve_request(
                    request_id, granted, for_session
                )
                print(f"[WebSocket] Resolve result: success={success}, info={info}")

                # If granted for session, add to session grants
                if success and granted and for_session and info:
                    from pilotcode.permissions.permission_manager import get_permission_manager

                    perm_mgr = get_permission_manager()
                    perm_mgr.grant_session_permission(info.tool_name, info.tool_input)
                    print(f"[Permission] Granted {info.tool_name} for session")

                # Send permission result to client
                await self.send_to_client(
                    websocket,
                    {
                        "type": "permission_result",
                        "request_id": request_id,
                        "granted": granted,
                        "level": "session" if for_session else "once",
                    },
                )

            elif msg_type == "user_question_response":
                request_id = data.get("request_id", "")
                response = data.get("response", "")
                print(f"[WebSocket] User question response received: {request_id} = {response}")

                # Resolve the question request
                success, info = self.question_manager.resolve_request(request_id, response)
                print(f"[WebSocket] Question resolve result: success={success}, info={info}")

            else:
                print(f"[WebSocket] Unknown message type: {msg_type}")

        except json.JSONDecodeError as e:
            print(f"[WebSocket] JSON decode error: {e}")
        except Exception as e:
            print(f"[WebSocket] Handler error: {e}")
            print(traceback.format_exc())

    async def request_permission_via_websocket(
        self, websocket, tool_name: str, tool_input: dict, risk_level: str
    ) -> tuple[bool, bool]:
        """Request permission from client via WebSocket. Returns (granted, for_session)."""
        request_id, future = self.permission_manager.create_request(
            tool_name, tool_input, risk_level
        )

        # Send permission request to client
        try:
            await self.send_to_client(
                websocket,
                {
                    "type": "permission_request",
                    "request_id": request_id,
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "risk_level": risk_level,
                },
            )
            print(f"[Permission] Sent request {request_id} for {tool_name}")
        except Exception as e:
            print(f"[Permission] Failed to send request: {e}")
            self.permission_manager.resolve_request(request_id, False)
            return False, False

        # Wait for response with timeout
        try:
            granted, for_session = await asyncio.wait_for(future, timeout=300.0)
            print(
                f"[Permission] Request {request_id} result: granted={granted}, for_session={for_session}"
            )
            return granted, for_session
        except asyncio.TimeoutError:
            print(f"[Permission] Request {request_id} timed out")
            self.permission_manager.resolve_request(request_id, False)
            return False, False
        except asyncio.CancelledError:
            print(f"[Permission] Request {request_id} was cancelled")
            self.permission_manager.resolve_request(request_id, False)
            raise  # Re-raise to propagate cancellation
        except Exception as e:
            print(f"[Permission] Request {request_id} error: {e}")
            return False, False

    async def request_user_input_via_websocket(
        self, websocket, question: str, options: list[str] | None = None
    ) -> str:
        """Request user input from client via WebSocket. Returns user response string."""
        request_id, future = self.question_manager.create_request(question, options)

        # Send question request to client
        try:
            await self.send_to_client(
                websocket,
                {
                    "type": "user_question_request",
                    "request_id": request_id,
                    "question": question,
                    "options": options,
                },
            )
            print(f"[Question] Sent request {request_id}: {question[:50]}...")
        except Exception as e:
            print(f"[Question] Failed to send request: {e}")
            self.question_manager.resolve_request(request_id, "")
            return ""

        # Wait for response with timeout
        try:
            response = await asyncio.wait_for(future, timeout=300.0)
            print(f"[Question] Request {request_id} result: {response[:50]}...")
            return response
        except asyncio.TimeoutError:
            print(f"[Question] Request {request_id} timed out")
            self.question_manager.resolve_request(request_id, "")
            return ""
        except asyncio.CancelledError:
            print(f"[Question] Request {request_id} was cancelled")
            self.question_manager.resolve_request(request_id, "")
            raise  # Re-raise to propagate cancellation
        except Exception as e:
            print(f"[Question] Request {request_id} error: {e}")
            return ""

    async def process_query(self, websocket, session_id: str, query: str, explicit_mode: str | None = None):
        """Process user query and stream results within a Session context.

        The QueryEngine is retrieved from the session context, ensuring
        multi-turn conversation history persists across queries.
        """
        print(f"[Query] Processing in session {session_id}: {query[:50]}...")

        stream_id = f"stream_{uuid.uuid4().hex[:8]}"

        # Reset LoopGuard for each new query
        self.loop_guard.reset()

        # Retrieve session context (QueryEngine + Store are reused)
        session_ctx = await self._get_session(session_id)
        if session_ctx is None:
            await self.send_to_client(
                websocket,
                {
                    "type": "streaming_error",
                    "stream_id": stream_id,
                    "error": f"Session not found: {session_id}",
                },
            )
            return

        query_engine = session_ctx["query_engine"]
        store = session_ctx["store"]

        try:
            from pilotcode.tools.base import ToolUseContext, ToolResult
            from pilotcode.permissions import get_tool_executor
            from pilotcode.permissions.permission_manager import (
                get_permission_manager,
                PermissionLevel,
            )
            from pilotcode.components.repl import classify_task_complexity
            from pilotcode.orchestration.adapter import MissionAdapter
            from pilotcode.orchestration.report import (
                format_plan,
                format_completion,
                format_failure,
                format_task_event,
            )

            # Send streaming start
            await self.send_to_client(
                websocket, {"type": "streaming_start", "stream_id": stream_id, "message": query}
            )

            # Auto-detect task complexity
            # Allow explicit mode override from client message
            if explicit_mode == "PLAN":
                mode = "PLAN"
            else:
                mode = await classify_task_complexity(query)
            if mode == "PLAN":
                await self.send_to_client(
                    websocket,
                    {
                        "type": "system",
                        "stream_id": stream_id,
                        "content": "Task classified as complex — entering structured PLAN mode with P-EVR orchestration.",
                    },
                )

                cancel_event = asyncio.Event()
                adapter = MissionAdapter(cancel_event=cancel_event)

                async def _ws_progress(event_type: str, data: dict):
                    if event_type == "mission:planned":
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
                        await self.send_to_client(
                            websocket,
                            {
                                "type": "planning_progress",
                                "stream_id": stream_id,
                                "content": plan_text,
                            },
                        )
                    elif event_type in (
                        "task:started",
                        "task:verified",
                        "task:rejected",
                        "task:needs_rework",
                    ):
                        msg = format_task_event(event_type, data)
                        await self.send_to_client(
                            websocket,
                            {
                                "type": "planning_progress",
                                "stream_id": stream_id,
                                "content": msg,
                            },
                        )
                    elif event_type == "mission:blocked":
                        msg = format_task_event(event_type, data)
                        await self.send_to_client(
                            websocket,
                            {
                                "type": "system",
                                "stream_id": stream_id,
                                "content": msg,
                            },
                        )

                result = await adapter.run(query, progress_callback=_ws_progress)

                if result.get("success"):
                    summary = format_completion(result)
                    await self.send_to_client(
                        websocket,
                        {
                            "type": "streaming_complete",
                            "stream_id": stream_id,
                            "content": summary,
                        },
                    )
                else:
                    error = result.get("error", "Unknown error")
                    summary = format_failure(result, error)
                    await self.send_to_client(
                        websocket,
                        {
                            "type": "streaming_error",
                            "stream_id": stream_id,
                            "error": summary,
                        },
                    )
                self._touch_session(session_id)
                return

            # Set up notification handler that routes to this websocket
            def _on_notify(event_type: str, payload: dict) -> None:
                if event_type == "auto_compact":
                    saved = payload.get("tokens_saved", 0)
                    cleared = payload.get("tool_results_cleared", 0)
                    if payload.get("fallback"):
                        content = f"🔄 Auto-compacted context (fallback, ~{saved} tokens saved)"
                    elif cleared > 0:
                        content = f"🔄 Auto-compacted context ({cleared} old tool results cleared, ~{saved} tokens saved)"
                    else:
                        content = f"🔄 Auto-compacted context (~{saved} tokens saved)"
                    asyncio.create_task(
                        self.send_to_client(
                            websocket,
                            {
                                "type": "system",
                                "stream_id": stream_id,
                                "content": content,
                            },
                        )
                    )

            # Attach notification callback to the existing query engine for this query
            query_engine.config.on_notify = _on_notify

            # Set up permission callback for Web mode
            perm_manager = get_permission_manager()

            async def web_permission_callback(permission_request):
                """Callback to request permission via WebSocket."""
                print(f"[Permission] Requesting permission for {permission_request.tool_name}")
                granted, for_session = await self.request_permission_via_websocket(
                    websocket,
                    permission_request.tool_name,
                    permission_request.tool_input,
                    permission_request.risk_level,
                )
                if for_session:
                    return PermissionLevel.ALWAYS_ALLOW
                return PermissionLevel.ALLOW if granted else PermissionLevel.DENY

            perm_manager.set_permission_callback(web_permission_callback)

            # ------------------------------------------------------------------
            # Four-layer rendering helpers (localized to this query scope)
            # ------------------------------------------------------------------
            async def _render_status(event_type: str, **kwargs):
                pass  # Placeholder for future status-bar updates

            async def _render_conversational_chunk(chunk: str):
                await self.send_to_client(
                    websocket, {"type": "streaming_chunk", "stream_id": stream_id, "chunk": chunk}
                )

            async def _render_conversational_tool_call(tool_name: str, tool_input: dict):
                await self.send_to_client(
                    websocket,
                    {
                        "type": "tool_call",
                        "stream_id": stream_id,
                        "tool_name": tool_name,
                        "tool_input": tool_input,
                    },
                )

            async def _render_system(content: str):
                await self.send_to_client(
                    websocket, {"type": "system", "stream_id": stream_id, "content": content}
                )

            async def _render_error(content: str):
                await self.send_to_client(
                    websocket, {"type": "streaming_error", "stream_id": stream_id, "error": content}
                )

            # ------------------------------------------------------------------
            # Process query
            full_content = ""
            sent_content_length = 0  # Track how much content has been sent to avoid duplicates
            max_iterations = 50
            iteration = 0
            is_continue_query = False  # Track if this is an internal continuation
            consecutive_permission_denied = (
                0  # Track consecutive permission denials to prevent loops
            )

            while iteration < max_iterations:
                iteration += 1
                print(f"[Query] Iteration {iteration}, query={query[:50]}...")

                # Check if task was cancelled
                if asyncio.current_task().cancelled():
                    print("[Query] Task cancelled, breaking loop")
                    break

                pending_tools = []

                async for result in query_engine.submit_message(query):
                    # Check for cancellation frequently during streaming
                    if asyncio.current_task().cancelled():
                        print("[Query] Task cancelled during streaming, breaking")
                        raise asyncio.CancelledError()

                    msg = result.message
                    msg_type = msg.__class__.__name__

                    # Handle thinking content
                    if msg_type == "ThinkingMessage" or (hasattr(msg, "thinking") and msg.thinking):
                        thinking_content = getattr(msg, "thinking", "") or (
                            msg.content if hasattr(msg, "content") else ""
                        )
                        if thinking_content:
                            await self.send_to_client(
                                websocket,
                                {
                                    "type": "thinking",
                                    "stream_id": stream_id,
                                    "content": thinking_content,
                                },
                            )

                    # Handle streaming content
                    elif hasattr(msg, "content") and msg.content and isinstance(msg.content, str):
                        if result.is_complete:
                            # Store complete content - will be sent after tools or immediately if no tools
                            full_content = msg.content
                        elif not is_continue_query:
                            # Stream incremental content for user queries only
                            # Skip streaming for continue queries to avoid showing internal prompts
                            content = msg.content
                            if len(content) > sent_content_length:
                                new_content = content[sent_content_length:]
                                await self.send_to_client(
                                    websocket,
                                    {
                                        "type": "streaming_chunk",
                                        "stream_id": stream_id,
                                        "chunk": new_content,
                                    },
                                )
                                sent_content_length = len(content)

                    # Handle tool use
                    elif msg_type == "ToolUseMessage":
                        pending_tools.append(msg)
                        await _render_conversational_tool_call(msg.name, msg.input)

                # No more tools to execute - this is the final response
                if not pending_tools:
                    # ---- Tool-call reinforcement: if user explicitly asked for a tool
                    # but the model answered directly without calling it, nudge once.
                    if (
                        iteration == 1
                        and not is_continue_query
                        and _should_use_tools(query, full_content)
                    ):
                        reinforce_msg = (
                            "The user explicitly requested a tool operation. "
                            "You MUST call the appropriate tool instead of answering in text. "
                            "Do NOT explain your plan — just call the tool now."
                        )
                        query_engine.messages.append(SystemMessage(content=reinforce_msg))
                        print("[Query] Tool reinforcement triggered, retrying with system nudge")
                        query = "Please execute the requested tool operation now."
                        is_continue_query = True
                        sent_content_length = 0
                        continue

                    # Send final content if any (only the new part)
                    if full_content:
                        if len(full_content) > sent_content_length:
                            new_content = full_content[sent_content_length:]
                            await self.send_to_client(
                                websocket,
                                {
                                    "type": "streaming_chunk",
                                    "stream_id": stream_id,
                                    "chunk": new_content,
                                },
                            )
                        full_content = ""
                    break

                # ---- LoopGuard: detect repetitive tool-call patterns ----
                loop_reason = self.loop_guard.record(pending_tools)
                if loop_reason:
                    self.loop_guard.loop_count += 1
                    print(f"[LoopGuard] {loop_reason} — blocking {len(pending_tools)} tool(s)")
                    await _render_system(
                        f"[LOOP GUARD] {loop_reason}. Repeating tool calls detected. "
                        "Forcing final answer."
                    )
                    # Block all pending tools and inject error results
                    for tool_msg in pending_tools:
                        forced_result = (
                            f"[SYSTEM ERROR] LOOP DETECTED: {loop_reason}. "
                            f"Tool execution has been blocked. You MUST provide your final answer NOW "
                            f"without any more tool calls."
                        )
                        query_engine.add_tool_result(
                            tool_msg.tool_use_id, forced_result, is_error=True
                        )
                    # Force the model to summarize instead of continuing exploration
                    query = (
                        "CRITICAL: You are in a tool-call loop. All pending tool calls were blocked. "
                        "Summarize what you have done so far and declare completion. "
                        "Do NOT call any more tools."
                    )
                    is_continue_query = True
                    sent_content_length = 0
                    continue

                # Check if we've reached max iterations
                if iteration >= max_iterations:
                    print(f"[Query] Reached max iterations ({max_iterations}), forcing end")
                    if full_content:
                        if len(full_content) > sent_content_length:
                            new_content = full_content[sent_content_length:]
                            await self.send_to_client(
                                websocket,
                                {
                                    "type": "streaming_chunk",
                                    "stream_id": stream_id,
                                    "chunk": new_content,
                                },
                            )
                    # -- System Layer: max iterations reached --
                    await _render_system(
                        f"⏹️  Reached maximum tool iterations ({max_iterations}). Task paused. Send another message to continue."
                    )
                    break

                # Send final content for user-facing queries (not the final response)
                if full_content and not is_continue_query:
                    if len(full_content) > sent_content_length:
                        new_content = full_content[sent_content_length:]
                        await self.send_to_client(
                            websocket,
                            {
                                "type": "streaming_chunk",
                                "stream_id": stream_id,
                                "chunk": new_content,
                            },
                        )
                        sent_content_length = len(full_content)
                    full_content = ""

                print(f"[Query] Executing {len(pending_tools)} tools...")

                # Notify client that tools are about to run (keeps connection alive
                # during long-running operations like CodeIndex)
                for tool_msg in pending_tools:
                    await self.send_to_client(
                        websocket,
                        {
                            "type": "tool_progress",
                            "stream_id": stream_id,
                            "tool_name": tool_msg.name,
                            "line": f"Executing {tool_msg.name}...",
                            "is_progress": True,
                        },
                    )

                # Get tool executor
                tool_executor = get_tool_executor()

                for tool_msg in pending_tools:
                    # Check for cancellation before executing each tool
                    if asyncio.current_task().cancelled():
                        print("[Query] Task cancelled before tool execution, breaking")
                        raise asyncio.CancelledError()

                    # Special handling for AskUser tool in Web mode
                    # Check both primary name and aliases
                    ask_user_aliases = {"AskUser", "ask", "question"}
                    print(
                        f"[AskUser] Checking tool: {tool_msg.name}, aliases: {ask_user_aliases}, match: {tool_msg.name in ask_user_aliases}"
                    )
                    if tool_msg.name in ask_user_aliases:
                        question = tool_msg.input.get("question", "")
                        options = tool_msg.input.get("options")
                        print(f"[AskUser] Intercepted! Question: {question[:50]}...")

                        # Send tool use notification
                        await self.send_to_client(
                            websocket,
                            {
                                "type": "tool_use",
                                "stream_id": stream_id,
                                "tool_name": "AskUser",
                                "tool_input": tool_msg.input,
                            },
                        )

                        # Request user input via WebSocket
                        user_response = await self.request_user_input_via_websocket(
                            websocket, question, options
                        )

                        # Create tool result
                        from pilotcode.tools.base import ToolResult
                        from pilotcode.tools.ask_user_tool import AskUserOutput
                        from pilotcode.permissions.tool_executor import ToolExecutionResult

                        result_data = AskUserOutput(response=user_response, question=question)
                        exec_result = ToolExecutionResult(
                            success=True,
                            result=ToolResult(data=result_data),
                            permission_granted=True,
                            message="Success",
                            tool_name="AskUser",
                        )
                    else:
                        context = ToolUseContext(
                            get_app_state=store.get_state,
                            set_app_state=lambda f: store.set_state(f),
                            cwd=getattr(store.get_state(), "cwd", ""),
                        )

                        def _send_tool_progress(data):
                            if isinstance(data, dict) and data.get("type") == "bash_output":
                                line = data.get("line", "")
                                if line:
                                    asyncio.create_task(
                                        self.send_to_client(
                                            websocket,
                                            {
                                                "type": "tool_progress",
                                                "stream_id": stream_id,
                                                "tool_name": tool_msg.name,
                                                "line": line,
                                                "is_progress": data.get("is_progress", False),
                                            },
                                        )
                                    )

                        exec_result = await tool_executor.execute_tool_by_name(
                            tool_msg.name, tool_msg.input, context, on_progress=_send_tool_progress
                        )

                    result_content = ""
                    if exec_result.success and exec_result.result:
                        result_content = (
                            str(exec_result.result.data) if exec_result.result.data else "Success"
                        )
                        consecutive_permission_denied = 0  # Reset on success
                    else:
                        result_content = exec_result.message
                        # Check if this is a permission denial
                        if (
                            "Permission denied" in result_content
                            or "permission" in result_content.lower()
                        ):
                            consecutive_permission_denied += 1
                            print(
                                f"[Query] Permission denied count: {consecutive_permission_denied}"
                            )
                            if consecutive_permission_denied >= 2:
                                # Stop the loop - user has denied permission multiple times
                                await self.send_to_client(
                                    websocket,
                                    {
                                        "type": "streaming_chunk",
                                        "stream_id": stream_id,
                                        "chunk": "\n\n[Permission denied. Cannot continue with file modifications without user consent.]",
                                    },
                                )
                                await self.send_to_client(
                                    websocket, {"type": "streaming_end", "stream_id": stream_id}
                                )
                                return

                    query_engine.add_tool_result(
                        tool_msg.tool_use_id, result_content, is_error=not exec_result.success
                    )

                    await self.send_to_client(
                        websocket,
                        {
                            "type": "tool_result",
                            "stream_id": stream_id,
                            "tool_name": tool_msg.name,
                            "result": result_content,
                            "success": exec_result.success,
                        },
                    )

                # Switch to internal continuation query
                query = "Please continue based on the tool results above."
                is_continue_query = True
                # Reset content length tracking for new response
                sent_content_length = 0

            # Send any remaining content and completion signal
            if full_content and len(full_content) > sent_content_length:
                await self.send_to_client(
                    websocket,
                    {
                        "type": "streaming_chunk",
                        "stream_id": stream_id,
                        "chunk": full_content[sent_content_length:],
                    },
                )
            await self.send_to_client(
                websocket, {"type": "streaming_complete", "stream_id": stream_id}
            )
            print("[Query] Done")

        except asyncio.CancelledError:
            print("[Query] Query was cancelled")
            await self.send_to_client(
                websocket,
                {"type": "streaming_error", "stream_id": stream_id, "error": "Query interrupted"},
            )
            raise  # Re-raise to propagate cancellation
        except Exception as e:
            print(f"[Query] Error: {e}")
            print(traceback.format_exc())
            await self.send_to_client(
                websocket, {"type": "streaming_error", "stream_id": stream_id, "error": str(e)}
            )
        finally:
            # Clean up task tracking
            if websocket in self.current_tasks:
                del self.current_tasks[websocket]
            # Update session activity
            self._touch_session(session_id)


ws_manager = WebSocketManager()


async def websocket_handler(websocket):
    """Handle WebSocket connections."""
    import websockets

    try:
        print(f"[WebSocket] Connection from {websocket.remote_address}")
        await ws_manager.register(websocket)
        try:
            async for message in websocket:
                await ws_manager.handle_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            error_str = str(e).lower()
            if "connection" not in error_str and "closed" not in error_str:
                print(f"[WebSocket] Handler error: {e}")
    except Exception as e:
        error_str = str(e).lower()
        if "connection" not in error_str and "handshake" not in error_str:
            print(f"[WebSocket] Connection error: {e}")
    finally:
        try:
            await ws_manager.unregister(websocket)
        except Exception:
            pass


class CustomHTTPHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler for serving static files."""

    def __init__(self, *args, **kwargs):
        web_dir = Path(__file__).parent / "static"
        super().__init__(*args, directory=str(web_dir), **kwargs)

    def log_message(self, format, *args):
        print(f"[HTTP] {args[0]}" if args else "[HTTP] request")

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


def run_http_server(host: str, port: int):
    """Run HTTP server."""
    try:
        server = HTTPServer((host, port), CustomHTTPHandler)
        print(f"[HTTP] Server running on http://{host}:{port}")
        server.serve_forever()
    except Exception as e:
        print(f"[HTTP] Server error: {e}")


def run_websocket_server_sync(host: str, port: int):
    """Run WebSocket server (synchronous wrapper)."""
    import websockets

    async def safe_websocket_handler(websocket, path=None):
        """Wrapper to handle connection errors gracefully."""
        try:
            await websocket_handler(websocket)
        except websockets.exceptions.InvalidMessage:
            pass
        except websockets.exceptions.ConnectionClosed:
            pass
        except EOFError:
            print("[WebSocket] Client disconnected during handshake")
        except Exception as e:
            if "connection closed" not in str(e).lower():
                print(f"[WebSocket] Handler error: {e}")

    async def ws_main():
        print(f"[WebSocket] Starting server on ws://{host}:{port}")
        try:
            async with websockets.serve(
                safe_websocket_handler,
                host,
                port,
                ping_interval=20,
                ping_timeout=10,
                origins=None,
            ):
                print(f"[WebSocket] Server running on ws://{host}:{port}")
                await asyncio.Future()
        except Exception as e:
            print(f"[WebSocket] Server error: {e}")

    try:
        asyncio.run(ws_main())
    except KeyboardInterrupt:
        print("\n[WebSocket] Server stopped by user")
    except Exception as e:
        print(f"[WebSocket] Fatal error: {e}")


def run_server_standalone(host: str = "127.0.0.1", port: int = 8080, cwd: str = "."):
    """Run both HTTP and WebSocket servers."""
    ws_manager.cwd = cwd

    print("=" * 60)
    print("PilotCode Web UI Server")
    print("=" * 60)
    print(f"Working directory: {cwd}")
    print(f"Python: {sys.executable}")
    print()

    http_thread = threading.Thread(target=run_http_server, args=(host, port), daemon=True)
    http_thread.start()

    run_websocket_server_sync(host, port + 1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--cwd", default=".")
    args = parser.parse_args()

    run_server_standalone(args.host, args.port, args.cwd)
