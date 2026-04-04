#!/usr/bin/env python3
"""Test chat without tools."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from claudecode.query_engine import QueryEngine, QueryEngineConfig
from claudecode.types.message import AssistantMessage

console = Console()

async def test():
    """Test chat."""
    engine = QueryEngine(QueryEngineConfig(
        cwd=".",
        tools=[]  # No tools
    ))
    
    prompt = "编写一个Python函数，计算斐波那契数列"
    console.print(f"[green]Prompt:[/green] {prompt}\n")
    
    full = ""
    async for result in engine.submit_message(prompt):
        msg = result.message
        if isinstance(msg, AssistantMessage) and msg.content:
            if isinstance(msg.content, str):
                if result.is_complete:
                    full = msg.content
                else:
                    full += msg.content
    
    console.print(Markdown(full))

if __name__ == "__main__":
    asyncio.run(test())
