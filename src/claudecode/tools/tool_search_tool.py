"""ToolSearch tool for finding available tools."""

from typing import Any
from pydantic import BaseModel, Field

from .base import Tool, ToolResult, ToolUseContext, build_tool
from .registry import register_tool, get_all_tools


class ToolSearchInput(BaseModel):
    """Input for ToolSearch tool."""
    query: str = Field(description="Search query for tools")
    limit: int = Field(default=5, description="Maximum results")


class ToolSearchOutput(BaseModel):
    """Output from ToolSearch tool."""
    results: list[dict]
    total: int


async def tool_search_call(
    input_data: ToolSearchInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any
) -> ToolResult[ToolSearchOutput]:
    """Search for tools."""
    query = input_data.query.lower()
    tools = get_all_tools()
    
    matches = []
    for tool in tools:
        score = 0
        
        # Name match
        if query in tool.name.lower():
            score += 10
        
        # Alias match
        for alias in tool.aliases:
            if query in alias.lower():
                score += 5
        
        # Search hint match
        if query in tool.search_hint.lower():
            score += 3
        
        if score > 0:
            matches.append((score, tool))
    
    # Sort by score
    matches.sort(key=lambda x: x[0], reverse=True)
    matches = matches[:input_data.limit]
    
    results = [
        {
            "name": tool.name,
            "aliases": tool.aliases,
            "description": tool.search_hint,
            "score": score
        }
        for score, tool in matches
    ]
    
    return ToolResult(data=ToolSearchOutput(
        results=results,
        total=len(results)
    ))


async def tool_search_description(input_data: ToolSearchInput, options: dict[str, Any]) -> str:
    """Get description for tool search."""
    return f"Searching for tools: {input_data.query}"


ToolSearchTool = build_tool(
    name="ToolSearch",
    description=tool_search_description,
    input_schema=ToolSearchInput,
    output_schema=ToolSearchOutput,
    call=tool_search_call,
    aliases=["tool_search", "find_tool"],
    search_hint="Search for available tools",
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
)

register_tool(ToolSearchTool)
