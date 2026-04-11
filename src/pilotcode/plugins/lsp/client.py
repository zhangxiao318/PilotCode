"""LSP JSON-RPC client implementation."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from .types import (
    LspServerConfig,
    LspCompletionItem,
    LspLocation,
    LspHover,
    LspError,
    LspRequestError,
    LspTimeoutError,
)


class LspClient:
    """LSP JSON-RPC client.

    Handles communication with LSP servers over stdio or socket.
    """

    def __init__(self, config: LspServerConfig):
        self.config = config
        self.process: Optional[asyncio.subprocess.Process] = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._initialized = False
        self._capabilities: dict[str, Any] = {}
        self._read_task: Optional[asyncio.Task] = None

    async def start(self) -> bool:
        """Start the LSP server process.

        Returns:
            True if started successfully
        """
        try:
            if self.config.transport == "stdio":
                self.process = await asyncio.create_subprocess_exec(
                    self.config.command,
                    *self.config.args,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env={
                        **dict(self.config.env),
                        **dict(asyncio.get_event_loop()._default_executor),
                    },
                )
                self._reader = self.process.stdout
                self._writer = self.process.stdin
            else:
                # Socket transport
                reader, writer = await asyncio.open_connection("localhost", self.config.port)
                self._reader = reader
                self._writer = writer

            # Start reading responses
            self._read_task = asyncio.create_task(self._read_loop())

            # Send initialize request
            init_result = await self._request(
                "initialize",
                {
                    "processId": None,
                    "rootUri": None,
                    "capabilities": {},
                    "initializationOptions": self.config.initializationOptions,
                },
            )

            self._capabilities = init_result.get("capabilities", {})
            self._initialized = True

            # Send initialized notification
            await self._notify("initialized", {})

            return True

        except Exception as e:
            raise LspError(f"Failed to start LSP server: {e}")

    async def stop(self) -> None:
        """Stop the LSP server."""
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        if self._initialized:
            try:
                await self._notify("shutdown", {})
                await self._notify("exit", {})
            except Exception:
                pass

        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()

        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass

    async def _read_loop(self) -> None:
        """Read responses from the server."""
        try:
            while True:
                message = await self._read_message()
                if message is None:
                    break

                if "id" in message:
                    # Response to a request
                    request_id = message["id"]
                    if request_id in self._pending:
                        future = self._pending.pop(request_id)
                        if "error" in message:
                            error = message["error"]
                            future.set_exception(
                                LspRequestError(
                                    error.get("message", "Unknown error"), error.get("code")
                                )
                            )
                        else:
                            future.set_result(message.get("result"))
                else:
                    # Notification from server
                    await self._handle_notification(message)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            # Fail all pending requests
            for future in self._pending.values():
                future.set_exception(LspError(f"Read loop error: {e}"))
            self._pending.clear()

    async def _read_message(self) -> Optional[dict]:
        """Read a single LSP message."""
        if not self._reader:
            return None

        # Read headers
        headers = {}
        while True:
            line = await self._reader.readline()
            if not line:
                return None
            line = line.decode().strip()
            if not line:
                break
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip()] = value.strip()

        # Read content
        content_length = int(headers.get("Content-Length", 0))
        if content_length == 0:
            return None

        content = await self._reader.read(content_length)
        return json.loads(content.decode())

    async def _send_message(self, message: dict) -> None:
        """Send a message to the server."""
        if not self._writer:
            raise LspError("Not connected")

        content = json.dumps(message)
        header = f"Content-Length: {len(content)}\r\n\r\n"

        self._writer.write(header.encode())
        self._writer.write(content.encode())
        await self._writer.drain()

    async def _request(self, method: str, params: Any) -> Any:
        """Send a request and wait for response."""
        self._request_id += 1
        request_id = self._request_id

        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future

        await self._send_message(message)

        try:
            return await asyncio.wait_for(future, timeout=self.config.requestTimeout / 1000)
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            raise LspTimeoutError(f"Request {method} timed out")

    async def _notify(self, method: str, params: Any) -> None:
        """Send a notification (no response expected)."""
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        await self._send_message(message)

    async def _handle_notification(self, message: dict) -> None:
        """Handle server notifications."""
        method = message.get("method")
        params = message.get("params", {})

        if method == "textDocument/publishDiagnostics":
            # Handle diagnostics
            pass  # Could emit event or store diagnostics

    # LSP Methods

    async def textDocument_didOpen(
        self,
        uri: str,
        language_id: str,
        version: int,
        text: str,
    ) -> None:
        """Notify server that document was opened."""
        await self._notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": language_id,
                    "version": version,
                    "text": text,
                }
            },
        )

    async def textDocument_didChange(
        self,
        uri: str,
        version: int,
        changes: list[dict],
    ) -> None:
        """Notify server that document changed."""
        await self._notify(
            "textDocument/didChange",
            {
                "textDocument": {"uri": uri, "version": version},
                "contentChanges": changes,
            },
        )

    async def textDocument_didClose(self, uri: str) -> None:
        """Notify server that document was closed."""
        await self._notify("textDocument/didClose", {"textDocument": {"uri": uri}})

    async def textDocument_completion(
        self,
        uri: str,
        line: int,
        character: int,
    ) -> list[LspCompletionItem]:
        """Get completions at position."""
        result = await self._request(
            "textDocument/completion",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
            },
        )

        items = []
        if isinstance(result, list):
            items = result
        elif isinstance(result, dict) and "items" in result:
            items = result["items"]

        return [
            LspCompletionItem(
                label=item.get("label", ""),
                kind=item.get("kind", 0),
                detail=item.get("detail"),
                documentation=item.get("documentation"),
                insertText=item.get("insertText"),
            )
            for item in items
        ]

    async def textDocument_hover(
        self,
        uri: str,
        line: int,
        character: int,
    ) -> Optional[LspHover]:
        """Get hover information at position."""
        result = await self._request(
            "textDocument/hover",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
            },
        )

        if not result:
            return None

        contents = result.get("contents", "")
        if isinstance(contents, dict):
            contents = contents.get("value", "")

        return LspHover(
            contents=contents,
            range=result.get("range"),
        )

    async def textDocument_definition(
        self,
        uri: str,
        line: int,
        character: int,
    ) -> list[LspLocation]:
        """Go to definition."""
        result = await self._request(
            "textDocument/definition",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
            },
        )

        if not result:
            return []

        if isinstance(result, dict):
            result = [result]

        return [
            LspLocation(
                uri=loc.get("uri", ""),
                range=loc.get("range", {}),
            )
            for loc in result
        ]

    async def textDocument_formatting(self, uri: str) -> list[dict]:
        """Format document."""
        return (
            await self._request(
                "textDocument/formatting",
                {
                    "textDocument": {"uri": uri},
                    "options": {"tabSize": 4, "insertSpaces": True},
                },
            )
            or []
        )

    @property
    def capabilities(self) -> dict[str, Any]:
        """Server capabilities."""
        return self._capabilities

    @property
    def is_initialized(self) -> bool:
        """Check if client is initialized."""
        return self._initialized
