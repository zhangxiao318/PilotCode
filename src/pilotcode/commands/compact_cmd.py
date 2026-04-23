"""Compact command implementation."""

from .base import CommandHandler, register_command, CommandContext


async def compact_command(args: list[str], context: CommandContext) -> str:
    """Handle /compact command."""
    if context.query_engine is None:
        return "Query engine not available."

    qe = context.query_engine

    from ..services.token_estimation import estimate_tokens
    from ..utils.models_config import get_model_context_window

    # Stats before
    msg_before = len(qe.messages)
    tokens_before = sum(estimate_tokens(str(getattr(m, "content", ""))) for m in qe.messages)

    if msg_before == 0:
        return "No messages to compact."

    ctx_window = get_model_context_window()
    before_pct = tokens_before * 100 // ctx_window

    # Run intelligent compaction
    result = qe.intelligent_compact()

    if not result.get("compacted", False):
        return (
            f"No compaction needed.\n"
            f"  Messages: {msg_before} | Tokens: {tokens_before}/{ctx_window} ({before_pct}%)"
        )

    # Stats after
    msg_after = len(qe.messages)
    tokens_after = sum(estimate_tokens(str(getattr(m, "content", ""))) for m in qe.messages)
    after_pct = tokens_after * 100 // ctx_window

    lines = [
        "Context compacted:",
        f"  Messages:  {msg_before} -> {msg_after}",
        f"  Tokens:    {tokens_before} -> {tokens_after} ({tokens_before - tokens_after} saved)",
        f"  Usage:     {before_pct}% -> {after_pct}%",
    ]
    if result.get("tool_results_cleared", 0) > 0:
        lines.append(f"  🧹 Cleared {result['tool_results_cleared']} old tool results")
    if after_pct >= 80:
        lines.append("  ⚠️  Still above 80% — may compress again soon")

    return "\n".join(lines)


register_command(
    CommandHandler(
        name="compact", description="Compact conversation history", handler=compact_command
    )
)
