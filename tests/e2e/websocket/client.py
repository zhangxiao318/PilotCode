"""WebSocket test client for PilotCode LLM E2E tests.

Provides a programmatic interface to interact with the PilotCode
WebSocket server for session-level multi-turn conversation testing.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class QueryResult:
    """Result of a single query round."""

    success: bool
    response: str = ""
    tool_calls: list[str] = field(default_factory=list)
    tool_results: list[str] = field(default_factory=list)
    system_messages: list[str] = field(default_factory=list)
    error: str = ""
    stream_id: str = ""


@dataclass
class SessionInfo:
    """Information about a server-side session."""

    session_id: str
    message_count: int = 0
    status: str = ""


class PilotCodeWebSocketClient:
    """Async WebSocket client for PilotCode session-level testing.

    Usage:
        client = PilotCodeWebSocketClient("ws://127.0.0.1:18081")
        await client.connect()
        session_id = await client.create_session()

        result = await client.query("Analyze this project")
        assert "pilotcode" in result.response.lower()

        result2 = await client.query("What files did you find?")
        assert result2.success
    """

    def __init__(self, ws_url: str, default_timeout: float = 120.0):
        self.ws_url = ws_url
        self.default_timeout = default_timeout
        self._ws = None
        self._receive_task = None
        self._message_queues: dict[str, asyncio.Queue] = {}
        self._current_stream_id: str | None = None
        self.session_id: str | None = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        import websockets

        self._ws = await websockets.connect(self.ws_url)
        self._message_queues["_global"] = asyncio.Queue()
        self._receive_task = asyncio.create_task(self._receive_loop())

    async def close(self) -> None:
        """Close connection and cleanup."""
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
            self._ws = None

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def create_session(self, session_id: str | None = None) -> str:
        """Create a new session on the server and attach this connection.

        Returns:
            The session_id (server-generated or user-provided).
        """
        await self._send({"type": "session_create", "session_id": session_id})
        resp = await self._wait_for("session_created", timeout=60.0)
        self.session_id = resp["session_id"]
        return self.session_id

    async def attach_session(self, session_id: str) -> SessionInfo:
        """Attach this connection to an existing session."""
        await self._send({"type": "session_attach", "session_id": session_id})
        resp = await self._wait_for("session_attached", timeout=60.0)
        self.session_id = resp["session_id"]
        return SessionInfo(
            session_id=resp["session_id"],
            message_count=resp.get("message_count", 0),
            status=resp.get("status", ""),
        )

    async def list_sessions(self) -> list[dict]:
        """List all active sessions on the server."""
        await self._send({"type": "session_list"})
        resp = await self._wait_for("session_list", timeout=5.0)
        return resp.get("sessions", [])

    async def save_session(self, name: str | None = None) -> bool:
        """Save the current session to disk."""
        if not self.session_id:
            raise RuntimeError("No active session")
        await self._send({"type": "session_save", "name": name or self.session_id})
        resp = await self._wait_for("session_saved", timeout=5.0)
        return resp.get("session_id") == self.session_id

    async def delete_session(self, session_id: str | None = None) -> bool:
        """Delete a session."""
        sid = session_id or self.session_id
        if not sid:
            raise RuntimeError("No session specified")
        await self._send({"type": "session_delete", "session_id": sid})
        resp = await self._wait_for("session_deleted", timeout=5.0)
        if sid == self.session_id:
            self.session_id = None
        return resp.get("session_id") == sid

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    async def query(
        self,
        message: str,
        session_id: str | None = None,
        timeout: float | None = None,
        progress_callback: Callable[[str, dict], None] | None = None,
    ) -> QueryResult:
        """Send a query and collect the complete response.

        This is the core method for multi-turn testing. It sends a query
        to the server, waits for the full response (including any tool
        calls and their results), and returns a structured result.

        Args:
            message: The user message to send.
            session_id: Optional override. Uses attached session by default.
            timeout: Max seconds to wait for completion.
            progress_callback: Optional callback for streaming progress.

        Returns:
            QueryResult with response text, tool calls, and metadata.
        """
        sid = session_id or self.session_id
        if not sid:
            raise RuntimeError(
                "No active session. Call create_session() or attach_session() first."
            )

        timeout = timeout or self.default_timeout

        # Drain any stale messages before sending
        await self._drain_queue()

        await self._send({"type": "query", "message": message, "session_id": sid})

        result = QueryResult(success=True)
        chunks: list[str] = []
        deadline = asyncio.get_event_loop().time() + timeout

        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                result.success = False
                result.error = f"Timeout after {timeout}s"
                break

            try:
                # Per-recv timeout: if the server is silent for this long we assume
                # something is wrong. Tool-execution heartbeats (tool_progress)
                # keep the connection alive during legitimate long operations.
                recv_timeout = min(remaining, 45.0)
                msg = await asyncio.wait_for(self._recv_any(), timeout=recv_timeout)
            except asyncio.TimeoutError:
                result.success = False
                result.error = "Timeout waiting for server response"
                break

            msg_type = msg.get("type")
            stream_id = msg.get("stream_id", "")

            if msg_type == "streaming_start":
                result.stream_id = stream_id
                self._current_stream_id = stream_id

            elif msg_type == "streaming_chunk":
                chunk = msg.get("chunk", "")
                chunks.append(chunk)
                if progress_callback:
                    progress_callback("chunk", {"chunk": chunk, "stream_id": stream_id})

            elif msg_type == "streaming_complete":
                # Planning mode returns this instead of streaming_end
                result.response = msg.get("content", "")
                result.success = True
                break

            elif msg_type == "streaming_end":
                result.response = "".join(chunks)
                result.success = True
                break

            elif msg_type == "streaming_error":
                result.success = False
                result.error = msg.get("error", "Unknown error")
                break

            elif msg_type == "tool_call":
                result.tool_calls.append(msg.get("tool_name", ""))
                if progress_callback:
                    progress_callback("tool_call", msg)

            elif msg_type == "tool_result":
                result.tool_results.append(msg.get("tool_name", ""))
                if progress_callback:
                    progress_callback("tool_result", msg)

            elif msg_type == "tool_progress":
                # Server heartbeat during long-running tool execution
                if progress_callback:
                    progress_callback("tool_progress", msg)

            elif msg_type == "tool_use":
                # AskUser tool use notification
                result.tool_calls.append(msg.get("tool_name", ""))

            elif msg_type == "user_question_request":
                # Auto-reply to server-side AskUser prompts so tests don't hang
                await self._send(
                    {
                        "type": "user_question_response",
                        "request_id": msg.get("request_id", ""),
                        "response": "yes",
                    }
                )

            elif msg_type == "permission_request":
                # Auto-approve all tool permissions so tests don't hang
                await self._send(
                    {
                        "type": "permission_response",
                        "request_id": msg.get("request_id", ""),
                        "granted": True,
                        "for_session": True,
                    }
                )

            elif msg_type == "system":
                result.system_messages.append(msg.get("content", ""))

            elif msg_type == "interrupted":
                result.success = False
                result.error = "Interrupted by user"
                break

            elif msg_type == "thinking":
                if progress_callback:
                    progress_callback("thinking", msg)

            elif msg_type in ("session_created", "session_attached"):
                # These may come through if auto-created; store them but continue
                pass

            else:
                # Unknown message type - log but continue
                pass

        self._current_stream_id = None
        return result

    async def interrupt(self) -> None:
        """Send an interrupt signal to stop the current query."""
        await self._send({"type": "interrupt"})

    # ------------------------------------------------------------------
    # Low-level I/O
    # ------------------------------------------------------------------

    async def _send(self, data: dict) -> None:
        if self._ws is None:
            raise RuntimeError("WebSocket not connected")
        await self._ws.send(json.dumps(data))

    async def _recv_any(self) -> dict:
        """Receive the next message from the global queue."""
        queue = self._message_queues.get("_global")
        if queue is None:
            raise RuntimeError("Client not connected")
        msg = await queue.get()
        return msg

    async def _wait_for(self, msg_type: str, timeout: float = 5.0) -> dict:
        """Wait for a specific message type."""
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for {msg_type}")
            msg = await asyncio.wait_for(self._recv_any(), timeout=remaining)
            if msg.get("type") == msg_type:
                return msg
            # If we get an error for our request, propagate it
            if msg.get("type") == "session_error":
                raise RuntimeError(f"Session error: {msg.get('error')}")

    async def _drain_queue(self) -> None:
        """Remove any stale messages from the queue."""
        queue = self._message_queues.get("_global")
        if queue is None:
            return
        while not queue.empty():
            try:
                queue.get_nowait()
                queue.task_done()
            except asyncio.QueueEmpty:
                break

    async def _receive_loop(self) -> None:
        """Background task that continuously receives messages."""
        queue = self._message_queues["_global"]
        try:
            while True:
                if self._ws is None:
                    break
                raw = await self._ws.recv()
                data = json.loads(raw)
                await queue.put(data)
        except Exception:
            # Connection closed or other error
            pass
