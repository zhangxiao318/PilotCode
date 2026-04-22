"""MCP TUI Test Client - Universal client for TUI automation MCP servers.

Supports:
- mcp-tui-test (Python): https://github.com/GeorgePearse/mcp-tui-test
- mcp-terminator (Go): https://github.com/davidroman0O/mcp-terminator
"""

import asyncio
import json
import subprocess
import time
from dataclasses import dataclass
from typing import Optional, Dict, List
from pathlib import Path


@dataclass
class TUISession:
    """Represents an active TUI testing session."""

    session_id: str
    command: str
    mode: str  # "stream" or "buffer"
    created_at: float


class MCPClientError(Exception):
    """Base exception for MCP client errors."""

    pass


class TUITestClient:
    """Universal MCP TUI Test Client.

    This client can work with different MCP TUI testing servers:
    - mcp-tui-test: Python implementation with pexpect/pyte
    - mcp-terminator: Go implementation with Terminal State Tree

    Example:
        async with TUITestClient() as client:
            session = await client.launch_tui(
                command="python -m pilotcode --auto-allow",
                session_id="pilotcode_test",
                mode="buffer",
                dimensions="120x40"
            )

            # Wait for welcome screen
            await client.expect_text("PilotCode", session_id="pilotcode_test")

            # Send query
            await client.send_keys("现在几点了\n", session_id="pilotcode_test")

            # Wait for response
            await client.expect_text("时间", timeout=15, session_id="pilotcode_test")

            # Get screen content
            screen = await client.capture_screen(session_id="pilotcode_test")
            print(screen.content)
    """

    def __init__(
        self,
        server_command: Optional[str] = None,
        server_type: str = "auto",  # "auto", "tui-test", "terminator"
    ):
        """Initialize TUI Test Client.

        Args:
            server_command: Command to launch MCP server (auto-detected if None)
            server_type: Type of MCP server ("tui-test", "terminator", or "auto")
        """
        self.server_command = server_command
        self.server_type = server_type
        self.process: Optional[subprocess.Process] = None
        self.sessions: Dict[str, TUISession] = {}
        self._request_id = 0
        self._pending_responses: Dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None

    def _detect_server(self) -> tuple[str, str]:
        """Auto-detect available MCP TUI server.

        Returns:
            Tuple of (server_command, server_type)
        """
        # Try mcp-terminator first (preferred - more modern)
        result = subprocess.run(["which", "mcp-terminator"], capture_output=True, text=True)
        if result.returncode == 0:
            return ("mcp-terminator", "terminator")

        # Try mcp-tui-test
        result = subprocess.run(["which", "mcp-tui-test"], capture_output=True, text=True)
        if result.returncode == 0:
            return ("mcp-tui-test", "tui-test")

        # Check if server.py exists in common locations
        possible_paths = [
            Path.home() / ".local" / "bin" / "mcp-tui-test",
            Path.home() / "mcp-tui-test" / "server.py",
            Path("/usr/local/bin/mcp-tui-test"),
        ]
        for path in possible_paths:
            if path.exists():
                return (str(path), "tui-test")

        raise MCPClientError(
            "No MCP TUI server found. Please install:\n"
            "  - mcp-terminator: go install github.com/davidroman0O/mcp-terminator@latest\n"
            "  - mcp-tui-test: pip install mcp-tui-test"
        )

    async def __aenter__(self):
        """Start MCP server and initialize connection."""
        if not self.server_command:
            self.server_command, detected_type = self._detect_server()
            if self.server_type == "auto":
                self.server_type = detected_type

        # Start MCP server process
        self.process = await asyncio.create_subprocess_exec(
            *self.server_command.split(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Start response reader
        self._reader_task = asyncio.create_task(self._read_responses())

        # Initialize MCP connection
        await self._initialize()

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup: close all sessions and terminate server."""
        # Close all sessions
        for session_id in list(self.sessions.keys()):
            try:
                await self.close_session(session_id)
            except Exception:
                pass

        # Stop reader
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        # Terminate server
        if self.process:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.process.kill()

    async def _initialize(self):
        """Initialize MCP connection."""
        init_request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pilotcode-tui-client", "version": "1.0.0"},
            },
        }

        response = await self._send_request(init_request)
        if "error" in response:
            raise MCPClientError(f"Initialization failed: {response['error']}")

        # Send initialized notification
        await self._send_notification("initialized", {})

    def _next_id(self) -> int:
        """Get next request ID."""
        self._request_id += 1
        return self._request_id

    async def _send_request(self, request: dict) -> dict:
        """Send JSON-RPC request and wait for response."""
        request_id = request["id"]
        future = asyncio.Future()
        self._pending_responses[request_id] = future

        # Send request
        data = json.dumps(request) + "\n"
        self.process.stdin.write(data.encode())
        await self.process.stdin.drain()

        # Wait for response
        try:
            return await asyncio.wait_for(future, timeout=30)
        except asyncio.TimeoutError:
            del self._pending_responses[request_id]
            raise MCPClientError(f"Request {request_id} timed out")

    async def _send_notification(self, method: str, params: dict):
        """Send JSON-RPC notification (no response expected)."""
        notification = {"jsonrpc": "2.0", "method": method, "params": params}
        data = json.dumps(notification) + "\n"
        self.process.stdin.write(data.encode())
        await self.process.stdin.drain()

    async def _read_responses(self):
        """Background task to read responses from MCP server."""
        while True:
            try:
                line = await self.process.stdout.readline()
                if not line:
                    break

                response = json.loads(line.decode())
                request_id = response.get("id")

                if request_id and request_id in self._pending_responses:
                    future = self._pending_responses.pop(request_id)
                    future.set_result(response)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error reading response: {e}")

    async def _call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call an MCP tool."""
        # Map generic tool names to server-specific names
        tool_name = self._map_tool_name(tool_name)

        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }

        response = await self._send_request(request)

        if "error" in response:
            raise MCPClientError(f"Tool call failed: {response['error']}")

        result = response.get("result", {})
        if result.get("isError"):
            content = result.get("content", [{}])[0]
            raise MCPClientError(f"Tool error: {content.get('text', 'Unknown error')}")

        return result

    def _map_tool_name(self, name: str) -> str:
        """Map generic tool names to server-specific names."""
        mappings = {
            "terminator": {
                "launch_tui": "terminal_session_create",
                "close_session": "terminal_session_close",
                "send_keys": "terminal_type",
                "send_ctrl": "terminal_press_key",
                "capture_screen": "terminal_snapshot",
                "expect_text": "terminal_wait_for",
                "list_sessions": "terminal_session_list",
            },
            "tui-test": {
                "launch_tui": "launch_tui",
                "close_session": "close_session",
                "send_keys": "send_keys",
                "send_ctrl": "send_ctrl",
                "capture_screen": "capture_screen",
                "expect_text": "expect_text",
                "list_sessions": "list_sessions",
            },
        }

        return mappings.get(self.server_type, {}).get(name, name)

    # === Public API ===

    async def launch_tui(
        self,
        command: str,
        session_id: str = "default",
        mode: str = "buffer",
        dimensions: str = "120x40",
        timeout: int = 30,
        cwd: Optional[str] = None,
    ) -> TUISession:
        """Launch a TUI application for testing.

        Args:
            command: Command to launch the TUI application
            session_id: Unique identifier for this session
            mode: "stream" for CLI tools, "buffer" for full TUIs
            dimensions: Terminal dimensions as "WIDTHxHEIGHT"
            timeout: Command timeout in seconds
            cwd: Working directory for the command

        Returns:
            TUISession object
        """
        arguments = {
            "command": command,
            "session_id": session_id,
            "timeout": timeout,
        }

        if self.server_type == "tui-test":
            arguments["mode"] = mode
            arguments["dimensions"] = dimensions
        elif self.server_type == "terminator":
            # Parse dimensions for terminator
            width, height = dimensions.split("x")
            arguments["rows"] = int(height)
            arguments["cols"] = int(width)
            if cwd:
                arguments["cwd"] = cwd

        await self._call_tool("launch_tui", arguments)

        session = TUISession(
            session_id=session_id, command=command, mode=mode, created_at=time.time()
        )
        self.sessions[session_id] = session

        # Small delay for TUI to initialize
        await asyncio.sleep(0.5)

        return session

    async def send_keys(self, keys: str, session_id: str = "default", delay: float = 0.1):
        """Send keyboard input to TUI.

        Args:
            keys: Keys to send. Use \\n for Enter, \\t for Tab
            session_id: Session identifier
            delay: Delay after sending keys (seconds)
        """
        if self.server_type == "terminator":
            # Terminator uses terminal_type for text input
            await self._call_tool(
                "send_keys", {"session_id": session_id, "text": keys, "delay_ms": int(delay * 1000)}
            )
        else:
            await self._call_tool(
                "send_keys", {"keys": keys, "session_id": session_id, "delay": delay}
            )

        # Wait for keys to be processed
        await asyncio.sleep(delay)

    async def send_ctrl(self, key: str, session_id: str = "default"):
        """Send Ctrl+Key combination.

        Args:
            key: Key to combine with Ctrl (e.g., 'c', 'd', 'l')
            session_id: Session identifier
        """
        if self.server_type == "terminator":
            await self._call_tool("send_ctrl", {"session_id": session_id, "key": f"Ctrl+{key}"})
        else:
            await self._call_tool("send_ctrl", {"key": key, "session_id": session_id})

    async def capture_screen(
        self, session_id: str = "default", include_ansi: bool = False
    ) -> "ScreenCapture":
        """Capture current screen output.

        Args:
            session_id: Session identifier
            include_ansi: Whether to include ANSI escape codes

        Returns:
            ScreenCapture object with content and metadata
        """
        if self.server_type == "terminator":
            result = await self._call_tool(
                "capture_screen", {"session_id": session_id, "idle_threshold_ms": 100}
            )
            # Parse Terminal State Tree response
            content = result.get("content", [{}])[0].get("text", "")
            # Extract raw text from TST
            try:
                tst = json.loads(content)
                return ScreenCapture(
                    raw_text=tst.get("raw_text", ""),
                    elements=tst.get("elements", []),
                    cursor=tst.get("cursor", {}),
                    dimensions=tst.get("dimensions", {}),
                )
            except json.JSONDecodeError:
                return ScreenCapture(raw_text=content)
        else:
            result = await self._call_tool(
                "capture_screen", {"session_id": session_id, "include_ansi": include_ansi}
            )
            content = result.get("content", [{}])[0].get("text", "")
            return ScreenCapture(raw_text=content)

    async def expect_text(
        self, pattern: str, session_id: str = "default", timeout: float = 10
    ) -> bool:
        """Wait for specific text to appear on screen.

        Args:
            pattern: Text or regex pattern to wait for
            session_id: Session identifier
            timeout: Maximum time to wait (seconds)

        Returns:
            True if text found, raises TimeoutError otherwise
        """
        if self.server_type == "terminator":
            await self._call_tool(
                "expect_text",
                {"session_id": session_id, "text": pattern, "timeout_ms": int(timeout * 1000)},
            )
        else:
            await self._call_tool(
                "expect_text", {"pattern": pattern, "session_id": session_id, "timeout": timeout}
            )
        return True

    async def assert_contains(self, text: str, session_id: str = "default") -> bool:
        """Assert that screen contains specific text.

        Args:
            text: Text to search for
            session_id: Session identifier

        Returns:
            True if found, False otherwise
        """
        screen = await self.capture_screen(session_id)
        return text in screen.raw_text

    async def close_session(self, session_id: str = "default"):
        """Close a TUI testing session.

        Args:
            session_id: Session identifier
        """
        await self._call_tool("close_session", {"session_id": session_id})

        if session_id in self.sessions:
            del self.sessions[session_id]

    async def list_sessions(self) -> List[str]:
        """List all active sessions.

        Returns:
            List of session IDs
        """
        result = await self._call_tool("list_sessions", {})
        content = result.get("content", [{}])[0].get("text", "")
        # Parse session list from response
        return [s.strip() for s in content.split("\n") if s.strip()]


@dataclass
class ScreenCapture:
    """Represents a captured screen."""

    raw_text: str
    elements: Optional[List[dict]] = None
    cursor: Optional[dict] = None
    dimensions: Optional[dict] = None

    @property
    def content(self) -> str:
        """Get plain text content (without ANSI codes)."""
        return self.raw_text

    def find_element(self, element_type: str, label: Optional[str] = None) -> Optional[dict]:
        """Find UI element by type and optional label."""
        if not self.elements:
            return None

        for elem in self.elements:
            if elem.get("type") == element_type:
                if label is None or label in elem.get("label", ""):
                    return elem
        return None

    def __str__(self) -> str:
        return self.raw_text
