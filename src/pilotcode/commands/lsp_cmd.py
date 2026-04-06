"""LSP command implementation."""

from .base import CommandHandler, register_command, CommandContext


async def lsp_command(args: list[str], context: CommandContext) -> str:
    """Handle /lsp command."""
    if not args:
        return "LSP Servers:\n\nNo active LSP connections.\n\nUse '/lsp start <language>' to start one."

    action = args[0]

    if action == "start":
        if len(args) < 2:
            return "Usage: /lsp start <language>\n\nSupported: python, typescript, rust, go"

        language = args[1]
        return f"Would start LSP server for: {language}\n(Not fully implemented)"

    elif action == "stop":
        return "Would stop LSP server\n(Not fully implemented)"

    elif action == "status":
        return "LSP Status:\n\nNo active connections."

    else:
        return f"Unknown action: {action}. Use: start, stop, status"


register_command(CommandHandler(name="lsp", description="Manage LSP servers", handler=lsp_command))
