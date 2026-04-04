"""Cost command implementation."""

from .base import CommandHandler, register_command, CommandContext


# Global cost tracking
_total_tokens = 0
_total_cost = 0.0
_api_calls = 0


def track_usage(tokens: int, cost: float):
    """Track API usage."""
    global _total_tokens, _total_cost, _api_calls
    _total_tokens += tokens
    _total_cost += cost
    _api_calls += 1


async def cost_command(args: list[str], context: CommandContext) -> str:
    """Handle /cost command."""
    global _total_tokens, _total_cost, _api_calls
    
    if args and args[0] == "reset":
        _total_tokens = 0
        _total_cost = 0.0
        _api_calls = 0
        return "Cost tracking reset"
    
    lines = [
        "Usage Statistics:",
        "",
        f"  API calls: {_api_calls}",
        f"  Total tokens: {_total_tokens:,}",
        f"  Total cost: ${_total_cost:.4f}",
        "",
        f"  Average tokens/call: {_total_tokens // max(_api_calls, 1):,}",
        f"  Average cost/call: ${_total_cost / max(_api_calls, 1):.4f}",
    ]
    
    return "\n".join(lines)


register_command(CommandHandler(
    name="cost",
    description="Show usage costs",
    handler=cost_command,
    aliases=["usage", "stats"]
))
