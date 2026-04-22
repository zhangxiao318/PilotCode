"""In-memory session management for Daemon."""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

from ..components.repl import run_headless, classify_task_complexity, run_headless_with_planning
from ..services.session_persistence import (
    get_session_persistence,
    save_session as persist_save,
    load_session as persist_load,
)
from ..types.message import Message


@dataclass
class Session:
    """An active session in the daemon."""

    session_id: str
    cwd: str
    messages: list[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    auto_allow: bool = True
    max_iterations: int = 50

    def touch(self):
        """Update last activity time."""
        self.last_activity = time.time()

    def is_expired(self, timeout_seconds: float = 3600) -> bool:
        """Check if session has expired due to inactivity."""
        return time.time() - self.last_activity > timeout_seconds


class SessionManager:
    """Manages multiple sessions in memory."""

    def __init__(self, persist_enabled: bool = True):
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()
        self._persist_enabled = persist_enabled
        self._persistence = get_session_persistence() if persist_enabled else None
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start background tasks."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        """Stop and cleanup."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Persist all sessions before exit
        if self._persist_enabled:
            async with self._lock:
                for session in self._sessions.values():
                    await self._persist_session(session)

    async def create_session(
        self, session_id: Optional[str] = None, cwd: str = ".", restore_from_disk: bool = True
    ) -> Session:
        """Create a new session or restore existing one."""
        async with self._lock:
            if session_id is None:
                session_id = f"daemon_{int(time.time() * 1000)}"

            # Check if already in memory
            if session_id in self._sessions:
                return self._sessions[session_id]

            # Try to restore from disk
            messages = []
            if restore_from_disk and self._persist_enabled:
                result = persist_load(session_id)
                if result:
                    messages, _ = result

            session = Session(session_id=session_id, cwd=cwd, messages=messages)
            self._sessions[session_id] = session
            return session

    async def get_session(self, session_id: str) -> Optional[Session]:
        """Get an existing session."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.touch()
            return session

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                if self._persist_enabled:
                    self._persistence.delete_session(session_id)
                return True
            return False

    async def list_sessions(self) -> list[dict]:
        """List all active sessions."""
        async with self._lock:
            result = []
            for s in self._sessions.values():
                result.append(
                    {
                        "session_id": str(s.session_id),
                        "cwd": str(s.cwd),
                        "message_count": int(len(s.messages)),
                        "created_at": float(s.created_at),
                        "last_activity": float(s.last_activity),
                    }
                )
            return result

    async def execute_query(
        self,
        session_id: str,
        query: str,
        stream_callback: Optional[callable] = None,
        cwd: Optional[str] = None,
    ) -> dict:
        """Execute a query in a session."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise ValueError(f"Session not found: {session_id}")
            session.touch()

        # Use provided cwd or fall back to session's cwd
        effective_cwd = cwd or session.cwd

        # Execute query (outside lock to allow concurrent queries on different sessions)
        try:
            if not session.messages:
                mode = await classify_task_complexity(query)
                if mode == "PLAN":
                    result = await run_headless_with_planning(
                        prompt=query,
                        auto_allow=session.auto_allow,
                        json_mode=True,
                        max_iterations=session.max_iterations,
                        cwd=effective_cwd,
                        progress_callback=lambda msg: None,
                    )
                else:
                    result = await run_headless(
                        prompt=query,
                        auto_allow=session.auto_allow,
                        json_mode=True,
                        max_iterations=session.max_iterations,
                        cwd=effective_cwd,
                    )
            else:
                result = await run_headless(
                    prompt=query,
                    auto_allow=session.auto_allow,
                    json_mode=True,
                    max_iterations=session.max_iterations,
                    # Pass existing messages as context
                    initial_messages=session.messages,
                    # Use effective cwd for tool execution
                    cwd=effective_cwd,
                )

            # Update session messages with new conversation
            if "messages" in result:
                session.messages = result["messages"]

            # Persist session after each query
            if self._persist_enabled:
                await self._persist_session(session)

            # Clean result for JSON serialization
            return self._clean_result(result)

        except Exception as e:
            return {"success": False, "error": str(e), "response": f"Error: {e}"}

    async def _persist_session(self, session: Session):
        """Save session to disk."""
        if not self._persist_enabled or not self._persistence:
            return

        try:
            persist_save(
                session_id=session.session_id,
                messages=session.messages,
                project_path=session.cwd,
            )
        except Exception as e:
            print(f"[Daemon] Failed to persist session {session.session_id}: {e}")

    def _clean_result(self, result: dict) -> dict:
        """Clean result to ensure JSON serialization."""
        cleaned = {}
        for key, value in result.items():
            if key == "messages":
                # Convert message objects to plain dicts
                cleaned[key] = []
                for msg in value:
                    if hasattr(msg, "content"):
                        # Pydantic models have 'type' field (user/assistant)
                        role = getattr(msg, "type", None) or getattr(msg, "role", "unknown")
                        cleaned[key].append({"role": str(role), "content": str(msg.content)})
                    elif isinstance(msg, dict):
                        cleaned[key].append(msg)
            elif isinstance(value, (str, int, float, bool, list, dict)) or value is None:
                cleaned[key] = value
            else:
                cleaned[key] = str(value)
        return cleaned

    async def _cleanup_loop(self):
        """Periodically cleanup expired sessions."""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Daemon] Cleanup error: {e}")

    async def _cleanup_expired(self):
        """Remove expired sessions."""
        async with self._lock:
            expired = [sid for sid, s in self._sessions.items() if s.is_expired()]
            for sid in expired:
                session = self._sessions[sid]
                await self._persist_session(session)
                del self._sessions[sid]
                print(f"[Daemon] Cleaned up expired session: {sid}")
