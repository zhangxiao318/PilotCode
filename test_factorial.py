#!/usr/bin/env python3
"""Test factorial creation without tools (non-interactive)."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from pilotcode.query_engine import QueryEngine, QueryEngineConfig
from pilotcode.types.message import AssistantMessage

console = Console()

async def test():
    """Test without tools."""
    # No tools - just code generation
    engine = QueryEngine(QueryEngineConfig(
        cwd=".",
        tools=[]
    ))
    
    prompt = "创建一个计算阶乘的Python程序"
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
    console.print("\n[dim]--- 上面是AI生成的代码 ---[/dim]")
    console.print("[dim]在实际使用中，AI会询问是否保存文件[/dim]")

if __name__ == "__main__":
    asyncio.run(test())
