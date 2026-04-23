"""PilotCode Daemon Server - TCP-based for Windows compatibility."""

from __future__ import annotations

import asyncio
import sys
import os
from pathlib import Path
from typing import Optional, Callable

# Set UTF-8 encoding for Windows
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    # Set console code page to UTF-8
    os.system("chcp 65001 >nul 2>&1")

from .protocol import Request, Response, ErrorCode
from .session_manager import SessionManager


def make_json_serializable(obj):
    """Convert object to JSON serializable format."""
    if obj is None:
        return None
    elif isinstance(obj, (str, int, float, bool)):
        return obj
    elif isinstance(obj, (list, tuple)):
        return [make_json_serializable(item) for item in obj]
    elif isinstance(obj, dict):
        return {str(k): make_json_serializable(v) for k, v in obj.items()}
    elif hasattr(obj, "to_dict"):  # Objects with to_dict method
        return make_json_serializable(obj.to_dict())
    elif hasattr(obj, "__dict__"):
        # Convert dataclass/object to dict
        result = {}
        for k, v in obj.__dict__.items():
            if not k.startswith("_"):
                try:
                    result[str(k)] = make_json_serializable(v)
                except (TypeError, ValueError):
                    result[str(k)] = str(v)
        return result
    elif hasattr(obj, "content"):  # Message-like objects
        role = getattr(obj, "role", "unknown")
        return {"role": str(role), "content": str(obj.content), "type": obj.__class__.__name__}
    else:
        return str(obj)


class DaemonServer:
    """TCP-based JSON-RPC server for PilotCode."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.port = port
        self.session_manager = SessionManager(persist_enabled=True)
        self._running = False
        self.server: Optional[asyncio.Server] = None
        self._clients: set[asyncio.StreamWriter] = set()

    async def start(self):
        """Start the TCP server."""
        self.server = await asyncio.start_server(self._handle_client, self.host, self.port)

        # Get the actual port (if 0 was passed)
        addr = self.server.sockets[0].getsockname()
        self.port = addr[1]

        print(f"[Daemon] Server listening on {self.host}:{self.port}", file=sys.stderr)

        # Write port to file for client discovery
        port_file = Path.home() / ".pilotcode" / "daemon.port"
        port_file.parent.mkdir(parents=True, exist_ok=True)
        port_file.write_text(str(self.port))

        await self.session_manager.start()
        self._running = True

        async with self.server:
            await self.server.serve_forever()

    async def stop(self):
        """Stop the server."""
        print("[Daemon] Stopping...", file=sys.stderr)
        self._running = False

        # Close all client connections
        for writer in list(self._clients):
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

        if self.server:
            self.server.close()
            await self.server.wait_closed()

        await self.session_manager.stop()

        # Remove port file
        port_file = Path.home() / ".pilotcode" / "daemon.port"
        if port_file.exists():
            port_file.unlink()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a client connection."""
        addr = writer.get_extra_info("peername")
        print(f"[Daemon] Client connected: {addr}", file=sys.stderr)
        self._clients.add(writer)

        buffer = ""
        try:
            while self._running:
                data = await reader.read(4096)
                if not data:
                    break

                buffer += data.decode("utf-8")

                # Process complete messages (newline delimited)
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if line:
                        response = await self._handle_request(line)
                        if response:
                            writer.write(response.to_json().encode("utf-8"))
                            await writer.drain()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[Daemon] Client error: {e}", file=sys.stderr)
        finally:
            print(f"[Daemon] Client disconnected: {addr}", file=sys.stderr)
            self._clients.discard(writer)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _handle_request(self, line: str) -> Optional[Response]:
        """Handle a single request."""
        try:
            request = Request.from_json(line)
        except Exception:
            return Response.error_response(id=0, code=ErrorCode.PARSE_ERROR, message="Invalid JSON")

        if not request:
            return Response.error_response(
                id=0, code=ErrorCode.PARSE_ERROR, message="Invalid request"
            )

        handler = self._get_handler(request.method)
        if not handler:
            return Response.error_response(
                id=request.id,
                code=ErrorCode.METHOD_NOT_FOUND,
                message=f"Method not found: {request.method}",
            )

        try:
            result = await handler(request.params)
            return Response.success(id=request.id, result=result)
        except Exception as e:
            print(f"[Daemon] Handler error: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc()
            return Response.error_response(
                id=request.id, code=ErrorCode.INTERNAL_ERROR, message=str(e)
            )

    def _get_handler(self, method: str) -> Optional[Callable]:
        """Get handler for a method."""
        handlers = {
            "initialize": self._handle_initialize,
            "query": self._handle_query,
            "createSession": self._handle_create_session,
            "deleteSession": self._handle_delete_session,
            "listSessions": self._handle_list_sessions,
            "getSessionHistory": self._handle_get_session_history,
            "shutdown": self._handle_shutdown,
        }
        return handlers.get(method)

    # Handlers

    async def _handle_initialize(self, params: dict) -> dict:
        """Initialize the daemon."""
        return {
            "protocolVersion": "1.0",
            "serverInfo": {"name": "pilotcode-daemon", "version": "0.2.0"},
            "capabilities": {
                "streaming": False,
                "sessionManagement": True,
                "tools": True,
            },
        }

    async def _handle_query(self, params: dict) -> dict:
        """Execute a query in a session."""
        session_id = params.get("sessionId")
        message = params.get("message", "")
        cwd = params.get("cwd") or "."

        if not message:
            raise ValueError("Message is required")

        # Get or create session
        if not session_id:
            # New session: use cwd from params
            session = await self.session_manager.create_session(cwd=cwd)
            session_id = session.session_id
            effective_cwd = cwd
        else:
            session = await self.session_manager.get_session(session_id)
            if not session:
                # Session not found, create new one with given cwd
                session = await self.session_manager.create_session(session_id=session_id, cwd=cwd)
                effective_cwd = cwd
            else:
                # Existing session: use session's saved cwd
                # But update if params provides a different cwd (user switched project)
                if cwd != session.cwd and cwd != ".":
                    session.cwd = cwd
                    effective_cwd = cwd
                else:
                    effective_cwd = session.cwd

        result = await self.session_manager.execute_query(
            session_id=session_id, query=message, cwd=effective_cwd
        )

        # Ensure result is JSON serializable - only extract primitive fields
        response_text = ""
        if "response" in result:
            response_text = str(result["response"])
        elif "error" in result:
            response_text = f"Error: {result['error']}"

        return {
            "sessionId": str(session_id),
            "response": response_text,
            "success": bool(result.get("success", False)),
        }

    async def _handle_create_session(self, params: dict) -> dict:
        """Create a new session."""
        session_id = params.get("sessionId")
        cwd = params.get("cwd", ".")
        restore = params.get("restoreFromDisk", True)

        session = await self.session_manager.create_session(
            session_id=session_id, cwd=cwd, restore_from_disk=restore
        )

        return {
            "sessionId": session.session_id,
            "cwd": session.cwd,
            "messageCount": len(session.messages),
            "created": True,
        }

    async def _handle_delete_session(self, params: dict) -> dict:
        """Delete a session."""
        session_id = params.get("sessionId")
        if not session_id:
            raise ValueError("sessionId is required")

        success = await self.session_manager.delete_session(session_id)
        return {"deleted": success}

    async def _handle_list_sessions(self, params: dict) -> dict:
        """List all active sessions."""
        sessions = await self.session_manager.list_sessions()
        return {"sessions": sessions}

    async def _handle_get_session_history(self, params: dict) -> dict:
        """Get session message history."""
        session_id = params.get("sessionId")
        if not session_id:
            raise ValueError("sessionId is required")

        session = await self.session_manager.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        messages = []
        for msg in session.messages:
            messages.append(
                {
                    "type": msg.__class__.__name__,
                    "content": str(getattr(msg, "content", "")),
                }
            )

        return {"sessionId": session_id, "messages": messages}

    async def _handle_shutdown(self, params: dict) -> dict:
        """Shutdown the daemon."""
        asyncio.create_task(self._delayed_stop())
        return {"shuttingDown": True}

    async def _delayed_stop(self):
        """Delayed stop to allow response to be sent."""
        await asyncio.sleep(0.5)
        await self.stop()


def start_daemon():
    """Entry point for daemon mode."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0, help="Port to listen on (0 for auto)")
    parser.add_argument("--skip-config-check", action="store_true", help="Skip configuration check")
    args, _ = parser.parse_known_args()  # Ignore unknown args

    try:
        server = DaemonServer(port=args.port)
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("[Daemon] Interrupted", file=sys.stderr)
    except Exception as e:
        print("[Daemon] Fatal error: {}".format(e), file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
