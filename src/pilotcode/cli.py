"""CLI entry point for PilotCode."""

import typer
from rich.console import Console
from rich.panel import Panel
from rich import box

from .components.repl import run_repl, run_headless
from .version import __version__
from .utils.config import is_configured, get_config_manager
from .utils.configure import run_configure_wizard, format_model_list

app = typer.Typer(
    name="pilotcode",
    help="PilotCode - AI-powered coding assistant",
    add_completion=False
)
console = Console()


def check_configuration() -> bool:
    """Check if application is configured, prompt user if not.
    
    Returns:
        True if configured or user configured it, False otherwise.
    """
    if is_configured():
        return True
    
    # Not configured - show setup message
    console.print(Panel.fit(
        "[bold yellow]⚠️  PilotCode is not configured yet[/bold yellow]\n\n"
        "You need to configure a language model to use PilotCode.",
        border_style="yellow"
    ))
    
    console.print("\n[bold]Options:[/bold]")
    console.print("  [cyan]1.[/cyan] Run interactive configuration wizard")
    console.print("  [cyan]2.[/cyan] Set environment variables")
    console.print("  [cyan]3.[/cyan] View available models")
    console.print("  [cyan]4.[/cyan] Exit\n")
    
    choice = typer.prompt("Select option", type=int, default=1)
    
    if choice == 1:
        return run_configure_wizard()
    elif choice == 2:
        console.print("\n[bold]Environment Variables:[/bold]")
        console.print("You can set these environment variables:")
        console.print("  [green]PILOTCODE_API_KEY[/green]      - Your API key")
        console.print("  [green]PILOTCODE_MODEL[/green]        - Model name (e.g., deepseek, openai)")
        console.print("  [green]PILOTCODE_BASE_URL[/green]     - Custom base URL (optional)")
        console.print("\nOr provider-specific variables:")
        console.print("  [green]OPENAI_API_KEY[/green], [green]ANTHROPIC_API_KEY[/green], [green]DEEPSEEK_API_KEY[/green]")
        console.print("  [green]DASHSCOPE_API_KEY[/green], [green]ZHIPU_API_KEY[/green], [green]MOONSHOT_API_KEY[/green], etc.")
        
        # Ask if they want to run wizard now
        if typer.confirm("\nRun configuration wizard now?", default=True):
            return run_configure_wizard()
        return False
    elif choice == 3:
        console.print(format_model_list())
        console.print("\n[dim]Run with --configure to set up your model[/dim]")
        return False
    else:
        return False


@app.command()
def main(
    version: bool = typer.Option(False, "--version", "-v", help="Show version"),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose mode"),
    model: str = typer.Option("default", "--model", "-m", help="Model to use"),
    cwd: str = typer.Option(".", "--cwd", help="Working directory"),
    auto_allow: bool = typer.Option(False, "--auto-allow", help="Auto-allow all tool executions (for testing)"),
    prompt: str | None = typer.Option(None, "--prompt", "-p", help="Run a single prompt in headless mode"),
    json_mode: bool = typer.Option(False, "--json", help="Output structured JSON in headless mode"),
    tui: bool = typer.Option(False, "--tui/--no-tui", help="Use Textual TUI interface (default: False)"),
    simple: bool = typer.Option(True, "--simple/--no-simple", help="Use simple CLI (default: True, use --tui for TUI)"),
    skip_config_check: bool = typer.Option(False, "--skip-config-check", help="Skip configuration check (for testing)"),
):
    """PilotCode - Python rewrite of Claude Code."""
    
    if version:
        console.print(f"PilotCode {__version__}")
        raise typer.Exit()
    
    # Check configuration unless skipped or running headless
    if not skip_config_check and not prompt:
        if not check_configuration():
            console.print("\n[yellow]Configuration required. Run:[/yellow]")
            console.print("  [cyan]python -m pilotcode configure[/cyan]")
            console.print("or")
            console.print("  [cyan]python -m pilotcode.main --configure[/cyan]")
            raise typer.Exit(code=1)
    
    if prompt is not None:
        import asyncio
        asyncio.run(run_headless(prompt, auto_allow=auto_allow, json_mode=json_mode))
        raise typer.Exit()
    
    if tui:
        # Launch Textual TUI
        from .tui.simple_app import SimpleTUI
        from .state.app_state import get_default_app_state
        from .state.store import Store, set_global_store
        from .tools.registry import get_all_tools
        
        store = Store(get_default_app_state())
        set_global_store(store)
        tools = get_all_tools()
        
        app_tui = SimpleTUI(store=store, tools=tools, auto_allow=auto_allow)
        app_tui.run()
    elif simple:
        # Launch Simple CLI (default)
        import asyncio
        from .tui.simple_cli import SimpleCLI
        
        cli = SimpleCLI(auto_allow=auto_allow)
        try:
            asyncio.run(cli.run())
        except KeyboardInterrupt:
            print("\nGoodbye! 👋")
    else:
        # Show banner for REPL mode
        banner = f"""
[bold cyan]PilotCode[/bold cyan] [dim]v{__version__}[/dim]

[cyan]An AI-powered coding assistant[/cyan]
[dim]Type /help for commands or start chatting![/dim]
"""
        console.print(Panel(banner, border_style="cyan"))
        
        # Start REPL with options
        run_repl(auto_allow=auto_allow)


@app.command()
def configure(
    wizard: bool = typer.Option(True, "--wizard/--quick", help="Use interactive wizard"),
    model: str | None = typer.Option(None, "--model", "-m", help="Model name for quick setup"),
    api_key: str | None = typer.Option(None, "--api-key", "-k", help="API key for quick setup"),
    base_url: str | None = typer.Option(None, "--base-url", "-u", help="Custom base URL"),
    list_models: bool = typer.Option(False, "--list-models", "-l", help="List all available models"),
    show: bool = typer.Option(False, "--show", "-s", help="Show current configuration"),
):
    """Configure PilotCode settings and model."""
    from .utils.configure import quick_configure, show_current_config
    
    if list_models:
        console.print(format_model_list())
        return
    
    if show:
        show_current_config()
        return
    
    if model:
        success = quick_configure(model, api_key, base_url)
        if not success:
            raise typer.Exit(code=1)
    elif wizard:
        success = run_configure_wizard()
        if not success:
            raise typer.Exit(code=1)
    else:
        console.print("[yellow]Use --model MODEL_NAME for quick setup or run with --wizard[/yellow]")
        console.print(f"\nAvailable models: {', '.join(get_available_model_names())}")


@app.command()
def config(
    list: bool = typer.Option(False, "--list", "-l", help="List configuration"),
    set_key: str | None = typer.Option(None, "--set", help="Set configuration key"),
    set_value: str | None = typer.Option(None, "--value", help="Configuration value"),
):
    """Manage configuration (legacy command, use 'configure' instead)."""
    from .utils.config import get_global_config, get_config_manager
    
    if list:
        config = get_global_config()
        console.print("[bold]Global Configuration:[/bold]")
        console.print(f"  Theme: {config.theme}")
        console.print(f"  Verbose: {config.verbose}")
        console.print(f"  Auto Compact: {config.auto_compact}")
        console.print(f"  Default Model: {config.default_model}")
        console.print(f"  Model Provider: {config.model_provider}")
        console.print(f"  Base URL: {config.base_url or 'Default'}")
        console.print(f"  API Key: {'***set***' if config.api_key else 'Not set'}")
        
        config_file = get_config_manager().SETTINGS_FILE
        console.print(f"\n[dim]Config file: {config_file}[/dim]")
        
    elif set_key and set_value:
        manager = get_config_manager()
        config = get_global_config()
        
        # Handle boolean values
        if set_value.lower() in ("true", "false"):
            set_value = set_value.lower() == "true"
        
        if hasattr(config, set_key):
            setattr(config, set_key, set_value)
            manager.save_global_config(config)
            console.print(f"[green]Set {set_key} = {set_value}[/green]")
        else:
            console.print(f"[red]Unknown configuration key: {set_key}[/red]")
    else:
        console.print("[yellow]Use --list to view config or --set/--value to modify[/yellow]")
        console.print("\n[dim]Tip: Use 'configure' command for interactive setup:[/dim]")
        console.print("  [cyan]python -m pilotcode configure[/cyan]")


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


from .utils.configure import get_available_model_names


def cli_main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    cli_main()
