#!/usr/bin/env python3
"""Demo script for ClaudeDecode tools."""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from claudecode.tools.registry import get_all_tools, get_tool_by_name
from claudecode.tools.base import ToolUseContext


console = Console()


async def demo_bash_tool():
    """Demo Bash tool."""
    console.print(Panel("[bold cyan]Bash Tool Demo[/bold cyan]", border_style="cyan"))
    
    from claudecode.tools.bash_tool import BashTool, BashInput
    
    commands = [
        "echo 'Hello from ClaudeDecode!'",
        "pwd",
        "ls -la | head -5",
    ]
    
    for cmd in commands:
        console.print(f"\n[yellow]$ {cmd}[/yellow]")
        
        async def allow_permission(*args, **kwargs):
            return type('obj', (object,), {'behavior': 'allow'})()
        
        result = await BashTool.call(
            BashInput(command=cmd),
            ToolUseContext(),
            allow_permission,
            None,
            lambda x: None
        )
        
        if result.data.stdout:
            console.print(result.data.stdout.strip())
        if result.data.stderr:
            console.print(f"[red]{result.data.stderr}[/red]")


async def demo_file_tools():
    """Demo file tools."""
    console.print(Panel("\n[bold cyan]File Tools Demo[/bold cyan]", border_style="cyan"))
    
    import tempfile
    from claudecode.tools.file_write_tool import FileWriteTool, FileWriteInput
    from claudecode.tools.file_read_tool import FileReadTool, FileReadInput
    from claudecode.tools.glob_tool import GlobTool, GlobInput
    
    async def allow_permission(*args, **kwargs):
        return type('obj', (object,), {'behavior': 'allow'})()
    
    # Write a test file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Line 1: Hello\n")
        f.write("Line 2: World\n")
        f.write("Line 3: From ClaudeDecode\n")
        test_file = f.name
    
    try:
        # Read file
        console.print(f"\n[yellow]Reading {test_file}[/yellow]")
        
        # First read to setup state
        read_result = await FileReadTool.call(
            FileReadInput(file_path=test_file),
            ToolUseContext(),
            allow_permission,
            None,
            lambda x: None
        )
        
        console.print(read_result.data.content)
        
        # Glob for Python files
        console.print("\n[yellow]Globbing for Python files:[/yellow]")
        
        glob_result = await GlobTool.call(
            GlobInput(pattern="*.py", limit=10),
            ToolUseContext(),
            allow_permission,
            None,
            lambda x: None
        )
        
        for filename in glob_result.data.filenames[:5]:
            console.print(f"  - {filename}")
        
        if glob_result.data.truncated:
            console.print(f"  ... and {glob_result.data.total_count - 5} more")
    
    finally:
        os.unlink(test_file)


async def demo_grep_tool():
    """Demo Grep tool."""
    console.print(Panel("\n[bold cyan]Grep Tool Demo[/bold cyan]", border_style="cyan"))
    
    from claudecode.tools.grep_tool import GrepTool, GrepInput, OutputMode
    
    async def allow_permission(*args, **kwargs):
        return type('obj', (object,), {'behavior': 'allow'})()
    
    # Search for class definitions
    console.print("\n[yellow]Searching for 'class' definitions in Python files:[/yellow]")
    
    result = await GrepTool.call(
        GrepInput(
            pattern="^class ",
            path="src/claudecode/tools",
            glob="*.py",
            output_mode=OutputMode.CONTENT,
            head_limit=10
        ),
        ToolUseContext(),
        lambda **kwargs: {"behavior": "allow"},
        None,
        lambda x: None
    )
    
    if result.data.content:
        for line in result.data.content.split('\n')[:5]:
            console.print(f"  {line}")
    
    console.print(f"\n[dim]Found {result.data.num_matches} matches[/dim]")


def list_all_tools():
    """List all registered tools."""
    console.print(Panel("\n[bold cyan]Registered Tools[/bold cyan]", border_style="cyan"))
    
    tools = get_all_tools()
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Name")
    table.add_column("Aliases")
    table.add_column("Read Only")
    table.add_column("Concurrent")
    
    for tool in sorted(tools, key=lambda t: t.name):
        aliases = ", ".join(tool.aliases) if tool.aliases else "-"
        
        # Test with sample input or None
        try:
            sample_input = tool.input_schema(command="echo test") if tool.name == "Bash" else \
                          tool.input_schema(file_path="test.txt") if tool.name in ["FileRead", "FileWrite", "FileEdit"] else \
                          tool.input_schema(pattern="*") if tool.name == "Glob" else \
                          tool.input_schema(pattern="test", path=".") if tool.name == "Grep" else \
                          tool.input_schema(question="test") if tool.name == "AskUser" else \
                          tool.input_schema(todos=[]) if tool.name == "TodoWrite" else \
                          tool.input_schema(query="test") if tool.name == "WebSearch" else \
                          tool.input_schema(url="http://example.com") if tool.name == "WebFetch" else None
            
            is_readonly = tool.is_read_only(sample_input)
            is_concurrent = tool.is_concurrency_safe(sample_input)
        except Exception:
            is_readonly = False
            is_concurrent = False
        
        table.add_row(
            tool.name,
            aliases,
            "✓" if is_readonly else "",
            "✓" if is_concurrent else ""
        )
    
    console.print(table)
    console.print(f"\n[dim]Total: {len(tools)} tools[/dim]")


async def main():
    """Run all demos."""
    console.print(Panel.fit(
        "[bold green]ClaudeDecode Demo[/bold green]\n"
        "[dim]Python rewrite of Claude Code[/dim]",
        border_style="green"
    ))
    
    # List tools
    list_all_tools()
    
    # Run demos
    await demo_bash_tool()
    await demo_file_tools()
    await demo_grep_tool()
    
    console.print(Panel("\n[bold green]Demo Complete![/bold green]", border_style="green"))
    console.print("\nTo start the full application, run:")
    console.print("  [cyan]python -m claudecode[/cyan]")
    console.print("Or:")
    console.print("  [cyan]./run.sh[/cyan]")


if __name__ == "__main__":
    asyncio.run(main())
