#!/usr/bin/env python3
"""Full demo script for PilotCode with all features."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich import box

from pilotcode.tools.registry import get_all_tools
from pilotcode.commands.base import get_all_commands
from pilotcode.tools.task_tools import TaskCreateInput, TaskCreateTool, TaskListInput, TaskListTool
from pilotcode.tools.base import ToolUseContext

console = Console()


def show_header():
    """Show header."""
    console.print(Panel.fit("""
[bold cyan]PilotCode[/bold cyan] [dim]v0.2.0[/dim]
[cyan]Python rewrite of Claude Code[/cyan]
[dim]Complete Feature Demo[/dim]
""", border_style="cyan"))


def show_tools():
    """Show all tools."""
    tools = get_all_tools()
    
    table = Table(title=f"Available Tools ({len(tools)})", box=box.ROUNDED)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Aliases", style="dim")
    table.add_column("RO", justify="center")
    table.add_column("C", justify="center")
    table.add_column("Description")
    
    for tool in sorted(tools, key=lambda t: t.name):
        aliases = ", ".join(tool.aliases[:2]) if tool.aliases else "-"
        
        # Check properties
        try:
            sample = None
            if tool.name == "Bash":
                from pilotcode.tools.bash_tool import BashInput
                sample = BashInput(command="echo test")
            elif tool.name in ["FileRead", "FileWrite", "FileEdit"]:
                sample = tool.input_schema(file_path="test.txt")
            elif "Task" in tool.name:
                from pilotcode.tools.task_tools import TaskCreateInput
                sample = TaskCreateInput(description="test")
            
            is_ro = tool.is_read_only(sample) if sample else False
            is_c = tool.is_concurrency_safe(sample) if sample else False
        except:
            is_ro = False
            is_c = False
        
        desc = tool.search_hint or tool.name
        
        table.add_row(
            tool.name,
            aliases,
            "✓" if is_ro else "",
            "✓" if is_c else "",
            desc
        )
    
    console.print(table)


def show_commands():
    """Show all commands."""
    commands = get_all_commands()
    
    table = Table(title=f"Available Commands ({len(commands)})", box=box.ROUNDED)
    table.add_column("Command", style="green", no_wrap=True)
    table.add_column("Aliases", style="dim")
    table.add_column("Description")
    
    for cmd in sorted(commands, key=lambda c: c.name):
        aliases = ", ".join(cmd.aliases) if cmd.aliases else "-"
        table.add_row(f"/{cmd.name}", aliases, cmd.description)
    
    console.print(table)


async def demo_tasks():
    """Demo task management."""
    console.print(Panel("\n[bold cyan]Task Management Demo[/bold cyan]", border_style="cyan"))
    
    async def allow_perm(*args, **kwargs):
        return type('obj', (object,), {'behavior': 'allow'})()
    
    # Create tasks
    console.print("\n[yellow]Creating tasks...[/yellow]")
    
    tasks_to_create = [
        ("Background analysis", "echo 'Analyzing code...' && sleep 5"),
        ("Data processing", "echo 'Processing data...' && sleep 3"),
        ("Report generation", "echo 'Generating report...' && sleep 2"),
    ]
    
    created_tasks = []
    for desc, cmd in tasks_to_create:
        result = await TaskCreateTool.call(
            TaskCreateInput(description=desc, command=cmd),
            ToolUseContext(),
            allow_perm,
            None,
            lambda x: None
        )
        created_tasks.append(result.data.task_id)
        console.print(f"  Created: {result.data.task_id} - {desc}")
    
    # List tasks
    console.print("\n[yellow]Listing tasks...[/yellow]")
    list_result = await TaskListTool.call(
        TaskListInput(),
        ToolUseContext(),
        allow_perm,
        None,
        lambda x: None
    )
    
    for task in list_result.data.tasks[:5]:
        console.print(f"  {task['task_id']}: {task['description']} ({task['status']})")
    
    console.print(f"\n[dim]Total tasks: {list_result.data.total}[/dim]")


def show_architecture():
    """Show architecture tree."""
    tree = Tree("[bold]PilotCode Architecture[/bold]")
    
    types = tree.add("📦 Types")
    types.add("Message types")
    types.add("Permission types")
    types.add("Command types")
    
    tools = tree.add("🔧 Tools (16 implemented)")
    tools.add("File: Read/Write/Edit/Glob")
    tools.add("Search: Grep")
    tools.add("Shell: Bash/PowerShell")
    tools.add("Web: Search/Fetch")
    tools.add("Agent: Agent spawning")
    tools.add("Task: Create/Get/List/Stop/Update")
    tools.add("Other: Todo, AskUser, Config, LSP, Notebook")
    
    cmds = tree.add("⌨️  Commands (9 implemented)")
    cmds.add("System: help, clear, quit")
    cmds.add("Config: config")
    cmds.add("Session: session")
    cmds.add("Monitoring: cost, tasks")
    cmds.add("Management: agents, tools")
    
    state = tree.add("📊 State")
    state.add("AppState")
    state.add("Store (Zustand-like)")
    state.add("Settings")
    
    services = tree.add("🌐 Services")
    services.add("Model Client (OpenAI-compatible)")
    services.add("MCP Client")
    
    console.print(tree)


async def main():
    """Run full demo."""
    show_header()
    
    console.print("\n[bold]1. Architecture Overview[/bold]")
    show_architecture()
    
    console.print("\n[bold]2. Available Tools[/bold]")
    show_tools()
    
    console.print("\n[bold]3. Available Commands[/bold]")
    show_commands()
    
    await demo_tasks()
    
    # Summary
    console.print(Panel.fit("""
[bold green]Summary[/bold green]

[cyan]Implemented:[/cyan]
• 16 Tools (40+ planned)
• 9 Commands (80+ planned)  
• Core architecture
• Query engine
• State management
• Basic TUI

[cyan]Next Steps:[/cyan]
• Implement remaining tools
• Add full command set
• Enhance TUI with Textual
• Add MCP full support
• Add Git integration

[dim]Run with: python3 -m pilotcode[/dim]
""", border_style="green"))


if __name__ == "__main__":
    asyncio.run(main())
