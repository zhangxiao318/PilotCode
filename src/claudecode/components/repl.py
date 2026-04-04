"""REPL for ClaudeDecode - Programming Assistant."""

import asyncio
import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.status import Status
from rich.text import Text
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style

from ..tools.registry import get_all_tools
from ..commands.base import process_user_input, CommandContext
from ..query_engine import QueryEngine, QueryEngineConfig
from ..state.app_state import get_default_app_state
from ..state.store import Store, set_global_store
from ..utils.config import get_global_config
from ..types.message import AssistantMessage, ToolUseMessage, ToolResultMessage


class REPL:
    """Programming Assistant REPL."""
    
    def __init__(self):
        self.console = Console()
        self.store = Store(get_default_app_state())
        set_global_store(self.store)
        
        config = get_global_config()
        self.store.set_state(lambda s: s)
        
        self.session = PromptSession(
            message="❯ ",
            style=Style.from_dict({'prompt': '#00aa00 bold'})
        )
        
        # Initialize with empty tools list to avoid tool call issues
        # Tools can be enabled later when the tool system is stable
        self.query_engine = QueryEngine(QueryEngineConfig(
            cwd=self.store.get_state().cwd,
            tools=[],  # Empty for now - add tools back when stable
            get_app_state=self.store.get_state,
            set_app_state=lambda f: self.store.set_state(f)
        ))
        
        self.running = True
        
    def print_header(self) -> None:
        """Print welcome header."""
        self.console.print(Panel.fit(
            "[bold cyan]ClaudeDecode[/bold cyan] [dim]v0.2.0[/dim]\n"
            "[cyan]AI Programming Assistant[/cyan]\n"
            "[dim]Type /help for commands, or ask me to write code![/dim]",
            border_style="cyan"
        ))
        self.console.print("\n[bold green]💡 Tips:[/bold green]")
        self.console.print("  • 'Write a Python function to...'")
        self.console.print("  • 'Analyze this code for bugs'")
        self.console.print("  • 'Create a web scraper'")
        self.console.print("  • Use /agents for specialized assistants\n")
        
    async def handle_command(self, input_text: str) -> bool:
        """Handle slash commands."""
        context = CommandContext(cwd=self.store.get_state().cwd)
        is_command, result = await process_user_input(input_text, context)
        if is_command:
            self.console.print(result)
            return True
        return False
        
    async def stream_response(self, prompt: str) -> None:
        """Stream response from model."""
        full_content = ""
        tool_info = []
        
        with Status("[cyan]Thinking...[/cyan]", console=self.console, spinner="dots"):
            try:
                async for result in self.query_engine.submit_message(prompt):
                    msg = result.message
                    
                    if isinstance(msg, AssistantMessage) and msg.content:
                        if isinstance(msg.content, str):
                            if result.is_complete:
                                full_content = msg.content
                            else:
                                full_content += msg.content
                    
                    elif isinstance(msg, ToolUseMessage):
                        tool_info.append(f"🔧 {msg.name}")
                        
                    elif isinstance(msg, ToolResultMessage):
                        if msg.is_error:
                            tool_info.append(f"✗ Error")
                        else:
                            tool_info.append(f"✓ Done")
                            
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")
                return
        
        # Display result
        if full_content:
            self.console.print()
            self.console.print(Markdown(full_content))
            
            # Show tool usage summary
            if tool_info:
                self.console.print(f"\n[dim]{' | '.join(set(tool_info))}[/dim]")
        else:
            self.console.print("[dim]No response[/dim]")
            
    async def run(self) -> None:
        """Run the REPL."""
        self.print_header()
        
        while self.running:
            try:
                user_input = await self.session.prompt_async()
                user_input = user_input.strip()
                
                if not user_input:
                    continue
                
                if await self.handle_command(user_input):
                    continue
                
                await self.stream_response(user_input)
                
            except KeyboardInterrupt:
                self.console.print("\n[yellow]Use /quit to exit[/yellow]")
                continue
            except EOFError:
                break
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")
                continue
        
        self.console.print("\n[dim]Goodbye! 👋[/dim]")


def run_repl() -> None:
    """Run the REPL."""
    repl = REPL()
    asyncio.run(repl.run())
