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
    from ..utils.models_config import get_model_info, get_model_context_window

    config = get_global_config()
    lines.append(f"Model: {config.default_model}")

    # Model capability info
    model_info = get_model_info(config.default_model)
    if model_info:
        ctx = model_info.context_window
        ctx_str = f"{ctx // 1000}K" if ctx >= 1000 else str(ctx)
        max_tok = model_info.max_tokens
        max_tok_str = f"{max_tok // 1000}K" if max_tok >= 1000 else str(max_tok)
        lines.append(f"  Context window: {ctx_str}")
        lines.append(f"  Max output:     {max_tok_str}")
        lines.append(f"  Tools:          {'Yes' if model_info.supports_tools else 'No'}")
        lines.append(f"  Vision:         {'Yes' if model_info.supports_vision else 'No'}")

    lines.append(f"Theme: {config.theme}")

    # QueryEngine context_window (for debugging auto-compact threshold)
    if context.query_engine is not None:
        qe = context.query_engine
        qe_ctx = qe.config.context_window
        try:
            qe_threshold = (
                int(qe_ctx * 0.8) if isinstance(qe_ctx, (int, float)) and qe_ctx > 0 else "auto"
            )
        except (TypeError, ValueError):
            qe_threshold = "auto"
        lines.append(f"QE context_window: {qe_ctx}  (compact threshold: {qe_threshold})")

    # Conversation context stats
    if context.query_engine is not None:
        qe = context.query_engine
        msg_count = len(qe.messages)
        from ..services.token_estimation import estimate_tokens

        total_tokens = sum(estimate_tokens(str(getattr(m, "content", ""))) for m in qe.messages)
        ctx_window = get_model_context_window()
        used_pct = total_tokens * 100 // ctx_window
        lines.append("")
        lines.append("Conversation Context:")
        lines.append(f"  Messages:   {msg_count}")
        lines.append(f"  Tokens:     {total_tokens} / {ctx_window} ({used_pct}%)")
        lines.append(f"  Remaining:  {ctx_window - total_tokens}")
        # Budget bar
        bar_len = 20
        filled = int(used_pct / 100 * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        lines.append(f"  [{bar}] {used_pct}%")
        if used_pct >= 80:
            lines.append(f"  ⚠️  Above 80% — auto-compression active")
        elif used_pct >= 60:
            lines.append(f"  ⚡ Above 60% — approaching limit")

    return "\n".join(lines)


register_command(
    CommandHandler(
        name="status", description="Show status information", handler=status_command, aliases=["st"]
    )
)
