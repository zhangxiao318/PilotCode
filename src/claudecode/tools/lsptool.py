"""LSP Tool for Language Server Protocol integration."""

import json
import subprocess
from typing import Any
from dataclasses import dataclass
from pydantic import BaseModel, Field

from .base import Tool, ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class LSPInput(BaseModel):
    """Input for LSP tool."""
    command: str = Field(description="LSP command: 'definition', 'references', 'hover', 'completion', 'diagnostics'")
    file_path: str = Field(description="Path to the file")
    line: int = Field(description="Line number (0-indexed)")
    character: int = Field(description="Character position (0-indexed)")
    language: str = Field(default="python", description="Programming language")


class LSPOutput(BaseModel):
    """Output from LSP tool."""
    result: list[dict[str, Any]] | dict[str, Any] | None
    command: str
    file_path: str


# LSP server configurations
LSP_SERVERS = {
    "python": {
        "command": "pylsp",
        "args": [],
    },
    "typescript": {
        "command": "typescript-language-server",
        "args": ["--stdio"],
    },
    "javascript": {
        "command": "typescript-language-server",
        "args": ["--stdio"],
    },
    "rust": {
        "command": "rust-analyzer",
        "args": [],
    },
    "go": {
        "command": "gopls",
        "args": [],
    },
}


class LSPClient:
    """Simple LSP client."""
    
    def __init__(self, language: str):
        self.language = language
        self.process = None
        self.request_id = 0
    
    async def start(self) -> bool:
        """Start LSP server."""
        config = LSP_SERVERS.get(self.language)
        if not config:
            return False
        
        try:
            self.process = await asyncio.create_subprocess_exec(
                config["command"],
                *config["args"],
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Send initialize request
            await self._send_request("initialize", {
                "processId": None,
                "rootUri": None,
                "capabilities": {}
            })
            
            return True
        except Exception:
            return False
    
    async def _send_request(self, method: str, params: dict) -> dict:
        """Send LSP request."""
        if not self.process:
            return {}
        
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params
        }
        
        data = json.dumps(request)
        header = f"Content-Length: {len(data)}\r\n\r\n"
        
        self.process.stdin.write((header + data).encode())
        await self.process.stdin.drain()
        
        # Read response
        return await self._read_response()
    
    async def _read_response(self) -> dict:
        """Read LSP response."""
        # Simplified - real implementation needs proper header parsing
        return {}
    
    async def goto_definition(self, file_path: str, line: int, character: int) -> list[dict]:
        """Go to definition."""
        result = await self._send_request("textDocument/definition", {
            "textDocument": {"uri": f"file://{file_path}"},
            "position": {"line": line, "character": character}
        })
        return result.get("result", [])
    
    async def find_references(self, file_path: str, line: int, character: int) -> list[dict]:
        """Find references."""
        result = await self._send_request("textDocument/references", {
            "textDocument": {"uri": f"file://{file_path}"},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": True}
        })
        return result.get("result", [])
    
    async def hover(self, file_path: str, line: int, character: int) -> dict:
        """Get hover info."""
        result = await self._send_request("textDocument/hover", {
            "textDocument": {"uri": f"file://{file_path}"},
            "position": {"line": line, "character": character}
        })
        return result.get("result", {})
    
    async def completion(self, file_path: str, line: int, character: int) -> list[dict]:
        """Get completions."""
        result = await self._send_request("textDocument/completion", {
            "textDocument": {"uri": f"file://{file_path}"},
            "position": {"line": line, "character": character}
        })
        return result.get("result", [])
    
    async def stop(self) -> None:
        """Stop LSP server."""
        if self.process:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.process.kill()


async def lsp_call(
    input_data: LSPInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any
) -> ToolResult[LSPOutput]:
    """Execute LSP command."""
    import asyncio
    
    client = LSPClient(input_data.language)
    
    try:
        if not await client.start():
            return ToolResult(
                data=LSPOutput(result=None, command=input_data.command, file_path=input_data.file_path),
                error=f"Failed to start LSP server for {input_data.language}"
            )
        
        if input_data.command == "definition":
            result = await client.goto_definition(input_data.file_path, input_data.line, input_data.character)
        elif input_data.command == "references":
            result = await client.find_references(input_data.file_path, input_data.line, input_data.character)
        elif input_data.command == "hover":
            result = await client.hover(input_data.file_path, input_data.line, input_data.character)
        elif input_data.command == "completion":
            result = await client.completion(input_data.file_path, input_data.line, input_data.character)
        else:
            return ToolResult(
                data=LSPOutput(result=None, command=input_data.command, file_path=input_data.file_path),
                error=f"Unknown command: {input_data.command}"
            )
        
        return ToolResult(data=LSPOutput(
            result=result,
            command=input_data.command,
            file_path=input_data.file_path
        ))
    except Exception as e:
        return ToolResult(
            data=LSPOutput(result=None, command=input_data.command, file_path=input_data.file_path),
            error=str(e)
        )
    finally:
        await client.stop()


async def lsp_description(input_data: LSPInput, options: dict[str, Any]) -> str:
    """Get description for LSP tool."""
    return f"LSP {input_data.command} at {input_data.file_path}:{input_data.line}:{input_data.character}"


# Create the LSP tool
LSPTool = build_tool(
    name="LSP",
    description=lsp_description,
    input_schema=LSPInput,
    output_schema=LSPOutput,
    call=lsp_call,
    aliases=["lsp", "language-server"],
    search_hint="Use Language Server Protocol for code navigation",
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
)

register_tool(LSPTool)
