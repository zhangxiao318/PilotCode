"""Web command implementation - Launch web UI server."""

import os
import sys
import webbrowser
import asyncio
import socket
from pathlib import Path

from .base import CommandHandler, register_command, CommandContext


def is_port_available(host: str, port: int) -> bool:
    """Check if a port is available."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) != 0


async def web_command(args: list[str], context: CommandContext) -> str:
    """Handle /web command - Launch web UI server and take over the terminal."""
    port = 8080
    host = "127.0.0.1"
    no_browser = False
    
    # Parse arguments
    for i, arg in enumerate(args):
        if arg == "--port" or arg == "-p":
            if i + 1 < len(args):
                try:
                    port = int(args[i + 1])
                except ValueError:
                    return f"[red]Invalid port number: {args[i + 1]}[/red]"
        elif arg == "--host" or arg == "-h":
            if i + 1 < len(args):
                host = args[i + 1]
        elif arg == "--no-browser":
            no_browser = True
        elif arg.startswith("--port="):
            try:
                port = int(arg.split("=")[1])
            except ValueError:
                return f"[red]Invalid port number: {arg}[/red]"
    
    # Check websockets
    try:
        import websockets
    except ImportError as e:
        return f"[red]websockets not installed: {e}[/red]\nRun: {sys.executable} -m pip install websockets"
    
    # Check ports
    ws_port = port + 1
    
    # Find available ports if default is taken
    original_port = port
    max_attempts = 50
    attempts = 0
    while attempts < max_attempts:
        if is_port_available(host, port) and is_port_available(host, port + 1):
            break
        port += 2
        attempts += 1
    
    if attempts >= max_attempts:
        return f"[red]Could not find available ports near {original_port}[/red]"
    
    ws_port = port + 1
    url = f"http://{host}:{port}"
    ws_url = f"ws://{host}:{ws_port}"
    
    # Print startup message
    print(f"""
[green]╔══════════════════════════════════════════════════════════╗[/green]
[green]║          PilotCode Web UI Server                         ║[/green]
[green]╚══════════════════════════════════════════════════════════╝[/green]

  📡 HTTP:      [cyan]{url}[/cyan]
  📡 WebSocket: [cyan]{ws_url}[/cyan]
  📁 Working directory: [dim]{context.cwd}[/dim]

[yellow]Starting server... Press Ctrl+C to stop[/yellow]
""")
    
    # Open browser
    if not no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    
    # Import and run server directly (blocking)
    from ..web.server import run_server_standalone
    
    try:
        # This will block until Ctrl+C
        run_server_standalone(host, port, context.cwd)
    except KeyboardInterrupt:
        print("\n[yellow]Server stopped.[/yellow]")
    except Exception as e:
        print(f"\n[red]Server error: {e}[/red]")
    
    return ""


register_command(
    CommandHandler(
        name="web",
        description="Launch web UI server (blocks until Ctrl+C)",
        handler=web_command,
        aliases=[],
    )
)
