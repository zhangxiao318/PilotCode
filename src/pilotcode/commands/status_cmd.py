"""Status command implementation."""

import subprocess
from datetime import datetime
from .base import CommandHandler, register_command, CommandContext


async def status_command(args: list[str], context: CommandContext) -> str:
    """Handle /status command."""
    lines = ["PilotCode Status", "=" * 40, ""]

    # Git status
    try:
        result = subprocess.run(
            ["git", "status", "-sb"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=context.cwd,
        )

        if result.returncode == 0:
            lines.append("Git:")
            for line in result.stdout.strip().split("\n")[:5]:
                lines.append(f"  {line}")
            lines.append("")
    except Exception:
        pass

    # Current directory
    lines.append(f"Working directory: {context.cwd}")
    lines.append(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Configuration
    from ..utils.config import get_global_config
    from ..utils.models_config import get_model_info, get_model_limits

    config = get_global_config()
    lines.append(f"Model: {config.default_model}")

    # Model capability info (OpenCode-style: probe backend for real limits)
    limits = get_model_limits()
    ctx = limits.get("context_window", 128_000)
    max_tok = limits.get("max_tokens", 4096)
    ctx_str = f"{ctx // 1000}K" if ctx >= 1000 else str(ctx)
    max_tok_str = f"{max_tok // 1000}K" if max_tok >= 1000 else str(max_tok)
    usable = max(1, ctx - min(max_tok, 32_000))
    lines.append(f"  Context window: {ctx_str}  (probed)")
    lines.append(f"  Max output:     {max_tok_str}")
    lines.append(f"  Usable input:   {usable}")

    model_info = get_model_info(config.default_model)
    if model_info:
        lines.append(f"  Tools:          {'Yes' if model_info.supports_tools else 'No'}")
        lines.append(f"  Vision:         {'Yes' if model_info.supports_vision else 'No'}")

    lines.append(f"Theme: {config.theme}")

    # QueryEngine context_window (for debugging auto-compact threshold)
    if context.query_engine is not None:
        qe = context.query_engine
        qe_ctx = qe.config.context_window
        qe_usable = qe._usable_context
        qe_threshold = int(qe_usable * 0.85) if qe_usable > 0 else "auto"
        lines.append(f"QE context_window: {qe_ctx}  (usable={qe_usable}, threshold={qe_threshold})")

    # Conversation context stats
    if context.query_engine is not None:
        qe = context.query_engine
        msg_count = len(qe.messages)
        from ..services.token_estimation import estimate_tokens

        total_tokens = sum(estimate_tokens(str(getattr(m, "content", ""))) for m in qe.messages)
        ctx_window = ctx
        used_pct = total_tokens * 100 // ctx_window if ctx_window > 0 else 0
        usable_pct = total_tokens * 100 // usable if usable > 0 else 0
        lines.append("")
        lines.append("Conversation Context:")
        lines.append(f"  Messages:   {msg_count}")
        lines.append(f"  Tokens:     {total_tokens} / {ctx_window} ({used_pct}%)")
        lines.append(f"  Usable:     {usable}  ({usable_pct}% used)")
        lines.append(f"  Remaining:  {ctx_window - total_tokens}")
        # Budget bar
        bar_len = 20
        filled = int(usable_pct / 100 * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        lines.append(f"  [{bar}] {usable_pct}%")
        if usable_pct >= 85:
            lines.append("  ⚠️  Above 85% usable — auto-compression active")
        elif usable_pct >= 60:
            lines.append("  ⚡ Above 60% — approaching limit")

    return "\n".join(lines)


register_command(
    CommandHandler(
        name="status", description="Show status information", handler=status_command, aliases=["st"]
    )
)
