#!/usr/bin/env python3
"""Simple test without tool recursion."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from rich.console import Console
from rich.panel import Panel

from claudecode.query_engine import QueryEngine, QueryEngineConfig
from claudecode.tools.registry import get_all_tools
from claudecode.types.message import AssistantMessage

console = Console()

async def test_simple():
    """Test simple conversation."""
    console.print(Panel("[bold cyan]Simple Test[/bold cyan]", border_style="cyan"))
    
    tools = get_all_tools()
    
    engine = QueryEngine(QueryEngineConfig(
        cwd=".",
        tools=[]  # No tools for simple test
    ))
    
    prompt = "Write a simple Python hello world program"
    
    console.print(f"\n[green]Prompt:[/green] {prompt}")
    console.print("\n[cyan]Response:[/cyan]\n")
    
    full_content = ""
    
    async for result in engine.submit_message(prompt):
        msg = result.message
        
        if isinstance(msg, AssistantMessage) and msg.content:
            if result.is_complete:
                full_content = msg.content
            else:
                console.print(msg.content, end="")
                full_content += msg.content
    
    console.print("\n")
    console.print(Panel(full_content, title="Complete Response", border_style="green"))

if __name__ == "__main__":
    asyncio.run(test_simple())
