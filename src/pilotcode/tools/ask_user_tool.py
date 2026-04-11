"""Ask user question tool for interactive input."""

from typing import Any
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class AskUserInput(BaseModel):
    """Input for AskUser tool."""

    question: str = Field(description="The question to ask the user")
    options: list[str] | None = Field(
        default=None, description="Optional list of choices for the user"
    )


class AskUserOutput(BaseModel):
    """Output from AskUser tool."""

    response: str
    question: str


async def ask_user_call(
    input_data: AskUserInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[AskUserOutput]:
    """Ask user a question."""
    # This would normally interact with TUI
    # For now, just return a placeholder
    # In real implementation, this would show a prompt and wait for user input

    from rich.console import Console

    console = Console()

    console.print(f"\n[bold cyan]{input_data.question}[/bold cyan]")

    if input_data.options:
        for i, option in enumerate(input_data.options, 1):
            console.print(f"  {i}. {option}")
        console.print("Enter your choice (number or text):")

    # In actual implementation, this would use prompt_toolkit for async input
    # For now, return a simulated response
    response = input("> ")

    return ToolResult(data=AskUserOutput(response=response, question=input_data.question))


async def ask_user_description(input_data: AskUserInput, options: dict[str, Any]) -> str:
    """Get description for ask user."""
    return f"Asking: {input_data.question[:50]}..."


def render_ask_user_use(input_data: AskUserInput, options: dict[str, Any]) -> str:
    """Render ask user tool use message."""
    return f"❓ {input_data.question[:60]}"


# Create the AskUser tool
AskUserQuestionTool = build_tool(
    name="AskUser",
    description=ask_user_description,
    input_schema=AskUserInput,
    output_schema=AskUserOutput,
    call=ask_user_call,
    aliases=["ask", "question"],
    search_hint="Ask the user a question",
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: False,  # Blocks for user input
    render_tool_use_message=render_ask_user_use,
)

# Register the tool
register_tool(AskUserQuestionTool)
