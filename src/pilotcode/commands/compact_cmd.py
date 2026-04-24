"""Compact command implementation."""

from .base import CommandHandler, register_command, CommandContext


async def compact_command(args: list[str], context: CommandContext) -> str:
    """Handle /compact command."""
    if context.query_engine is None:
        return "Query engine not available."

    qe = context.query_engine
    from ..utils.models_config import get_model_context_window

    # Stats before (use count_tokens for accuracy, includes system prompt + tools)
    msg_before = len(qe.messages)
    tokens_before = qe.count_tokens()

    if msg_before == 0:
        return "No messages to compact."

    ctx_window = get_model_context_window()
    before_pct = min(tokens_before * 100 // ctx_window, 999)

    # Run full compaction chain (intelligent -> simple -> emergency)
    compacted = qe.auto_compact_if_needed()

    if not compacted:
        return (
            f"No compaction needed or cooldown active.\n"
            f"  Messages: {msg_before} | Tokens: {tokens_before}/{ctx_window} ({before_pct}%)"
        )

    # Stats after
    msg_after = len(qe.messages)
    tokens_after = qe.count_tokens()
    after_pct = min(tokens_after * 100 // ctx_window, 999)

    lines = [
        "Context compacted:",
        f"  Messages:  {msg_before} -> {msg_after}",
        f"  Tokens:    {tokens_before} -> {tokens_after} ({tokens_before - tokens_after} saved)",
        f"  Usage:     {before_pct}% -> {after_pct}%",
    ]
    if after_pct >= 80:
        lines.append("  ⚠️  Still above 80% — may compress again soon")

    return "\n".join(lines)


register_command(
    CommandHandler(
        name="compact", description="Compact conversation history", handler=compact_command
    )
)
