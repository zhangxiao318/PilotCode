"""Config command implementation."""

import asyncio
import os
import tempfile
from pathlib import Path

from .base import CommandHandler, register_command, CommandContext

# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Capability benchmark
# ---------------------------------------------------------------------------


async def _run_capability_benchmark() -> str:
    """Run model capability benchmark suite and return report.

    Returns:
        Analysis report text with capability scores and file path.
    """
    from ..model_capability import (
        evaluate_model,
        save_capability,
        format_evaluation_report,
    )
    from ..model_capability.benchmark import BenchmarkConnectionError
    from ..utils.config import get_global_config
    from pathlib import Path

    config = get_global_config()
    model_name = config.default_model or "unknown"

    try:
        cap = await evaluate_model(model_name)
    except BenchmarkConnectionError as e:
        return (
            f"[red]Benchmark aborted: cannot reach model API.[/red]\n"
            f"  Model: {model_name}\n"
            f"  Base URL: {config.base_url}\n"
            f"  Error: {e}\n\n"
            f"Please check:\n"
            f"  1. The model server is running and accessible\n"
            f"  2. The base_url in your config is correct\n"
            f"  3. Network / firewall settings allow the connection"
        )

    # Save to standard location
    save_path = Path.home() / ".pilotcode" / "model_capability.json"
    save_capability(cap, str(save_path))

    # Also save to project root for easy access
    cwd_path = Path.cwd() / ".pilotcode" / "model_capability.json"
    try:
        save_capability(cap, str(cwd_path))
    except Exception:
        pass

    report = format_evaluation_report([], cap)
    report += f"\n\n[Capability profile saved to: {save_path}]"
    return report


async def _run_layer_test(layer: str, extra_pytest_args: list[str] | None = None) -> str:
    """Run Layer 1 or Layer 2 e2e tests and return analysis report.

    Args:
        layer: "layer1" or "layer2"
        extra_pytest_args: Additional arguments to pass to pytest (e.g. ["-k", "test_name"])

    Returns:
        Analysis report text.
    """
    import sys

    # Map layer to test path
    layer_paths = {
        "layer1": "tests/e2e/model_capability/test_bare_llm/",
        "layer2": "tests/e2e/model_capability/test_tool_capability/",
    }
    test_path = layer_paths.get(layer)
    if not test_path:
        return f"Unknown layer: {layer}. Use: layer1, layer2"

    project_root = Path(__file__).resolve().parents[3]
    xml_path = tempfile.mktemp(suffix="_e2e.xml")

    # Build pytest command
    pytest_args = [
        sys.executable,
        "-m",
        "pytest",
        str(project_root / test_path),
        "--run-llm-e2e",
        "--e2e-timeout=240",
        "-v",
        f"--junitxml={xml_path}",
    ]
    if extra_pytest_args:
        pytest_args.extend(extra_pytest_args)

    env = os.environ.copy()
    pythonpath = str(project_root / "src")
    existing = env.get("PYTHONPATH", "")
    if existing:
        pythonpath = f"{pythonpath}{os.pathsep}{existing}"
    env["PYTHONPATH"] = pythonpath
    env["PYTHONUNBUFFERED"] = "1"

    # Run pytest with unbuffered output directly to terminal so user sees progress
    proc = await asyncio.create_subprocess_exec(
        *pytest_args,
        cwd=str(project_root),
        env=env,
        stdout=None,
        stderr=None,
    )
    await proc.communicate()
    if proc.returncode not in (0, 1):
        # pytest exits 0 (all pass) or 1 (some failed); anything else is a crash
        return f"[pytest exited with code {proc.returncode}]"

    # Run analyzer
    analyzer_script = project_root / "tests" / "e2e" / "analyze_results.py"
    report_lines: list[str] = []
    if analyzer_script.exists() and Path(xml_path).exists():
        analyzer_proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(analyzer_script),
            xml_path,
            cwd=str(project_root),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        a_stdout, a_stderr = await analyzer_proc.communicate()
        report_lines.append(a_stdout.decode("utf-8", errors="replace"))
        if a_stderr:
            report_lines.append(a_stderr.decode("utf-8", errors="replace"))
    else:
        report_lines.append("[Analyzer script not found]\n")

    # Cleanup
    try:
        os.unlink(xml_path)
    except OSError:
        pass

    return "\n".join(report_lines)


async def config_command(args: list[str], context: CommandContext) -> str:
    """Handle /config command."""
    from ..utils.config import get_config_manager, get_global_config, GlobalConfig

    # Handle --test option
    if args and args[0] in ("--test", "-t"):
        if len(args) < 2:
            return "Usage: /config --test <layer1|layer2|capability>"
        layer = args[1].lower()
        if layer == "capability":
            notify_msg = (
                "⏳ Starting model capability benchmark. "
                "This may take 1–3 minutes depending on model speed..."
            )
            print(notify_msg)
            try:
                qe = context.query_engine
                if (
                    qe
                    and hasattr(qe, "config")
                    and qe.config
                    and getattr(qe.config, "on_notify", None)
                ):
                    qe.config.on_notify(
                        "test_start", {"message": notify_msg, "layer": "capability"}
                    )
            except Exception:
                pass

            report = await _run_capability_benchmark()

            complete_msg = "✅ Capability benchmark completed."
            print(complete_msg)
            try:
                qe = context.query_engine
                if (
                    qe
                    and hasattr(qe, "config")
                    and qe.config
                    and getattr(qe.config, "on_notify", None)
                ):
                    qe.config.on_notify(
                        "test_complete", {"message": complete_msg, "layer": "capability"}
                    )
            except Exception:
                pass
            return report

        if layer not in ("layer1", "layer2"):
            return f"Unknown layer: {layer}. Use: layer1, layer2, capability"

        # Notify user about long-running test
        notify_msg = (
            f"⏳ Starting Layer {layer[-1]} E2E test. "
            f"This may take several minutes (typically 3–15 min depending on model speed)..."
        )
        print(notify_msg)  # CLI fallback
        # WebSocket / TUI notify via query_engine if available
        try:
            qe = context.query_engine
            if qe and hasattr(qe, "config") and qe.config and getattr(qe.config, "on_notify", None):
                qe.config.on_notify("test_start", {"message": notify_msg, "layer": layer})
        except Exception:
            pass

        report = await _run_layer_test(layer)

        complete_msg = f"✅ Layer {layer[-1]} test completed."
        print(complete_msg)
        try:
            qe = context.query_engine
            if qe and hasattr(qe, "config") and qe.config and getattr(qe.config, "on_notify", None):
                qe.config.on_notify("test_complete", {"message": complete_msg, "layer": layer})
        except Exception:
            pass

        return report

    if not args:
        # Show all config
        config = get_global_config()
        lines = ["Configuration:", ""]
        for key, value in config.__dict__.items():
            if not key.startswith("_"):
                lines.append(f"  {key}: {value}")
        return "\n".join(lines)

    action = args[0]

    if action == "get":
        if len(args) < 2:
            return "Usage: /config get <key>"

        key = args[1]
        config = get_global_config()
        value = getattr(config, key, None)

        if value is None:
            return f"Unknown key: {key}"

        return f"{key} = {value}"

    elif action == "set":
        if len(args) < 3:
            return "Usage: /config set <key> <value>  or  /config set model_overrides.<model>.<key> <value>"

        key = args[1]
        value = " ".join(args[2:])

        config = get_global_config()

        # Handle nested model_overrides: model_overrides.<model>.<field>
        if key.startswith("model_overrides."):
            parts = key.split(".")
            if len(parts) != 3:
                return "Usage: /config set model_overrides.<model>.<api_key|base_url> <value>"
            _, model_name, field = parts
            if field not in ("api_key", "base_url"):
                return f"Unknown model override field: {field}. Use: api_key, base_url"
            overrides = dict(config.model_overrides)
            model_cfg = dict(overrides.get(model_name, {}))
            model_cfg[field] = value
            overrides[model_name] = model_cfg
            config.model_overrides = overrides
            get_config_manager().save_global_config(config)
            return f"Set model_overrides.{model_name}.{field} = {value[:4]}..."

        if not hasattr(config, key):
            return f"Unknown key: {key}"

        # Parse value
        current = getattr(config, key)
        if isinstance(current, bool):
            new_value = value.lower() in ("true", "1", "yes", "on")
        elif isinstance(current, int):
            new_value = int(value)
        else:
            new_value = value

        setattr(config, key, new_value)
        get_config_manager().save_global_config(config)

        # Hot-reload: sync to running QueryEngine if available
        if context.query_engine and hasattr(context.query_engine, "config"):
            qe_config = context.query_engine.config
            if hasattr(qe_config, key):
                setattr(qe_config, key, new_value)

        return f"Set {key} = {new_value}"

    elif action == "reset":
        default = GlobalConfig()
        get_config_manager().save_global_config(default)

        # Hot-reload: sync to running QueryEngine if available
        if context.query_engine and hasattr(context.query_engine, "config"):
            qe_config = context.query_engine.config
            for key in ("theme", "verbose", "auto_compact", "auto_review", "max_review_iterations"):
                if hasattr(qe_config, key) and hasattr(default, key):
                    setattr(qe_config, key, getattr(default, key))

        return "Configuration reset to defaults"

    else:
        return f"Unknown action: {action}. Use: get, set, reset"


register_command(
    CommandHandler(
        name="config",
        description="Manage configuration. Use /config --test <layer1|layer2|capability> to run tests",
        handler=config_command,
        aliases=["cfg", "settings"],
    )
)
