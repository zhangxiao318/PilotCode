"""Web server for PilotCode Web UI."""

import os
import sys
import json
import asyncio
import traceback
import logging
import uuid
from pathlib import Path
from typing import Set, Dict, Any, Optional
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading

# Suppress websockets verbose logging - only show errors, not warnings
logging.getLogger('websockets').setLevel(logging.ERROR)
logging.getLogger('websockets.server').setLevel(logging.ERROR)
logging.getLogger('websockets.protocol').setLevel(logging.ERROR)

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


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
    
    def create_request(self, tool_name: str, tool_input: dict, risk_level: str) -> tuple[str, asyncio.Future]:
        """Create a new permission request. Returns (request_id, future)."""
        request_id = f"perm_{uuid.uuid4().hex[:12]}"
        future = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future
        self._request_info[request_id] = PermissionRequest(request_id, tool_name, tool_input, risk_level)
        return request_id, future
    
    def resolve_request(self, request_id: str, granted: bool, for_session: bool = False) -> tuple[bool, PermissionRequest | None]:
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


class WebSocketManager:
    """Manage WebSocket connections and communication."""
    
    def __init__(self):
        self.clients: Set[Any] = set()
        self.cwd: str = "."
        self.permission_manager = PermissionRequestManager()
        self.current_tasks: Dict[Any, asyncio.Task] = {}  # Track current query tasks per websocket
        
    async def register(self, websocket):
        """Register a new client."""
        self.clients.add(websocket)
        client_info = getattr(websocket, 'remote_address', ('unknown', 0))
        print(f"[WebSocket] Client connected from {client_info}. Total: {len(self.clients)}")
        
    async def unregister(self, websocket):
        """Unregister a client."""
        self.clients.discard(websocket)
        client_info = getattr(websocket, 'remote_address', ('unknown', 0))
        print(f"[WebSocket] Client disconnected from {client_info}. Total: {len(self.clients)}")
        # Cancel all pending permissions for this client
        self.permission_manager.cancel_all()
        
    async def send_to_client(self, websocket, message: dict):
        """Send message to specific client."""
        try:
            await websocket.send(json.dumps(message))
        except Exception as e:
            print(f"[WebSocket] Send error: {e}")
    
    async def handle_message(self, websocket, message: str):
        """Handle incoming WebSocket message."""
        print(f"[WebSocket] Received message: {message[:100]}...")
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")
            print(f"[WebSocket] Message type: {msg_type}")
            
            if msg_type == "query":
                query = data.get("message", "")
                # Cancel any existing task for this websocket
                if websocket in self.current_tasks:
                    old_task = self.current_tasks[websocket]
                    if not old_task.done():
                        old_task.cancel()
                        print(f"[Query] Cancelled previous task for client")
                # Process query in background task to avoid blocking message loop
                task = asyncio.create_task(self.process_query(websocket, query))
                self.current_tasks[websocket] = task
                
            elif msg_type == "interrupt":
                print(f"[WebSocket] Interrupt requested")
                if websocket in self.current_tasks:
                    task = self.current_tasks[websocket]
                    if not task.done():
                        task.cancel()
                        print(f"[Query] Cancelled task due to interrupt")
                    del self.current_tasks[websocket]
                # Cancel any pending permissions
                self.permission_manager.cancel_all()
                await self.send_to_client(websocket, {
                    "type": "interrupted",
                    "message": "Query interrupted by user"
                })
                
            elif msg_type == "permission_response":
                request_id = data.get("request_id", "")
                granted = data.get("granted", False)
                for_session = data.get("for_session", False)
                print(f"[WebSocket] Permission response received: {request_id} = {granted}, for_session={for_session}")
                print(f"[WebSocket] Pending requests before: {list(self.permission_manager._pending.keys())}")
                
                # Resolve the request
                future = self.permission_manager._pending.get(request_id)
                print(f"[WebSocket] Future for {request_id}: {future}, done={future.done() if future else 'None'}")
                
                success, info = self.permission_manager.resolve_request(request_id, granted, for_session)
                print(f"[WebSocket] Resolve result: success={success}, info={info}")
                
                # If granted for session, add to session grants
                if success and granted and for_session and info:
                    from pilotcode.permissions.permission_manager import get_permission_manager
                    perm_mgr = get_permission_manager()
                    perm_mgr.grant_session_permission(info.tool_name, info.tool_input)
                    print(f"[Permission] Granted {info.tool_name} for session")
                
                # Send permission result to client
                await self.send_to_client(websocket, {
                    "type": "permission_result",
                    "request_id": request_id,
                    "granted": granted,
                    "level": "session" if for_session else "once"
                })
            else:
                print(f"[WebSocket] Unknown message type: {msg_type}")
                
        except json.JSONDecodeError as e:
            print(f"[WebSocket] JSON decode error: {e}")
        except Exception as e:
            print(f"[WebSocket] Handler error: {e}")
            print(traceback.format_exc())
    
    async def request_permission_via_websocket(self, websocket, tool_name: str, tool_input: dict, risk_level: str) -> tuple[bool, bool]:
        """Request permission from client via WebSocket. Returns (granted, for_session)."""
        request_id, future = self.permission_manager.create_request(tool_name, tool_input, risk_level)
        
        # Send permission request to client
        try:
            await self.send_to_client(websocket, {
                "type": "permission_request",
                "request_id": request_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "risk_level": risk_level
            })
            print(f"[Permission] Sent request {request_id} for {tool_name}")
        except Exception as e:
            print(f"[Permission] Failed to send request: {e}")
            self.permission_manager.resolve_request(request_id, False)
            return False, False
        
        # Wait for response with timeout
        try:
            granted, for_session = await asyncio.wait_for(future, timeout=300.0)
            print(f"[Permission] Request {request_id} result: granted={granted}, for_session={for_session}")
            return granted, for_session
        except asyncio.TimeoutError:
            print(f"[Permission] Request {request_id} timed out")
            self.permission_manager.resolve_request(request_id, False)
            return False, False
        except Exception as e:
            print(f"[Permission] Request {request_id} error: {e}")
            return False, False
    
    async def process_query(self, websocket, query: str):
        """Process user query and stream results."""
        print(f"[Query] Processing: {query[:50]}...")
        
        stream_id = f"stream_{uuid.uuid4().hex[:8]}"
        
        try:
            from dataclasses import replace
            from pilotcode.query_engine import QueryEngine, QueryEngineConfig
            from pilotcode.tools.registry import get_all_tools
            from pilotcode.state.app_state import get_default_app_state
            from pilotcode.state.store import Store
            from pilotcode.tools.base import ToolUseContext
            from pilotcode.permissions import get_tool_executor
            from pilotcode.permissions.permission_manager import get_permission_manager, PermissionLevel
            from pilotcode.components.repl import classify_task_complexity, run_headless_with_planning
            
            # Send streaming start
            await self.send_to_client(websocket, {
                "type": "streaming_start",
                "stream_id": stream_id,
                "message": query
            })
            
            # Auto-detect task complexity
            mode = await classify_task_complexity(query)
            if mode == "PLAN":
                await self.send_to_client(websocket, {
                    "type": "system",
                    "stream_id": stream_id,
                    "content": "Task classified as complex — enabling planning and verification mode",
                })

                async def send_progress(msg: str):
                    await self.send_to_client(websocket, {
                        "type": "planning_progress",
                        "stream_id": stream_id,
                        "content": msg,
                    })

                def progress_callback(msg: str):
                    asyncio.create_task(send_progress(msg))

                result = await run_headless_with_planning(
                    query,
                    auto_allow=False,
                    max_iterations=25,
                    cwd=self.cwd,
                    progress_callback=progress_callback,
                )
                await self.send_to_client(websocket, {
                    "type": "streaming_complete",
                    "stream_id": stream_id,
                    "content": result.get("response", ""),
                })
                return
            
            # Create store
            store = Store(get_default_app_state())
            store.set_state(lambda s: replace(s, cwd=self.cwd))
            
            # Get tools
            tools = get_all_tools()
            
            # Create query engine
            query_engine = QueryEngine(
                QueryEngineConfig(
                    cwd=self.cwd,
                    tools=tools,
                    get_app_state=store.get_state,
                    set_app_state=lambda f: store.set_state(f),
                )
            )
            
            # Set up permission callback for Web mode
            perm_manager = get_permission_manager()
            
            async def web_permission_callback(permission_request):
                """Callback to request permission via WebSocket."""
                print(f"[Permission] Requesting permission for {permission_request.tool_name}")
                granted, for_session = await self.request_permission_via_websocket(
                    websocket,
                    permission_request.tool_name,
                    permission_request.tool_input,
                    permission_request.risk_level
                )
                if for_session:
                    return PermissionLevel.ALWAYS_ALLOW
                return PermissionLevel.ALLOW if granted else PermissionLevel.DENY
            
            perm_manager.set_permission_callback(web_permission_callback)
            
            # Process query
            full_content = ""
            sent_content_length = 0  # Track how much content has been sent to avoid duplicates
            max_iterations = 25
            iteration = 0
            is_continue_query = False  # Track if this is an internal continuation
            
            while iteration < max_iterations:
                iteration += 1
                print(f"[Query] Iteration {iteration}, query={query[:50]}...")
                
                # Check if task was cancelled
                if asyncio.current_task().cancelled():
                    print("[Query] Task cancelled, breaking loop")
                    break
                
                pending_tools = []
                
                async for result in query_engine.submit_message(query):
                    msg = result.message
                    msg_type = msg.__class__.__name__
                    
                    # Handle thinking content
                    if msg_type == 'ThinkingMessage' or (hasattr(msg, 'thinking') and msg.thinking):
                        thinking_content = getattr(msg, 'thinking', '') or (msg.content if hasattr(msg, 'content') else '')
                        if thinking_content:
                            await self.send_to_client(websocket, {
                                "type": "thinking",
                                "stream_id": stream_id,
                                "content": thinking_content
                            })
                    
                    # Handle streaming content
                    elif hasattr(msg, 'content') and msg.content and isinstance(msg.content, str):
                        if result.is_complete:
                            # Store complete content - will be sent after tools or immediately if no tools
                            full_content = msg.content
                        elif not is_continue_query:
                            # Stream incremental content for user queries only
                            # Skip streaming for continue queries to avoid showing internal prompts
                            content = msg.content
                            if len(content) > sent_content_length:
                                new_content = content[sent_content_length:]
                                await self.send_to_client(websocket, {
                                    "type": "streaming_chunk",
                                    "stream_id": stream_id,
                                    "chunk": new_content
                                })
                                sent_content_length = len(content)
                    
                    # Handle tool use
                    elif msg_type == 'ToolUseMessage':
                        pending_tools.append(msg)
                        await self.send_to_client(websocket, {
                            "type": "tool_call",
                            "stream_id": stream_id,
                            "tool_name": msg.name,
                            "tool_input": msg.input
                        })
                
                # No more tools to execute - this is the final response
                if not pending_tools:
                    # Send final content if any (only the new part)
                    if full_content:
                        if len(full_content) > sent_content_length:
                            new_content = full_content[sent_content_length:]
                            await self.send_to_client(websocket, {
                                "type": "streaming_chunk",
                                "stream_id": stream_id,
                                "chunk": new_content
                            })
                        full_content = ""
                    break
                
                # Check if we've reached max iterations
                if iteration >= max_iterations:
                    print(f"[Query] Reached max iterations ({max_iterations}), forcing end")
                    if full_content:
                        if len(full_content) > sent_content_length:
                            new_content = full_content[sent_content_length:]
                            await self.send_to_client(websocket, {
                                "type": "streaming_chunk",
                                "stream_id": stream_id,
                                "chunk": new_content
                            })
                    # Send a message indicating max iterations reached
                    else:
                        await self.send_to_client(websocket, {
                            "type": "streaming_chunk",
                            "stream_id": stream_id,
                            "chunk": "\n\n[Reached maximum tool call limit. Analysis may be incomplete.]"
                        })
                    break
                
                # Send final content for user-facing queries (not the final response)
                if full_content and not is_continue_query:
                    if len(full_content) > sent_content_length:
                        new_content = full_content[sent_content_length:]
                        await self.send_to_client(websocket, {
                            "type": "streaming_chunk",
                            "stream_id": stream_id,
                            "chunk": new_content
                        })
                        sent_content_length = len(full_content)
                    full_content = ""
                
                print(f"[Query] Executing {len(pending_tools)} tools...")
                
                # Get tool executor
                tool_executor = get_tool_executor()
                
                for tool_msg in pending_tools:
                    context = ToolUseContext(
                        get_app_state=store.get_state,
                        set_app_state=lambda f: store.set_state(f),
                    )
                    
                    exec_result = await tool_executor.execute_tool_by_name(
                        tool_msg.name, tool_msg.input, context
                    )
                    
                    result_content = ""
                    if exec_result.success and exec_result.result:
                        result_content = str(exec_result.result.data) if exec_result.result.data else "Success"
                    else:
                        result_content = exec_result.message
                    
                    query_engine.add_tool_result(
                        tool_msg.tool_use_id, result_content, is_error=not exec_result.success
                    )
                    
                    await self.send_to_client(websocket, {
                        "type": "tool_result",
                        "stream_id": stream_id,
                        "tool_name": tool_msg.name,
                        "result": result_content,
                        "success": exec_result.success
                    })
                
                # Switch to internal continuation query
                query = "Please continue based on the tool results above."
                is_continue_query = True
                # Reset content length tracking for new response
                sent_content_length = 0
            
            # Send streaming end
            await self.send_to_client(websocket, {
                "type": "streaming_end",
                "stream_id": stream_id
            })
            print("[Query] Done")
            
        except asyncio.CancelledError:
            print("[Query] Query was cancelled")
            await self.send_to_client(websocket, {
                "type": "streaming_error",
                "stream_id": stream_id,
                "error": "Query interrupted"
            })
            raise  # Re-raise to propagate cancellation
        except Exception as e:
            print(f"[Query] Error: {e}")
            print(traceback.format_exc())
            await self.send_to_client(websocket, {
                "type": "streaming_error",
                "stream_id": stream_id,
                "error": str(e)
            })
        finally:
            # Clean up task tracking
            if websocket in self.current_tasks:
                del self.current_tasks[websocket]


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
        except:
            pass


class CustomHTTPHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler for serving static files."""
    
    def __init__(self, *args, **kwargs):
        web_dir = Path(__file__).parent / "static"
        super().__init__(*args, directory=str(web_dir), **kwargs)
    
    def log_message(self, format, *args):
        print(f"[HTTP] {args[0]}" if args else "[HTTP] request")
    
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
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
            ) as server:
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
    
    print(f"="*60)
    print(f"PilotCode Web UI Server")
    print(f"="*60)
    print(f"Working directory: {cwd}")
    print(f"Python: {sys.executable}")
    print()
    
    http_thread = threading.Thread(
        target=run_http_server,
        args=(host, port),
        daemon=True
    )
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
