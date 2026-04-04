#!/usr/bin/env python3
"""Test tool execution."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from rich.console import Console
from rich.panel import Panel

from pilotcode.query_engine import QueryEngine, QueryEngineConfig
from pilotcode.tools.registry import get_all_tools
from pilotcode.types.message import AssistantMessage, ToolUseMessage, ToolResultMessage

console = Console()

async def test_tool_execution():
    """Test that tools can be executed."""
    console.print(Panel("[bold cyan]Tool Execution Test[/bold cyan]", border_style="cyan"))
    
    tools = get_all_tools()
    console.print(f"\n[yellow]Available tools: {len(tools)}[/yellow]")
    
    engine = QueryEngine(QueryEngineConfig(
        cwd=".",
        tools=tools
    ))
    
    # Test a prompt that should trigger tool use
    prompt = "List all Python files in the current directory using Glob"
    
    console.print(f"\n[green]Prompt:[/green] {prompt}")
    console.print("\n[cyan]Response:[/cyan]\n")
    
    chunk_count = 0
    tool_calls_seen = []
    
    async for result in engine.submit_message(prompt):
        msg = result.message
        chunk_count += 1
        
        if isinstance(msg, AssistantMessage) and msg.content:
            console.print(msg.content, end="")
        
        if isinstance(msg, ToolUseMessage):
            console.print(f"\n\n[bold yellow]🔧 Tool Called:[/bold yellow] {msg.name}")
            console.print(f"[dim]Input: {msg.input}[/dim]")
            tool_calls_seen.append(msg.name)
        
        if isinstance(msg, ToolResultMessage):
            if msg.is_error:
                console.print(f"\n[red]✗ Tool Error: {msg.content}[/red]")
            else:
                console.print(f"\n[green]✓ Tool Result:[/green]")
                content = str(msg.content)[:200]
                console.print(content + "..." if len(str(msg.content)) > 200 else content)
    
    console.print(f"\n\n[dim]Total chunks: {chunk_count}[/dim]")
    console.print(f"[dim]Tool calls: {tool_calls_seen}[/dim]")

if __name__ == "__main__":
    asyncio.run(test_tool_execution())
