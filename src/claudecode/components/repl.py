"""REPL (Read-Eval-Print Loop) for ClaudeDecode."""

import asyncio
import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

from ..tools.registry import get_all_tools
from ..commands.base import process_user_input, CommandContext
from ..query_engine import QueryEngine, QueryEngineConfig
from ..state.app_state import AppState, get_default_app_state
from ..state.store import Store, get_store, set_global_store
from ..utils.config import get_global_config


class REPL:
    """Read-Eval-Print Loop for ClaudeDecode."""
    
    def __init__(self):
        self.console = Console()
        self.store = Store(get_default_app_state())
        set_global_store(self.store)
        
        # Initialize state
        config = get_global_config()
        self.store.set_state(lambda s: s)
        
        # Setup prompt session
        self.session = PromptSession(
            message="❯ ",
            style=Style.from_dict({
                'prompt': '#00aa00 bold',
            })
        )
        
        # Create query engine
        tools = get_all_tools()
        self.query_engine = QueryEngine(QueryEngineConfig(
            cwd=self.store.get_state().cwd,
            tools=tools,
            get_app_state=self.store.get_state,
            set_app_state=lambda f: self.store.set_state(f)
        ))
        
        self.running = True
    
    def print_header(self) -> None:
        """Print welcome header."""
        header = """
╔═══════════════════════════════════════════════════════════════╗
║                   ClaudeDecode v0.1.0                          ║
║         Python rewrite of Claude Code                         ║
╚═══════════════════════════════════════════════════════════════╝

Type /help for available commands, or start chatting!
        """
        self.console.print(header, style="cyan")
    
    async def handle_command(self, input_text: str) -> bool:
        """Handle a command or message."""
        context = CommandContext(cwd=self.store.get_state().cwd)
        is_command, result = await process_user_input(input_text, context)
        
        if is_command:
            self.console.print(result)
            return True
        
        return False
    
    async def stream_response(self, prompt: str) -> None:
        """Stream response from model."""
        from ..types.message import AssistantMessage, ToolUseMessage, ToolResultMessage
        
        full_content = ""
        current_tool = None
        has_started = False
        
        async for result in self.query_engine.submit_message(prompt):
            msg = result.message
            
            # Accumulate assistant content
            if isinstance(msg, AssistantMessage) and isinstance(msg.content, str):
                if not has_started:
                    # First content received - clear status
                    has_started = True
                
                if result.is_complete:
                    # Final complete message
                    full_content = msg.content
                else:
                    # Accumulate and print incrementally
                    full_content += msg.content
                    # Print each chunk as it arrives
                    self.console.print(msg.content, end="")
            
            # Show tool use
            if isinstance(msg, ToolUseMessage):
                if has_started:
                    self.console.print()  # New line
                self.console.print(f"[dim]🔧 Using tool: {msg.name}[/dim]")
                current_tool = msg.name
                has_started = False
            
            # Show tool errors
            if isinstance(msg, ToolResultMessage) and msg.is_error:
                self.console.print(f"[red]Tool error: {msg.content}[/red]")
        
        # Final newline and formatted output
        self.console.print()
        if full_content:
            # Print formatted version
            self.console.print(Markdown(full_content))
        elif not current_tool:
            self.console.print("[dim]No response[/dim]")
    
    async def run(self) -> None:
        """Run the REPL."""
        self.print_header()
        
        while self.running:
            try:
                # Get input
                user_input = await self.session.prompt_async()
                user_input = user_input.strip()
                
                if not user_input:
                    continue
                
                # Handle commands
                is_command = await self.handle_command(user_input)
                if is_command:
                    continue
                
                # Show thinking indicator
                with self.console.status("[cyan]Thinking...[/cyan]", spinner="dots"):
                    pass  # Status will be cleared after first chunk
                
                # Send to model
                await self.stream_response(user_input)
                
            except KeyboardInterrupt:
                self.console.print("\n[yellow]Use /quit to exit[/yellow]")
                continue
            except EOFError:
                break
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")
                import traceback
                traceback.print_exc()
                continue
        
        self.console.print("\n[dim]Goodbye! 👋[/dim]")


def run_repl() -> None:
    """Run the REPL."""
    repl = REPL()
    asyncio.run(repl.run())
