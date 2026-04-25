"""CLI entry point for PilotCode."""

import sys
import asyncio
from typing import Any, Callable

# Fix Windows encoding issues
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    import os

    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import typer
from rich.console import Console
from rich.panel import Panel

from .components.repl import (
    run_repl,
    run_headless,
    run_headless_with_feedback,
    classify_task_complexity,
)
from .orchestration.adapter import MissionAdapter
from .orchestration.report import format_completion, format_failure
from .version import __version__
from .utils.config import is_configured, get_config_manager, is_local_url
from .utils.configure import run_configure_wizard, format_model_list, get_available_model_names

app = typer.Typer(
    name="pilotcode", help="PilotCode - AI-powered coding assistant", add_completion=False
)
console = Console()


def _is_local_url(url: str) -> bool:
    """Check if URL points to a local/internal model.

    Matches localhost, loopback, and RFC1918 private addresses.
    """
    if not url:
        return False

    # localhost / loopback
    if "localhost" in url or "127.0.0.1" in url:
        return True

    # Ollama default port
    if ":11434" in url:
        return True

    # Extract host from URL for RFC1918 checks
    from urllib.parse import urlparse

    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return False

    # 10.x.x.x
    if host.startswith("10."):
        return True

    # 172.16-31.x.x
    if host.startswith("172."):
        parts = host.split(".")
        if len(parts) >= 2:
            try:
                second = int(parts[1])
                if 16 <= second <= 31:
                    return True
            except ValueError:
                pass

    # 192.168.x.x
    if host.startswith("192.168."):
        return True

    return False


def _fmt_ctx(n: int) -> str:
    """Format context window for display."""
    if n >= 1_000_000:
        return f"{n // 1_000_000}M"
    if n >= 1_000:
        return f"{n // 1_000}K"
    return str(n)


def _print_model_capability(console: Console, info, source: str = "static") -> None:
    """Print model capability info from ModelInfo dataclass."""
    ctx = _fmt_ctx(info.context_window)
    max_tok = _fmt_ctx(info.max_tokens)
    console.print(f"  Display Name: {info.display_name}")
    console.print(f"  API Model:    {info.default_model}")
    console.print(f"  Provider:     {info.provider.value}")
    console.print(f"  Context:      {ctx}")
    console.print(f"  Max Tokens:   {max_tok}")
    console.print(f"  Tools:        {'✓' if info.supports_tools else '✗'}")
    console.print(f"  Vision:       {'✓' if info.supports_vision else '✗'}")
    console.print(f"  [dim]Source: {source}[/dim]")


def _print_api_capability(console: Console, caps: dict, static_info=None) -> None:
    """Print model capability info from API-probed dict.

    If static_info (ModelInfo) is provided, values that differ from the
    static config are highlighted in red.
    """

    def _val(label: str, detected: Any, static_val: Any, fmt: Callable[[Any], str] = str) -> None:
        if detected is None:
            return
        text = fmt(detected)
        if static_val is not None and detected != static_val:
            console.print(f"  {label}: [red]{text}[/red]  [dim](config: {fmt(static_val)})[/dim]")
        else:
            console.print(f"  {label}: {text}")

    display_name = caps.get("display_name")
    if display_name:
        static_name = static_info.display_name if static_info else None
        _val("Display Name", display_name, static_name)

    provider = caps.get("_provider")
    if provider:
        static_provider = static_info.provider.value if static_info else None
        _val("Provider", provider, static_provider)

    ctx = caps.get("context_window")
    static_ctx = static_info.context_window if static_info else None
    _val("Context", ctx, static_ctx, _fmt_ctx)

    max_tok = caps.get("max_tokens")
    static_max = static_info.max_tokens if static_info else None
    _val("Max Tokens", max_tok, static_max, _fmt_ctx)

    tools = caps.get("supports_tools")
    if tools is not None:
        static_tools = static_info.supports_tools if static_info else None
        _val("Tools", tools, static_tools, lambda x: "✓" if x else "✗")

    vision = caps.get("supports_vision")
    if vision is not None:
        static_vision = static_info.supports_vision if static_info else None
        _val("Vision", vision, static_vision, lambda x: "✓" if x else "✗")

    backend = caps.get("_backend")
    if backend:
        console.print(f"  [dim]Backend: {backend}[/dim]")


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

    # Skip dynamic verification for local/internal network models
    # Check both effective URL (after env override) and config file URL
    is_local_model = is_local_url(effective_base_url) or is_local_url(config_base_url)

    if is_local_model:
        display_url = effective_base_url or config_base_url
        console.print(f"[dim]Using local/internal LLM at {display_url}[/dim]")

        # Probe local model capabilities and update settings.json if needed
        _probe_and_update_local_config(config, config_manager)
        return True

    # Deep check: verify LLM is actually accessible
    try:
        console.print("[dim]Verifying LLM configuration...[/dim]")
        verification = asyncio.run(config_manager.verify_configuration(timeout=10.0))

        if verification["success"]:
            model_info = verification.get("model_info")
            if model_info:
                # Format context window nicely
                ctx = model_info.get("context_window", 0)
                if ctx >= 1_000_000:
                    ctx_str = f"{ctx // 1_000_000}M"
                elif ctx >= 1_000:
                    ctx_str = f"{ctx // 1_000}K"
                else:
                    ctx_str = str(ctx)

                # Format max tokens nicely
                max_tok = model_info.get("max_tokens", 0)
                if max_tok >= 1_000:
                    max_tok_str = f"{max_tok // 1_000}K"
                else:
                    max_tok_str = str(max_tok)

                console.print(
                    f"[green]✓[/green] LLM ready: [bold cyan]{model_info.get('display_name', model_info.get('name', 'Unknown'))}[/bold cyan]"
                )
                console.print(
                    f"   [dim]Model:[/dim] {model_info.get('default_model', 'N/A')}  "
                    f"[dim]Provider:[/dim] {model_info.get('provider', 'N/A')}  "
                    f"[dim]Context:[/dim] {ctx_str}  "
                    f"[dim]Max tokens:[/dim] {max_tok_str}  "
                    f"[dim]Tools:[/dim] {'✓' if model_info.get('supports_tools') else '✗'}  "
                    f"[dim]Vision:[/dim] {'✓' if model_info.get('supports_vision') else '✗'}"
                )
            else:
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


def _probe_and_update_local_config(config, config_manager) -> None:
    """Probe local model capabilities and update settings.json if needed.

    For local models, settings.json is the single source of truth.
    Prompts user for confirmation, then auto-fixes on confirmation.
    """
    import asyncio
    from .utils.model_client import ModelClient

    async def _probe() -> dict | None:
        client = ModelClient(
            api_key=config.api_key or None,
            base_url=config.base_url or None,
            model=config.default_model or None,
        )
        try:
            return await client.fetch_model_capabilities()
        finally:
            await client.close()

    try:
        api_caps = asyncio.run(_probe())
        if not api_caps:
            return

        local_updates: dict[str, Any] = {}
        backend = api_caps.get("_backend", "")

        # Check context_window
        detected_ctx = api_caps.get("context_window")
        if detected_ctx is not None:
            if config.context_window <= 0:
                console.print(
                    f"[yellow]⚠ context_window not set in settings.json. "
                    f"Detected: {detected_ctx}[/yellow]"
                )
                local_updates["context_window"] = detected_ctx
            elif config.context_window != detected_ctx:
                console.print(
                    f"[yellow]⚠ context_window mismatch: "
                    f"settings.json={config.context_window}, detected={detected_ctx}[/yellow]"
                )
                if typer.confirm("Update settings.json to match detected value?", default=True):
                    local_updates["context_window"] = detected_ctx

        # For vLLM, check model name
        if backend == "vllm":
            detected_model = api_caps.get("model_id") or api_caps.get("display_name")
            if detected_model and config.default_model != detected_model:
                console.print(
                    f"[yellow]⚠ vLLM model name mismatch: "
                    f"settings.json='{config.default_model}', detected='{detected_model}'[/yellow]"
                )
                if typer.confirm("Update default_model in settings.json?", default=True):
                    local_updates["default_model"] = detected_model

        # Check /v1 suffix for OpenAI-compatible backends
        if backend in ("vllm", "openai-compatible") and config.base_url:
            url = config.base_url.rstrip("/")
            if not url.endswith("/v1"):
                console.print(f"[yellow]⚠ base_url missing /v1 suffix: {config.base_url}[/yellow]")
                if typer.confirm("Auto-append /v1 to base_url?", default=True):
                    local_updates["base_url"] = url + "/v1"

        if local_updates:
            for key, val in local_updates.items():
                setattr(config, key, val)
            config_manager.save_global_config(config)
            console.print("[green]✓ settings.json updated.[/green]")
    except Exception as e:
        console.print(f"[dim]Could not probe local model: {e}[/dim]")


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


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
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
        100,
        "--max-iterations",
        "-i",
        help="Maximum tool execution rounds per query (default: 50, env: PILOTCODE_MAX_ITERATIONS)",
    ),
    tui_v2: bool = typer.Option(
        True, "--tui-v2/--no-tui-v2", help="Use TUI v2 interface (default: True)"
    ),
    simple: bool = typer.Option(
        False, "--simple/--no-simple", help="Use simple CLI without TUI (default: False)"
    ),
    web: bool = typer.Option(False, "--web", help="Launch Web UI server (default: False)"),
    web_port: int = typer.Option(8080, "--web-port", help="Port for Web UI server (default: 8080)"),
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
        True,
        "--planning/--no-planning",
        help="Enable automatic planning mode for complex tasks (default: True)",
    ),
    restore: bool = typer.Option(
        False, "--restore", "-r", help="Restore the most recent session on startup"
    ),
    session_id: str | None = typer.Option(
        None, "--session", "-s", help="Restore a specific session by ID"
    ),
):
    """PilotCode - Python rewrite of Claude Code."""

    if ctx.invoked_subcommand is not None:
        return

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
                console.print("[dim]⚡ Task classified as complex — entering P-EVR PLAN mode[/dim]")
                adapter = MissionAdapter()
                result = await adapter.run(prompt)
                if result.get("success"):
                    console.print(format_completion(result))
                else:
                    console.print(format_failure(result, result.get("error", "")))
                return result
            else:
                console.print(
                    "[dim]⚡ Task classified as simple — running in direct execution mode[/dim]"
                )
                return await run_headless(
                    prompt,
                    auto_allow=auto_allow,
                    json_mode=json_mode,
                    max_iterations=max_iterations,
                    cwd=cwd,
                )

        try:
            asyncio.run(_run_headless())
        except KeyboardInterrupt:
            print("\nInterrupted. Goodbye! 👋")
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

        session_options = {
            "restore": restore,
            "session_id": session_id,
            "cwd": cwd,
        }
        app_tui = EnhancedApp(
            auto_allow=auto_allow,
            max_iterations=max_iterations,
            session_options=session_options,
        )
        try:
            app_tui.run()
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
        try:
            run_repl(auto_allow=auto_allow, max_iterations=max_iterations)
        except KeyboardInterrupt:
            print("\nGoodbye! 👋")


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
    test: str | None = typer.Option(None, "--test", "-t", help="Run e2e capability tests: layer1 or layer2"),
):
    """Manage configuration (legacy command, use 'configure' instead)."""
    from .utils.config import get_global_config, get_config_manager

    if test:
        from .commands.config_cmd import _run_layer_test

        layer = test.lower().strip()
        if layer not in ("layer1", "layer2"):
            console.print(f"[red]Unknown layer: {layer}. Use: layer1, layer2[/red]")
            raise typer.Exit(1)

        console.print(f"[bold]⏳ Starting Layer {layer[-1]} E2E test...[/bold]")
        console.print("[dim]This may take several minutes (typically 3–15 min depending on model speed)[/dim]\n")

        report = asyncio.run(_run_layer_test(layer))
        console.print(report)
        raise typer.Exit(0)

    if list:
        import asyncio
        from .utils.models_config import get_model_info

        config = get_global_config()
        console.print("[bold]Global Configuration:[/bold]")
        console.print(f"  Theme: {config.theme}")
        console.print(f"  Verbose: {config.verbose}")
        console.print(f"  Auto Compact: {config.auto_compact}")
        console.print(f"  Default Model: {config.default_model}")
        console.print(f"  Model Provider: {config.model_provider}")
        console.print(f"  Base URL: {config.base_url or 'Default'}")
        console.print(f"  API Key: {'***set***' if config.api_key else 'Not set'}")
        if config.context_window > 0:
            console.print(f"  Context Window: {config.context_window}")

        # --- For local models, probe runtime info and check settings.json ---
        effective_url = config.base_url or ""
        if is_local_url(effective_url):
            console.print("\n[dim]Probing local model runtime info...[/dim]")

            async def _probe_local() -> dict | None:
                from .utils.model_client import ModelClient

                client = ModelClient(
                    api_key=config.api_key or None,
                    base_url=config.base_url or None,
                    model=config.default_model or None,
                )
                try:
                    return await client.fetch_model_capabilities()
                finally:
                    await client.close()

            try:
                api_caps = asyncio.run(_probe_local())
                if api_caps:
                    console.print("[bold]Model Capability (Runtime Detected):[/bold]")
                    _print_api_capability(console, api_caps, static_info=None)

                    # --- Suggest /v1 suffix for OpenAI-compatible local backends ---
                    backend = api_caps.get("_backend", "")
                    if backend in ("vllm", "openai-compatible") and config.base_url:
                        url = config.base_url.rstrip("/")
                        if not url.endswith("/v1"):
                            console.print(
                                f"\n[yellow]⚠ base_url missing /v1 suffix:[/yellow] {config.base_url}"
                            )
                            console.print(
                                "  [dim]vLLM and other OpenAI-compatible backends typically "
                                "expose endpoints under /v1 (e.g. /v1/chat/completions).[/dim]"
                            )
                            if typer.confirm("Auto-append /v1 to base_url?", default=True):
                                config.base_url = url + "/v1"
                                get_config_manager().save_global_config(config)
                                console.print(
                                    f"[green]✓ base_url updated: {config.base_url}[/green]"
                                )

                    # --- For local models, check settings.json against probed values ---
                    # Local models use settings.json as the single source of truth.
                    local_updates: dict[str, Any] = {}

                    detected_ctx = api_caps.get("context_window")
                    if detected_ctx is not None:
                        if config.context_window <= 0:
                            console.print(
                                f"\n[yellow]⚠ context_window not set in settings.json. "
                                f"Detected: {detected_ctx}[/yellow]"
                            )
                            local_updates["context_window"] = detected_ctx
                        elif config.context_window != detected_ctx:
                            console.print(
                                f"\n[yellow]⚠ context_window mismatch: "
                                f"settings.json={config.context_window}, detected={detected_ctx}[/yellow]"
                            )
                            if typer.confirm(
                                "Update settings.json to match detected value?", default=True
                            ):
                                local_updates["context_window"] = detected_ctx

                    # For vLLM, check model name
                    if backend == "vllm":
                        detected_model = api_caps.get("model_id") or api_caps.get("display_name")
                        if detected_model and config.default_model != detected_model:
                            console.print(
                                f"\n[yellow]⚠ vLLM model name mismatch: "
                                f"settings.json='{config.default_model}', detected='{detected_model}'[/yellow]"
                            )
                            if typer.confirm(
                                "Update default_model in settings.json?", default=True
                            ):
                                local_updates["default_model"] = detected_model

                    if local_updates:
                        for key, val in local_updates.items():
                            setattr(config, key, val)
                        get_config_manager().save_global_config(config)
                        console.print("[green]✓ settings.json updated.[/green]")
                else:
                    console.print("[dim]  Local model did not expose capability metadata.[/dim]")
            except Exception as e:
                console.print(f"[yellow]  Could not probe local model: {e}[/yellow]")

        else:
            # Remote models: show static config from models.json
            model_info = get_model_info(config.default_model)
            if model_info:
                console.print("\n[bold]Model Capability (Static Config):[/bold]")
                _print_model_capability(console, model_info, source="static")

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
