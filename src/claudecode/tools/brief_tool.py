"""Brief tool for summarizing content."""

from typing import Any
from pydantic import BaseModel, Field

from .base import Tool, ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class BriefInput(BaseModel):
    """Input for Brief tool."""
    content: str = Field(description="Content to summarize")
    max_length: int = Field(default=200, description="Maximum summary length")
    format: str = Field(default="text", description="Output format: text, bullet, or outline")


class BriefOutput(BaseModel):
    """Output from Brief tool."""
    summary: str
    original_length: int
    summary_length: int
    compression_ratio: float


async def brief_call(
    input_data: BriefInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any
) -> ToolResult[BriefOutput]:
    """Generate brief summary."""
    content = input_data.content
    
    # Simple summarization (in real implementation, would use LLM)
    sentences = content.split('.')
    
    if input_data.format == "bullet":
        # Take first sentence of each paragraph as bullet
        paragraphs = content.split('\n\n')
        bullets = []
        for p in paragraphs[:5]:
            first_sentence = p.split('.')[0].strip()
            if first_sentence:
                bullets.append(f"• {first_sentence}")
        summary = '\n'.join(bullets)
    elif input_data.format == "outline":
        # Simple outline
        lines = content.split('\n')[:5]
        summary = '\n'.join(f"  - {line[:50]}..." for line in lines if line.strip())
    else:
        # Text summary - take first few sentences
        summary = '. '.join(sentences[:3]) + '.'
    
    # Truncate if too long
    if len(summary) > input_data.max_length:
        summary = summary[:input_data.max_length].rsplit(' ', 1)[0] + '...'
    
    return ToolResult(data=BriefOutput(
        summary=summary,
        original_length=len(content),
        summary_length=len(summary),
        compression_ratio=len(summary) / max(len(content), 1)
    ))


async def brief_description(input_data: BriefInput, options: dict[str, Any]) -> str:
    """Get description for brief tool."""
    return f"Creating {input_data.format} summary"


BriefTool = build_tool(
    name="Brief",
    description=brief_description,
    input_schema=BriefInput,
    output_schema=BriefOutput,
    call=brief_call,
    aliases=["summarize", "summary"],
    search_hint="Create a brief summary of content",
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
)

register_tool(BriefTool)
