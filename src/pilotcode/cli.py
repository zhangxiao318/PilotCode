"""CLI entry point for PilotCode."""

import typer
from rich.console import Console
from rich.panel import Panel

from .components.repl import run_repl, run_headless
from .version import __version__

app = typer.Typer(
    name="pilotcode",
    help="PilotCode - AI-powered coding assistant",
    add_completion=False
)
console = Console()


@app.command()
def main(
    version: bool = typer.Option(False, "--version", "-v", help="Show version"),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose mode"),
    model: str = typer.Option("default", "--model", "-m", help="Model to use"),
    cwd: str = typer.Option(".", "--cwd", help="Working directory"),
    auto_allow: bool = typer.Option(False, "--auto-allow", help="Auto-allow all tool executions (for testing)"),
    prompt: str | None = typer.Option(None, "--prompt", "-p", help="Run a single prompt in headless mode"),
    json_mode: bool = typer.Option(False, "--json", help="Output structured JSON in headless mode"),
):
    """PilotCode - Python rewrite of Claude Code."""
    
    if version:
        console.print(f"PilotCode {__version__}")
        raise typer.Exit()
    
    if prompt is not None:
        import asyncio
        asyncio.run(run_headless(prompt, auto_allow=auto_allow, json_mode=json_mode))
        raise typer.Exit()
    
    # Show banner
    banner = f"""
[bold cyan]PilotCode[/bold cyan] [dim]v{__version__}[/dim]

[cyan]An AI-powered coding assistant[/cyan]
[dim]Type /help for commands or start chatting![/dim]
"""
    console.print(Panel(banner, border_style="cyan"))
    
    # Start REPL with options
    run_repl(auto_allow=auto_allow)


@app.command()
def config(
    list: bool = typer.Option(False, "--list", "-l", help="List configuration"),
    set_key: str = typer.Option(None, "--set", help="Set configuration key"),
    set_value: str = typer.Option(None, "--value", help="Configuration value"),
):
    """Manage configuration."""
    from .utils.config import get_config_manager, get_global_config
    
    if list:
        config = get_global_config()
        console.print("[bold]Global Configuration:[/bold]")
        console.print(f"  Theme: {config.theme}")
        console.print(f"  Verbose: {config.verbose}")
        console.print(f"  Auto Compact: {config.auto_compact}")
        console.print(f"  Default Model: {config.default_model}")
        console.print(f"  Base URL: {config.base_url}")
    elif set_key and set_value:
        manager = get_config_manager()
        config = get_global_config()
        
        if hasattr(config, set_key):
            setattr(config, set_key, set_value)
            manager.save_global_config(config)
            console.print(f"[green]Set {set_key} = {set_value}[/green]")
        else:
            console.print(f"[red]Unknown configuration key: {set_key}[/red]")
    else:
        console.print("[yellow]Use --list to view config or --set/--value to modify[/yellow]")


@app.command()
def tools(
    list_tools: bool = typer.Option(True, "--list", "-l", help="List available tools"),
):
    """Manage tools."""
    from .tools.registry import get_all_tools
    
    if list_tools:
        tools = get_all_tools()
        console.print("[bold]Available Tools:[/bold]\n")
        
        for tool in sorted(tools, key=lambda t: t.name):
            desc = tool.description if isinstance(tool.description, str) else tool.name
            aliases = f" [dim](aliases: {', '.join(tool.aliases)})[/dim]" if tool.aliases else ""
            console.print(f"  [cyan]{tool.name}[/cyan]{aliases}")
            console.print(f"     {desc[:80]}...\n" if len(desc) > 80 else f"     {desc}\n")


def cli_main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    cli_main()
