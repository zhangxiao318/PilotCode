"""MCP (Model Context Protocol) client implementation."""

import asyncio
import json
from typing import Any, AsyncIterator
from dataclasses import dataclass
from pydantic import BaseModel


class MCPConfig(BaseModel):
    """MCP server configuration."""
    command: str
    args: list[str] = []
    env: dict[str, str] = {}
    enabled: bool = True


@dataclass
class MCPServerConnection:
    """Connection to an MCP server."""
    name: str
    config: MCPConfig
    process: asyncio.subprocess.Process | None = None
    tools: list[dict[str, Any]] = None
    
    def __post_init__(self):
        if self.tools is None:
            self.tools = []


class MCPClient:
    """Client for MCP (Model Context Protocol) servers."""
    
    def __init__(self):
        self.connections: dict[str, MCPServerConnection] = {}
    
    async def connect(self, name: str, config: MCPConfig) -> MCPServerConnection:
        """Connect to an MCP server."""
        # Start the MCP server process
        env = {**config.env}
        
        process = await asyncio.create_subprocess_exec(
            config.command,
            *config.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        
        connection = MCPServerConnection(
            name=name,
            config=config,
            process=process
        )
        
        self.connections[name] = connection
        
        # Initialize connection
        await self._send_initialize(connection)
        
        return connection
    
    async def _send_initialize(self, connection: MCPServerConnection) -> None:
        """Send initialize request to MCP server."""
        # MCP initialize request
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "claudecode",
                    "version": "0.1.0"
                }
            }
        }
        
        await self._send_message(connection, init_request)
        response = await self._read_message(connection)
        
        # Fetch tools
        await self._fetch_tools(connection)
    
    async def _fetch_tools(self, connection: MCPServerConnection) -> None:
        """Fetch available tools from MCP server."""
        tools_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        
        await self._send_message(connection, tools_request)
        response = await self._read_message(connection)
        
        if response and "result" in response:
            connection.tools = response["result"].get("tools", [])
    
    async def _send_message(self, connection: MCPServerConnection, message: dict) -> None:
        """Send a message to MCP server."""
        if connection.process is None or connection.process.stdin is None:
            raise RuntimeError("MCP server process not running")
        
        data = json.dumps(message) + "\n"
        connection.process.stdin.write(data.encode())
        await connection.process.stdin.drain()
    
    async def _read_message(self, connection: MCPServerConnection) -> dict | None:
        """Read a message from MCP server."""
        if connection.process is None or connection.process.stdout is None:
            return None
        
        try:
            line = await asyncio.wait_for(
                connection.process.stdout.readline(),
                timeout=30.0
            )
            if not line:
                return None
            return json.loads(line.decode().strip())
        except asyncio.TimeoutError:
            return None
        except json.JSONDecodeError:
            return None
    
    async def call_tool(
        self,
        connection_name: str,
        tool_name: str,
        arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Call a tool on an MCP server."""
        connection = self.connections.get(connection_name)
        if not connection:
            raise ValueError(f"MCP server '{connection_name}' not connected")
        
        tool_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        await self._send_message(connection, tool_request)
        response = await self._read_message(connection)
        
        return response.get("result", {}) if response else {}
    
    async def disconnect(self, name: str) -> None:
        """Disconnect from an MCP server."""
        connection = self.connections.get(name)
        if connection and connection.process:
            connection.process.terminate()
            try:
                await asyncio.wait_for(connection.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                connection.process.kill()
            del self.connections[name]
    
    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        for name in list(self.connections.keys()):
            await self.disconnect(name)


# Global MCP client
_mcp_client: MCPClient | None = None


def get_mcp_client() -> MCPClient:
    """Get global MCP client."""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient()
    return _mcp_client
