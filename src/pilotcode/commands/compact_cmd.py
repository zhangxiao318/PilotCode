"""Compact command implementation."""

from .base import CommandHandler, register_command, CommandContext


async def compact_command(args: list[str], context: CommandContext) -> str:
    """Handle /compact command."""
    if context.query_engine is None:
        return "Query engine not available."

    qe = context.query_engine

    from ..services.token_estimation import estimate_tokens
    from ..services.context_compression import get_context_compressor
    from ..utils.models_config import get_model_context_window

    # Stats before
    msg_before = len(qe.messages)
    tokens_before = sum(
        estimate_tokens(str(getattr(m, "content", ""))) for m in qe.messages
    )

    if msg_before == 0:
        return "No messages to compact."

    ctx_window = get_model_context_window()
    before_pct = tokens_before * 100 // ctx_window

    # Run compaction
    compressor = get_context_compressor()
    compressed = compressor.simple_compact(qe.messages, keep_recent=10)
    removed = msg_before - len(compressed)

    if removed == 0:
        return (
            f"No compaction possible.\n"
            f"  Messages: {msg_before} | Tokens: {tokens_before}/{ctx_window} ({before_pct}%)"
        )

    qe.messages = compressed

    # Stats after
    msg_after = len(qe.messages)
    tokens_after = sum(
        estimate_tokens(str(getattr(m, "content", ""))) for m in qe.messages
    )
    after_pct = tokens_after * 100 // ctx_window

    lines = [
        "Context compacted:",
        f"  Messages:  {msg_before} -> {msg_after} ({removed} removed)",
        f"  Tokens:    {tokens_before} -> {tokens_after} ({tokens_before - tokens_after} saved)",
        f"  Usage:     {before_pct}% -> {after_pct}%",
    ]
    if after_pct >= 80:
        lines.append(f"  ⚠️  Still above 80% — may compress again soon")

    return "\n".join(lines)


register_command(
    CommandHandler(
        name="compact", description="Compact conversation history", handler=compact_command
    )
)
