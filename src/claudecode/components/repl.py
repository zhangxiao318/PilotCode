"""REPL for ClaudeDecode - Programming Assistant Mode."""

import asyncio
import sys
import os
from typing import Any
from dataclasses import dataclass

from rich.console import Console, Group
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text
from rich.table import Table
from rich.tree import Tree
from rich.align import Align
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style

from ..tools.registry import get_all_tools
from ..commands.base import process_user_input, CommandContext
from ..query_engine import QueryEngine, QueryEngineConfig
from ..state.app_state import AppState, get_default_app_state
from ..state.store import Store, set_global_store
from ..utils.config import get_global_config


@dataclass
class StreamBuffer:
    """Buffer for streaming content."""
    content: str = ""
    tool_calls: list[dict] = None
    
    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []


class CodeBlock:
    """Represents a code block in the output."""
    def __init__(self, language: str = "", content: str = ""):
        self.language = language
        self.content = content
        self.executed = False
        self.output = ""


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
            style=Style.from_dict({
                'prompt': '#00aa00 bold',
            })
        )
        
        tools = get_all_tools()
        self.query_engine = QueryEngine(QueryEngineConfig(
            cwd=self.store.get_state().cwd,
            tools=tools,
            get_app_state=self.store.get_state,
            set_app_state=lambda f: self.store.set_state(f)
        ))
        
        self.running = True
        self.show_tool_calls = True
        self.auto_execute = False  # 是否自动执行代码
        
    def print_header(self) -> None:
        """Print welcome header."""
        header = Panel.fit(
            "[bold cyan]ClaudeDecode[/bold cyan] [dim]v0.2.0[/dim]\n"
            "[cyan]AI Programming Assistant[/cyan]\n"
            "[dim]Type /help for commands, or ask me to write code![/dim]",
            border_style="cyan"
        )
        self.console.print(header)
        
    def format_code_block(self, code: str, language: str = "python") -> Panel:
        """Format code block with syntax highlighting."""
        syntax = Syntax(
            code,
            language,
            theme="monokai",
            line_numbers=True,
            word_wrap=True
        )
        return Panel(
            syntax,
            title=f"[bold]{language.upper()}[/bold]",
            border_style="green",
            padding=(1, 2)
        )
        
    def format_tool_call(self, tool_name: str, tool_input: dict) -> Panel:
        """Format tool call display."""
        content = Text()
        content.append(f"🔧 {tool_name}\n", style="bold yellow")
        
        # Format tool input
        import json
        for key, value in tool_input.items():
            content.append(f"  {key}: ", style="dim")
            if isinstance(value, str) and len(value) > 100:
                content.append(f"{value[:100]}...\n", style="cyan")
            else:
                content.append(f"{value}\n", style="cyan")
        
        return Panel(content, border_style="yellow", padding=(0, 1))
        
    def format_tool_result(self, result: Any, is_error: bool = False) -> Panel:
        """Format tool result display."""
        if is_error:
            return Panel(
                f"[red]✗ Error: {result}[/red]",
                border_style="red",
                padding=(0, 1)
            )
        
        content = str(result)
        if len(content) > 500:
            content = content[:500] + "\n... [truncated]"
            
        return Panel(
            Markdown(content),
            title="[green]✓ Result[/green]",
            border_style="green",
            padding=(0, 1)
        )
        
    def extract_code_blocks(self, text: str) -> list:
        """Extract code blocks from markdown text."""
        import re
        blocks = []
        
        # Find code blocks
        pattern = r'```(\w+)?\n(.*?)```'
        matches = re.finditer(pattern, text, re.DOTALL)
        
        for match in matches:
            language = match.group(1) or "text"
            code = match.group(2).strip()
            blocks.append(CodeBlock(language, code))
            
        return blocks
        
    async def handle_command(self, input_text: str) -> bool:
        """Handle slash commands."""
        context = CommandContext(cwd=self.store.get_state().cwd)
        is_command, result = await process_user_input(input_text, context)
        
        if is_command:
            if isinstance(result, str):
                self.console.print(result)
            return True
        return False
        
    async def stream_response(self, prompt: str) -> None:
        """Stream response with tool execution visualization."""
        from ..types.message import AssistantMessage, ToolUseMessage, ToolResultMessage
        
        buffer = StreamBuffer()
        current_panel = None
        
        # Create live display
        with Live(
            Panel(Spinner("dots", text="Thinking..."), border_style="blue"),
            console=self.console,
            refresh_per_second=10
        ) as live:
            
            async for result in self.query_engine.submit_message(prompt):
                msg = result.message
                
                # Handle assistant text content
                if isinstance(msg, AssistantMessage) and msg.content:
                    if isinstance(msg.content, str):
                        buffer.content += msg.content
                        
                        # Update live display with current content
                        if len(buffer.content) < 2000:
                            live.update(Panel(
                                Markdown(buffer.content + "▌"),
                                border_style="blue",
                                title="[cyan]Assistant[/cyan]"
                            ))
                        
                # Handle tool use
                if isinstance(msg, ToolUseMessage):
                    # Show tool call
                    tool_panel = self.format_tool_call(msg.name, msg.input)
                    live.update(tool_panel)
                    buffer.tool_calls.append({
                        "name": msg.name,
                        "input": msg.input
                    })
                    
                # Handle tool result
                if isinstance(msg, ToolResultMessage):
                    result_panel = self.format_tool_result(
                        msg.content, 
                        msg.is_error
                    )
                    live.update(result_panel)
                    
                    # Brief pause to show result
                    await asyncio.sleep(0.5)
            
            # Final display
            live.stop()
            
        # Print final formatted response
        if buffer.content:
            self.console.print()
            self.console.print(Panel(
                Markdown(buffer.content),
                border_style="green",
                title="[bold green]Response[/bold green]"
            ))
            
            # Extract and offer to execute code blocks
            code_blocks = self.extract_code_blocks(buffer.content)
            if code_blocks:
                self.console.print()
                self.console.print("[bold cyan]📦 Found code blocks:[/bold cyan]")
                
                for i, block in enumerate(code_blocks, 1):
                    self.console.print(f"\n[i] Code Block {i} ({block.language}):")
                    self.console.print(self.format_code_block(
                        block.content, 
                        block.language
                    ))
                    
                    # Offer to save or execute
                    if block.language in ["python", "bash", "shell"]:
                        self.console.print(
                            f"[dim]Tip: Use /edit or Bash tool to save/execute this code[/dim]"
                        )
                        
        elif not buffer.tool_calls:
            self.console.print("[dim]No response received[/dim]")
            
    async def interactive_mode(self) -> None:
        """Interactive programming mode with enhanced features."""
        self.console.print("\n[bold green]💡 Programming Mode Tips:[/bold green]")
        self.console.print("  • Ask me to write code: 'Write a Python script to...'")
        self.console.print("  • Request analysis: 'Analyze this code for bugs'")
        self.console.print("  • Run tests: 'Test this function'")
        self.console.print("  • Use /agents to spawn specialized coding assistants")
        self.console.print("  • Use /workflow for multi-step coding tasks\n")
        
    async def run(self) -> None:
        """Run the REPL."""
        self.print_header()
        await self.interactive_mode()
        
        while self.running:
            try:
                user_input = await self.session.prompt_async()
                user_input = user_input.strip()
                
                if not user_input:
                    continue
                
                # Handle commands
                if await self.handle_command(user_input):
                    continue
                
                # Process with streaming
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
