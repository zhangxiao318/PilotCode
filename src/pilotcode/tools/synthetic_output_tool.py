"""SyntheticOutput tool for generating synthetic/tool-generated content."""

from typing import Any
from pydantic import BaseModel, Field

from .base import Tool, ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class SyntheticOutputInput(BaseModel):
    """Input for SyntheticOutput tool."""

    content_type: str = Field(description="Type: code, text, json, markdown")
    description: str = Field(description="Description of what to generate")
    context: dict = Field(default_factory=dict, description="Additional context")


class SyntheticOutputOutput(BaseModel):
    """Output from SyntheticOutput tool."""

    content_type: str
    content: str
    generated: bool


async def synthetic_output_call(
    input_data: SyntheticOutputInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[SyntheticOutputOutput]:
    """Generate synthetic output."""

    # This would typically call an LLM to generate content
    # For now, return a placeholder/template

    content_type = input_data.content_type
    description = input_data.description

    if content_type == "code":
        content = f"""# {description}
# TODO: Implement this functionality

def main():
    pass

if __name__ == "__main__":
    main()
"""
    elif content_type == "json":
        content = f"""{{
  "description": "{description}",
  "status": "generated",
  "timestamp": "2024-01-01T00:00:00"
}}"""
    elif content_type == "markdown":
        content = f"""# {description}

## Overview

This is a synthetic output generated based on the description.

## Details

- Type: {content_type}
- Generated: Yes

## Content

Your content would be generated here based on the context and description.
"""
    else:
        content = f"Synthetic output for: {description}\n\nThis content was generated based on your request."

    return ToolResult(
        data=SyntheticOutputOutput(content_type=content_type, content=content, generated=True)
    )


SyntheticOutputTool = build_tool(
    name="SyntheticOutput",
    description=lambda x, o: f"Generate synthetic {x.content_type}: {x.description[:30]}...",
    input_schema=SyntheticOutputInput,
    output_schema=SyntheticOutputOutput,
    call=synthetic_output_call,
    aliases=["synthetic", "generate"],
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
)

register_tool(SyntheticOutputTool)
