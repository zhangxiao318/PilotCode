"""CLI entry point for PilotCode."""

import asyncio
import typer
from rich.console import Console
from rich.panel import Panel

from .components.repl import run_repl, run_headless, run_headless_with_planning, run_headless_with_feedback, classify_task_complexity
from .version import __version__
from .utils.config import is_configured, get_config_manager
from .utils.configure import run_configure_wizard, format_model_list, get_available_model_names

app = typer.Typer(
    name="pilotcode", help="PilotCode - AI-powered coding assistant", add_completion=False
)
console = Console()


def check_configuration() -> bool:
    """Check if application is configured, prompt user if not.

    Performs both static configuration check and live LLM verification.

    Returns:
        True if configured or user configured it, False otherwise.
    """
    # Quick check: configuration exists
    if not is_configured():
        return _show_configuration_prompt()

    # Get config to check if it's a local model (skip verification for local models)
    config_manager = get_config_manager()
    config = config_manager.load_global_config()

    # Check both config file and environment variables for base_url
    # Environment variables can override config, so we need to check both
    import os

    env_base_url = os.environ.get("OPENAI_BASE_URL") or os.environ.get("PILOTCODE_BASE_URL")
    effective_base_url = env_base_url or config.base_url or ""

    # Also check the raw config file (before env var overrides)
    # This handles the case where user configured a local model but env var overrides it
    raw_config = config_manager.load_raw_global_config()
    config_base_url = raw_config.base_url or config.base_url or ""

    def is_local_url(url: str) -> bool:
        """Check if URL points to a local/internal model."""
        if not url:
            return False
        return (
            "localhost" in url
            or "127.0.0.1" in url
            or ":11434" in url
            or url.startswith("http://192.168.")
            or url.startswith("http://10.")
            or url.startswith("http://172.")
        )

    # Skip dynamic verification for local/internal network models
    # Check both effective URL (after env override) and config file URL
    is_local_model = is_local_url(effective_base_url) or is_local_url(config_base_url)

    if is_local_model:
        display_url = effective_base_url or config_base_url
        console.print(f"[dim]Using local/internal LLM at {display_url}[/dim]")
        return True

    # Deep check: verify LLM is actually accessible
    try:
        console.print("[dim]Verifying LLM configuration...[/dim]")
        verification = asyncio.run(config_manager.verify_configuration(timeout=10.0))

        if verification["success"]:
            console.print(f"[green]✓[/green] LLM ready: {verification['response'][:60]}...")
            return True
        else:
            console.print(
                Panel.fit(
                    f"[bold yellow]⚠️  LLM connection failed[/bold yellow]\n\n"
                    f"Configuration exists but connection test failed:\n"
                    f"[red]{verification['message']}[/red]\n\n"
                    f"Please check your settings.",
                    border_style="yellow",
                )
            )
            return _show_configuration_prompt(skip_static_check=True)

    except Exception as e:
        console.print(f"[yellow]Warning: Could not verify LLM: {e}[/yellow]")
        # Fall back to static check
        return True


def _show_configuration_prompt(skip_static_check: bool = False) -> bool:
    """Show configuration prompt to user."""
    if not skip_static_check:
        console.print(
            Panel.fit(
                "[bold yellow]⚠️  PilotCode is not configured yet[/bold yellow]\n\n"
                "You need to configure a language model to use PilotCode.",
                border_style="yellow",
            )
        )

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
        console.print(
            "  [green]PILOTCODE_MODEL[/green]        - Model name (e.g., deepseek, openai)"
        )
        console.print("  [green]PILOTCODE_BASE_URL[/green]     - Custom base URL (optional)")
        console.print("\nOr provider-specific variables:")
        console.print(
            "  [green]OPENAI_API_KEY[/green], [green]ANTHROPIC_API_KEY[/green], [green]DEEPSEEK_API_KEY[/green]"
        )
        console.print(
            "  [green]DASHSCOPE_API_KEY[/green], [green]ZHIPU_API_KEY[/green], [green]MOONSHOT_API_KEY[/green], etc."
        )

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
    auto_allow: bool = typer.Option(
        False, "--auto-allow", help="Auto-allow all tool executions (for testing)"
    ),
    prompt: str | None = typer.Option(
        None, "--prompt", "-p", help="Run a single prompt in headless mode"
    ),
    json_mode: bool = typer.Option(False, "--json", help="Output structured JSON in headless mode"),
    max_iterations: int = typer.Option(
        25,
        "--max-iterations",
        "-i",
        help="Maximum tool execution rounds per query (default: 25, env: PILOTCODE_MAX_ITERATIONS)",
    ),
    tui_v2: bool = typer.Option(
        True, "--tui-v2/--no-tui-v2", help="Use TUI v2 interface (default: True)"
    ),
    simple: bool = typer.Option(
        False, "--simple/--no-simple", help="Use simple CLI without TUI (default: False)"
    ),
    web: bool = typer.Option(
        False, "--web", help="Launch Web UI server (default: False)"
    ),
    web_port: int = typer.Option(
        8080, "--web-port", help="Port for Web UI server (default: 8080)"
    ),
    web_host: str = typer.Option(
        "127.0.0.1", "--web-host", help="Host for Web UI server (default: 127.0.0.1)"
    ),
    skip_config_check: bool = typer.Option(
        False, "--skip-config-check", help="Skip configuration check (for testing)"
    ),
    daemon: bool = typer.Option(
        False, "--daemon", help="Run in daemon mode (stdio) for VS Code integration"
    ),
    planning: bool = typer.Option(
        True, "--planning/--no-planning", help="Enable automatic planning mode for complex tasks (default: True)"
    ),
):
    """PilotCode - Python rewrite of Claude Code."""

    if daemon:
        # Run in daemon mode for VS Code (skip config check)
        from .daemon import start_daemon

        start_daemon()
        raise typer.Exit()

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

        async def _run_headless():
            if planning:
                mode = await classify_task_complexity(prompt, cwd=cwd)
            else:
                mode = "DIRECT"
            if mode == "PLAN":
                console.print("[dim]⚡ Task classified as complex — enabling planning and verification mode[/dim]")
                return await run_headless_with_feedback(
                    prompt,
                    auto_allow=auto_allow,
                    json_mode=json_mode,
                    max_iterations=max_iterations,
                    cwd=cwd,
                    use_planning=True,
                )
            else:
                console.print("[dim]⚡ Task classified as simple — running in direct execution mode with feedback[/dim]")
                return await run_headless_with_feedback(
                    prompt,
                    auto_allow=auto_allow,
                    json_mode=json_mode,
                    max_iterations=max_iterations,
                    cwd=cwd,
                    use_planning=False,
                )

        asyncio.run(_run_headless())
        raise typer.Exit()

    if web:
        # Launch Web UI server
        import socket
        from .web.server import run_server_standalone

        def is_port_available(host: str, port: int) -> bool:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                return s.connect_ex((host, port)) != 0

        port = web_port
        host = web_host

        # Find available ports
        original_port = port
        max_attempts = 50
        attempts = 0
        while attempts < max_attempts:
            if is_port_available(host, port) and is_port_available(host, port + 1):
                break
            port += 2
            attempts += 1

        if attempts >= max_attempts:
            console.print(f"[red]Could not find available ports near {original_port}[/red]")
            raise typer.Exit(code=1)

        url = f"http://{host}:{port}"
        ws_url = f"ws://{host}:{port + 1}"

        import webbrowser
        banner = f"""
[bold cyan]PilotCode Web UI[/bold cyan] [dim]v{__version__}[/dim]

[cyan]Web interface is starting...[/cyan]
[dim]Press Ctrl+C to stop the server[/dim]

  📡 HTTP:      {url}
  📡 WebSocket: {ws_url}
"""
        console.print(Panel(banner, border_style="cyan"))

        # Open browser
        try:
            webbrowser.open(url)
        except Exception:
            pass

        # Start server (blocks until Ctrl+C)
        try:
            run_server_standalone(host, port, cwd)
        except KeyboardInterrupt:
            console.print("\n[yellow]Server stopped.[/yellow]")
    elif simple:
        # Launch Simple CLI (non-TUI)
        import asyncio
        from .tui.simple_cli import SimpleCLI

        cli = SimpleCLI(auto_allow=auto_allow, max_iterations=max_iterations)
        try:
            asyncio.run(cli.run())
        except KeyboardInterrupt:
            print("\nGoodbye! 👋")
    elif tui_v2:
        # Launch Enhanced TUI v2 (default)
        from .tui_v2.app import EnhancedApp

        app_tui = EnhancedApp(auto_allow=auto_allow, max_iterations=max_iterations)
        app_tui.run()
    else:
        # Show banner for REPL mode
        banner = f"""
[bold cyan]PilotCode[/bold cyan] [dim]v{__version__}[/dim]

[cyan]An AI-powered coding assistant[/cyan]
[dim]Type /help for commands or start chatting![/dim]
"""
        console.print(Panel(banner, border_style="cyan"))

        # Start REPL with options
        run_repl(auto_allow=auto_allow, max_iterations=max_iterations)


@app.command()
def configure(
    wizard: bool = typer.Option(True, "--wizard/--quick", help="Use interactive wizard"),
    model: str | None = typer.Option(None, "--model", "-m", help="Model name for quick setup"),
    api_key: str | None = typer.Option(None, "--api-key", "-k", help="API key for quick setup"),
    base_url: str | None = typer.Option(None, "--base-url", "-u", help="Custom base URL"),
    list_models: bool = typer.Option(
        False, "--list-models", "-l", help="List all available models"
    ),
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
        console.print(
            "[yellow]Use --model MODEL_NAME for quick setup or run with --wizard[/yellow]"
        )
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


def cli_main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    cli_main()
