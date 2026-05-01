"""CLI entry point for PilotCode."""

import sys
import asyncio
from typing import Any, Callable, List

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
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .components.repl import (
    run_repl,
    run_headless,
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

    api_protocol = caps.get("_api_protocol")
    if api_protocol:
        console.print(f"  API Protocol: {api_protocol}")

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

    # Programming-relevant capabilities from static config (API rarely exposes these)
    if static_info:
        console.print("  [dim]Coding capabilities:[/dim]")
        console.print(f"    Tool calls:   {'✓' if static_info.supports_tools else '✗'}")
        console.print(
            f"    JSON output:  {'✓' if hasattr(static_info, 'supports_json') and static_info.supports_json else '✓ (inferred)'}"
        )
        console.print(f"    Vision:       {'✓' if static_info.supports_vision else '✗'}")

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
        verification = asyncio.run(config_manager.verify_configuration(timeout=5.0))

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
        api_caps = asyncio.run(asyncio.wait_for(_probe(), timeout=5.0))
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
                if Confirm.ask("Update settings.json to match detected value?", default=True):
                    local_updates["context_window"] = detected_ctx

        # For vLLM, check model name
        if backend == "vllm":
            detected_model = api_caps.get("model_id") or api_caps.get("display_name")
            if detected_model and config.default_model != detected_model:
                console.print(
                    f"[yellow]⚠ vLLM model name mismatch: "
                    f"settings.json='{config.default_model}', detected='{detected_model}'[/yellow]"
                )
                if Confirm.ask("Update default_model in settings.json?", default=True):
                    local_updates["default_model"] = detected_model

        # Check /v1 suffix for OpenAI-compatible backends
        if backend in ("vllm", "openai-compatible") and config.base_url:
            url = config.base_url.rstrip("/")
            if not url.endswith("/v1"):
                console.print(f"[yellow]⚠ base_url missing /v1 suffix: {config.base_url}[/yellow]")
                if Confirm.ask("Auto-append /v1 to base_url?", default=True):
                    local_updates["base_url"] = url + "/v1"

        if local_updates:
            for key, val in local_updates.items():
                setattr(config, key, val)
            config_manager.save_global_config(config)
            console.print("[green]✓ settings.json updated.[/green]")
    except asyncio.TimeoutError:
        console.print("[dim]Local model probe timed out (5s), using existing config[/dim]")
    except Exception as e:
        console.print(f"[dim]Could not probe local model: {e}[/dim]")


async def _quick_probe(timeout: float = 3.0) -> tuple[bool, str]:
    """Lightweight connectivity probe on startup.

    Uses the configured URL and protocol to send a single message.
    Prints what it is probing and the result.
    Returns (ok, message).  ok=True if any non-empty response arrives.
    """
    from .utils.model_client import ModelClient, Message
    from .utils.config import get_global_config

    config = get_global_config()
    proto = config.api_protocol or "auto-detect"
    url = config.base_url or "(not set)"
    console.print(
        f"[dim]  → Probing LLM at {url} "
        f"(protocol: {proto}, model: {config.default_model or 'default'})...[/dim]"
    )

    client = ModelClient()
    try:
        test_messages = [Message(role="user", content="hi")]
        response_text = ""
        reasoning_text = ""
        async for chunk in client.chat_completion(
            test_messages,
            max_tokens=5,
            stream=False,
            temperature=0.0,
        ):
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            text = delta.get("content", "")
            if text:
                response_text += text
            reasoning = delta.get("reasoning_content", "")
            if reasoning:
                reasoning_text += reasoning

        combined = (response_text + reasoning_text).strip()
        if combined:
            preview = combined[:40].replace("\n", " ")
            console.print(f"[dim]  ✓ Got response: '{preview}'[/dim]")
            return True, "LLM responded"
        console.print("[dim]  ✗ Empty response[/dim]")
        return False, "Empty response"
    except asyncio.TimeoutError:
        console.print(f"[dim]  ✗ Timeout after {timeout}s[/dim]")
        return False, f"Connection timeout after {timeout}s"
    except Exception as e:
        err = str(e)[:120]
        console.print(f"[dim]  ✗ Error: {err}[/dim]")
        return False, err
    finally:
        await client.close()


async def _diagnose_connection() -> None:
    """Run detailed diagnostics when the quick probe fails.

    Prints actionable guidance to the console.
    """
    from .utils.config import get_global_config
    from .utils.model_client import ModelClient
    from pilotcode.utils.models_config import infer_api_protocol

    config = get_global_config()
    console.print("\n[bold yellow]🔍 Diagnosing connection...[/bold yellow]")

    console.print(f"  Model:      {config.default_model or '(not set)'}")
    console.print(f"  Base URL:   {config.base_url or '(not set)'}")
    console.print(f"  Protocol:   {config.api_protocol or 'auto-detect'}")
    console.print(f"  API Key:    {'***set***' if config.api_key else '[red]Not set[/red]'}")

    if not config.api_key and not is_local_url(config.base_url or ""):
        console.print(
            "\n[yellow]⚠ No API key found in config.\n"
            "  If you set it via env var, ModelClient will pick it up.[/yellow]\n"
            "  export PILOTCODE_API_KEY=sk-...\n"
            "  pilotcode configure"
        )

    client = ModelClient()

    # 1. Try /v1/models (or /models) to see if the server is up
    console.print("[dim]  → Detecting available models from API...[/dim]")
    try:
        models = await asyncio.wait_for(client.detect_models(), timeout=5.0)
        if models:
            console.print(
                f"[green]  ✓ API server reachable[/green] — detected {len(models)} model(s)"
            )
            for m in models[:5]:
                name = m.get("display_name") or m.get("id", "")
                console.print(f"    • {name}")
        else:
            console.print("[yellow]  ⚠ API server reachable but no models found[/yellow]")
    except Exception as e:
        console.print(f"[red]  ✗ Cannot reach API server: {e}[/red]")
        console.print(
            "\n[dim]Common fixes:[/dim]\n"
            "  • Check base_url (e.g. https://api.anthropic.com/v1)\n"
            "  • Check firewall / proxy settings\n"
            "  • Verify the API server is running (for local models)"
        )
        await client.close()
        return

    # 2. Try a minimal chat completion to catch auth / protocol mismatches
    console.print("[dim]  → Testing chat completion (auth / protocol check)...[/dim]")
    try:
        ok, msg = await asyncio.wait_for(_quick_probe(timeout=5.0), timeout=6.0)
        if ok:
            console.print("[green]  ✓ Chat completion works[/green]")
        else:
            console.print(f"[yellow]  ⚠ Chat completion failed: {msg}[/yellow]")
            proto = infer_api_protocol(
                config.default_model or "",
                config.base_url or "",
                {"api_protocol": config.api_protocol},
                None,
            )
            if "Empty response" in msg:
                console.print(
                    "    [dim]Hint: The server replied but returned no content. "
                    "This usually means the API protocol doesn't match the endpoint. "
                    f"Current protocol is '{proto}'; try the other one.[/dim]"
                )
            elif proto == "anthropic":
                console.print(
                    "    [dim]Hint: Anthropic uses 'x-api-key' header. "
                    "Make sure the key is valid and has not expired.[/dim]"
                )
            elif proto == "openai":
                console.print(
                    "    [dim]Hint: Verify the API key and base_url. "
                    "OpenAI-compatible endpoints should respond to /chat/completions.[/dim]"
                )
    except Exception as e:
        console.print(f"[yellow]  ⚠ Chat completion failed: {e}[/yellow]")

    await client.close()


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

    choice = Prompt.ask("Select option", choices=["1", "2", "3", "4"], default="1")

    if choice == "1":
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
        if Confirm.ask("Run configuration wizard now?", default=True):
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
    config_check: bool = typer.Option(
        False, "--config-check", help="Run live LLM configuration check on startup"
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

    # Check configuration only when explicitly requested with --config-check
    # Default is skipped for fast startup; static check still runs if not configured
    if config_check and not prompt:
        if not check_configuration():
            console.print("\n[yellow]Configuration required. Run:[/yellow]")
            console.print("  [cyan]python -m pilotcode configure[/cyan]")
            console.print("or")
            console.print("  [cyan]python -m pilotcode.main --configure[/cyan]")
            raise typer.Exit(code=1)
    elif not prompt:
        # Fast path: check config exists, then lightweight probe
        if not is_configured():
            console.print("\n[yellow]Configuration required. Run:[/yellow]")
            console.print("  [cyan]python -m pilotcode configure[/cyan]")
            console.print("or")
            console.print("  [cyan]python -m pilotcode.main --configure[/cyan]")
            raise typer.Exit(code=1)

        # Lightweight startup probe: 3-second connectivity check
        try:
            ok, msg = asyncio.run(asyncio.wait_for(_quick_probe(timeout=3.0), timeout=4.0))
            if ok:
                console.print("[dim]✓ LLM reachable[/dim]")
            else:
                console.print(f"[yellow]⚠ LLM probe warning: {msg}[/yellow]")
                asyncio.run(_diagnose_connection())
                if not Confirm.ask("Continue starting anyway?", default=True):
                    raise typer.Exit(code=1)
        except asyncio.TimeoutError:
            console.print(
                "[yellow]⚠ LLM probe timed out (>4s). Server may be slow or unreachable.[/yellow]"
            )
            asyncio.run(_diagnose_connection())
            if not Confirm.ask("Continue starting anyway?", default=True):
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
                adapter = MissionAdapter(cwd=cwd)
                result = await adapter.run(prompt, cwd=cwd)
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
            run_server_standalone(host, port, cwd, auto_allow=auto_allow)
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
    protocol: str | None = typer.Option(
        None, "--protocol", "-p", help='API protocol: "openai" or "anthropic"'
    ),
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
        success = quick_configure(model, api_key, base_url, protocol)
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


def _validate_and_select_remote_model(console, config, base_url: str) -> None:
    """Validate remote model config and let user pick a valid model if needed."""
    from .utils.config import get_config_manager
    from .utils.models_config import get_model_info

    base = base_url.lower()

    def _sync_provider() -> None:
        """Sync model_provider to match the newly chosen default_model."""
        model_info = get_model_info(config.default_model)
        if model_info:
            config.model_provider = model_info.provider.value
        elif "deepseek" in base:
            config.model_provider = "deepseek"

    if "deepseek" in base:
        valid_models = ["deepseek-v4-pro", "deepseek-v4-flash"]
        deprecated = {
            "deepseek-chat": "deepseek-v4-flash (non-thinking)",
            "deepseek-reasoner": "deepseek-v4-flash (thinking)",
        }
        current = config.default_model or ""

        if current in deprecated:
            console.print(
                f"\n[yellow]⚠ Deprecated model name:[/yellow] {current}\n"
                f"  [dim]DeepSeek deprecated this on 2026/07/24. "
                f"Use {deprecated[current]} instead.[/dim]"
            )
            if Confirm.ask("Update to deepseek-v4-pro?", default=True):
                config.default_model = "deepseek-v4-pro"
                _sync_provider()
                get_config_manager().save_global_config(config)
                console.print("[green]✓ default_model updated to deepseek-v4-pro[/green]")
            return

        if current not in valid_models:
            console.print(
                f"\n[yellow]⚠ Invalid model for DeepSeek:[/yellow] {current or '(not set)'}\n"
                f"  [dim]Valid models: {', '.join(valid_models)}[/dim]"
            )
            console.print("\n[bold]Select a model:[/bold]")
            for i, m in enumerate(valid_models, 1):
                label = "[Recommended]" if m == "deepseek-v4-pro" else ""
                console.print(f"  {i}. {m} {label}")
            choice = Prompt.ask("Enter number", choices=["1", "2"], default="1")
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(valid_models):
                    config.default_model = valid_models[idx]
                    _sync_provider()
                    get_config_manager().save_global_config(config)
                    console.print(
                        f"[green]✓ default_model updated to {config.default_model}[/green]"
                    )
                else:
                    console.print("[red]Invalid choice, skipping update.[/red]")
            except ValueError:
                console.print("[red]Invalid choice, skipping update.[/red]")


@app.command()
def config(
    list: bool = typer.Option(False, "--list", "-l", help="List configuration"),
    set_key: str | None = typer.Option(None, "--set", help="Set configuration key"),
    set_value: str | None = typer.Option(None, "--value", help="Configuration value"),
    test: str | None = typer.Option(
        None, "--test", "-t", help="Run e2e capability tests: layer1, layer2, or capability"
    ),
):
    """Manage configuration (legacy command, use 'configure' instead)."""
    from .utils.config import get_global_config, get_config_manager

    if test:
        from .commands.config_cmd import _run_layer_test

        layer = test.lower().strip()
        if layer == "capability":
            from .model_capability import evaluate_model, save_capability, format_evaluation_report
            from pathlib import Path

            config = get_global_config()
            model_name = config.default_model or "unknown"

            console.print(f"[bold]⏳ Starting capability benchmark for {model_name}...[/bold]")
            console.print("[dim]This may take 1–3 minutes depending on model speed[/dim]\n")

            cap = asyncio.run(evaluate_model(model_name))

            from pilotcode.utils.paths import get_model_capability_path

            save_path = get_model_capability_path()
            save_capability(cap, str(save_path))
            # Also try cwd
            try:
                cwd_path = Path.cwd() / ".pilotcode" / "model_capability.json"
                save_capability(cap, str(cwd_path))
            except Exception:
                pass

            report = format_evaluation_report([], cap)
            console.print(report)
            console.print(f"\n[green]✓ Capability profile saved to {save_path}[/green]")
            raise typer.Exit(0)

        if layer not in ("layer1", "layer2"):
            console.print(f"[red]Unknown test type: {layer}. Use: layer1, layer2, capability[/red]")
            raise typer.Exit(1)

        console.print(f"[bold]⏳ Starting Layer {layer[-1]} E2E test...[/bold]")
        console.print(
            "[dim]This may take several minutes (typically 3–15 min depending on model speed)[/dim]\n"
        )

        report = asyncio.run(_run_layer_test(layer))
        console.print(report)
        raise typer.Exit(0)

    if list:
        from .utils.models_config import get_model_info

        config = get_global_config()

        # ------------------------------------------------------------------
        # Step 1: Basic config display
        # ------------------------------------------------------------------
        console.print("[bold]Global Configuration:[/bold]")
        console.print(f"  Theme: {config.theme}")
        console.print(f"  Verbose: {config.verbose}")
        console.print(f"  Auto Compact: {config.auto_compact}")
        console.print(f"  Default Model: {config.default_model}")
        console.print(f"  Model Provider: {config.model_provider}")
        console.print(f"  API Protocol: {config.api_protocol or 'auto-detect'}")
        console.print(f"  Base URL: {config.base_url or 'Default'}")
        console.print(f"  API Key: {'***set***' if config.api_key else 'Not set'}")
        if config.context_window > 0:
            console.print(f"  Context Window: {config.context_window}")

        # ------------------------------------------------------------------
        # Step 2: Provider validation (model name, deprecated models, etc.)
        # ------------------------------------------------------------------
        effective_url = config.base_url or ""
        _validate_and_select_remote_model(console, config, effective_url)

        # Re-fetch config after potential user interaction above
        config = get_global_config()

        # ------------------------------------------------------------------
        # Step 3: Probe runtime capabilities (local OR remote)
        # ------------------------------------------------------------------
        static_info = get_model_info(config.default_model)

        if config.base_url:
            is_local = is_local_url(effective_url)
            label = "local" if is_local else "remote"
            console.print(f"\n[dim]Probing {label} model runtime info...[/dim]")

            async def _probe() -> tuple[dict | None, List[dict[str, str]]]:
                from .utils.model_client import ModelClient

                client = ModelClient(
                    api_key=config.api_key or None,
                    base_url=config.base_url or None,
                    model=config.default_model or None,
                )
                try:
                    caps = await client.fetch_model_capabilities()
                    models = await client.detect_models()
                    return caps, models
                finally:
                    await client.close()

            try:
                api_caps, detected_models = asyncio.run(asyncio.wait_for(_probe(), timeout=15.0))
                if detected_models:
                    console.print("\n[bold]Detected Models:[/bold]")
                    for m in detected_models[:10]:
                        name = m.get("display_name") or m.get("id", "")
                        mid = m.get("id", "")
                        if name and name != mid:
                            console.print(f"  • {name} [dim]({mid})[/dim]")
                        else:
                            console.print(f"  • {mid}")
                    if len(detected_models) > 10:
                        console.print(f"  ... and {len(detected_models) - 10} more")

                if api_caps:
                    api_err = api_caps.get("_error")
                    if api_err:
                        console.print(
                            f"\n[yellow]⚠ Could not probe runtime capabilities: {api_err}[/yellow]"
                        )
                        console.print("[dim]  Using static configuration from models.json.[/dim]")
                    console.print("\n[bold]Model Capability (Runtime Detected):[/bold]")
                    _print_api_capability(console, api_caps, static_info=static_info)

                    # --- Check settings.json against probed values ---
                    updates: dict[str, Any] = {}

                    detected_ctx = api_caps.get("context_window")
                    if detected_ctx is not None:
                        if config.context_window <= 0:
                            console.print(
                                f"\n[yellow]⚠ context_window not set in settings.json. "
                                f"Detected: {detected_ctx}[/yellow]"
                            )
                            updates["context_window"] = detected_ctx
                        elif config.context_window != detected_ctx:
                            # Warn if user's value is way off (e.g. 10x smaller)
                            ratio = detected_ctx / max(config.context_window, 1)
                            if ratio >= 2 or ratio <= 0.5:
                                console.print(
                                    f"\n[yellow]⚠ context_window mismatch: "
                                    f"settings.json={config.context_window}, detected={detected_ctx}"
                                    f" (ratio {ratio:.1f}x)[/yellow]"
                                )
                            else:
                                console.print(
                                    f"\n[dim]context_window differs slightly: "
                                    f"settings.json={config.context_window}, detected={detected_ctx}[/dim]"
                                )
                            if Confirm.ask(
                                "Update settings.json to match detected value?", default=True
                            ):
                                updates["context_window"] = detected_ctx

                    detected_model = api_caps.get("model_id") or api_caps.get("display_name")
                    if detected_model and config.default_model != detected_model:
                        console.print(
                            f"\n[yellow]⚠ Model name mismatch: "
                            f"settings.json='{config.default_model}', detected='{detected_model}'[/yellow]"
                        )
                        if Confirm.ask("Update default_model in settings.json?", default=True):
                            updates["default_model"] = detected_model

                    # --- Suggest /v1 suffix for self-hosted OpenAI-compatible backends ---
                    backend = api_caps.get("_backend", "")
                    base_lower = (config.base_url or "").lower()
                    is_known_cloud = any(
                        host in base_lower
                        for host in ("deepseek", "openai", "anthropic", "moonshot", "baichuan")
                    )
                    if (
                        backend in ("vllm", "openai-compatible")
                        and config.base_url
                        and not is_known_cloud
                    ):
                        url = config.base_url.rstrip("/")
                        if not url.endswith("/v1"):
                            console.print(
                                f"\n[yellow]⚠ base_url missing /v1 suffix:[/yellow] {config.base_url}"
                            )
                            console.print(
                                "  [dim]Self-hosted OpenAI-compatible backends (vLLM, TGI, etc.) typically "
                                "expose endpoints under /v1 (e.g. /v1/chat/completions).[/dim]"
                            )
                            if Confirm.ask("Auto-append /v1 to base_url?", default=True):
                                updates["base_url"] = url + "/v1"

                    if updates:
                        for key, val in updates.items():
                            setattr(config, key, val)
                        get_config_manager().save_global_config(config)
                        console.print("[green]✓ settings.json updated.[/green]")
                elif api_caps and api_caps.get("_error"):
                    err = api_caps["_error"]
                    console.print(f"[red]  Could not connect to backend: {err}[/red]")
                    console.print(
                        "  [dim]Tips:[/dim]\n"
                        "    • Check if the server is running\n"
                        "    • Verify base_url uses the correct protocol (http vs https)\n"
                        "    • Check firewall / port accessibility"
                    )
                    if static_info:
                        console.print("\n[bold]Model Capability (Static Config):[/bold]")
                        _print_model_capability(console, static_info, source="static")
                else:
                    console.print("[dim]  Model did not expose capability metadata.[/dim]")
                    if static_info:
                        console.print("\n[bold]Model Capability (Static Config):[/bold]")
                        _print_model_capability(console, static_info, source="static")
            except asyncio.TimeoutError:
                console.print("[red]  Connection timed out (10s).[/red]")
                console.print(
                    "  [dim]Tips:[/dim]\n"
                    "    • Check if the server is running\n"
                    "    • Verify base_url uses the correct protocol (http vs https)\n"
                    "    • Check firewall / port accessibility"
                )
                if static_info:
                    console.print("\n[bold]Model Capability (Static Config):[/bold]")
                    _print_model_capability(console, static_info, source="static")
            except Exception as e:
                console.print(f"[red]  Could not probe model: {type(e).__name__}: {e}[/red]")
                if static_info:
                    console.print("\n[bold]Model Capability (Static Config):[/bold]")
                    _print_model_capability(console, static_info, source="static")
        else:
            # No API key or base_url — can only show static config
            if static_info:
                console.print("\n[bold]Model Capability (Static Config):[/bold]")
                _print_model_capability(console, static_info, source="static")
            else:
                console.print(
                    "\n[yellow]No static config found for model '{config.default_model}'. "
                    "Run with --wizard to configure.[/yellow]"
                )

        config_file = get_config_manager().SETTINGS_FILE
        console.print(f"\n[dim]Config file: {config_file}[/dim]")

    elif set_key and set_value:
        manager = get_config_manager()
        config = get_global_config()

        # Handle boolean values
        if set_value.lower() in ("true", "false"):
            set_value = set_value.lower() == "true"

        if hasattr(config, set_key):
            old_value = getattr(config, set_key)
            setattr(config, set_key, set_value)
            manager.save_global_config(config)
            console.print(f"[green]Set {set_key} = {set_value}[/green]")

            # Prompt for capability test on model change
            if set_key == "default_model" and old_value != set_value:
                from pathlib import Path

                cap_file = Path.home() / ".pilotcode" / "model_capability.json"
                if cap_file.exists():
                    console.print(
                        f"\n[yellow]Model changed from '{old_value}' to '{set_value}'.[/yellow]"
                    )
                    if Confirm.ask("Run capability benchmark for this model?", default=True):
                        from .model_capability import evaluate_model, save_capability

                        cap = asyncio.run(evaluate_model(set_value))
                        save_capability(cap, str(cap_file))
                        console.print(
                            f"[green]Capability profile saved. Overall score: {cap.overall_score:.1%}[/green]"
                        )
                else:
                    console.print(
                        f"\n[yellow]Model changed to '{set_value}'.[/yellow]"
                        "\nTip: Run 'pilotcode config --test capability' to evaluate this model."
                    )
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


@app.command("sessions")
def list_sessions_cmd():
    """List all saved sessions."""
    from pilotcode.services.session_persistence import get_session_persistence

    persistence = get_session_persistence()
    sessions = persistence.list_sessions()

    if not sessions:
        console.print("[dim]No saved sessions found.[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("Session ID", style="cyan", no_wrap=True)
    table.add_column("Messages", justify="right", style="green")
    table.add_column("Project Path", style="yellow")
    table.add_column("Summary", style="white")

    for s in sessions:
        # Truncate long paths and summaries for clean display
        path = s.project_path or "—"
        if len(path) > 35:
            path = "..." + path[-32:]
        summary = s.summary or "—"
        if len(summary) > 40:
            summary = summary[:37] + "..."
        table.add_row(s.session_id, str(s.message_count), path, summary)

    console.print(table)


def cli_main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    cli_main()
