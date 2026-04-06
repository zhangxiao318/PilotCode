"""Web search tool for searching the internet."""

from typing import Any
from pydantic import BaseModel, Field

from .base import Tool, ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class WebSearchInput(BaseModel):
    """Input for WebSearch tool."""

    query: str = Field(description="Search query")
    limit: int = Field(default=5, description="Maximum number of results")


class WebSearchResult(BaseModel):
    """Single search result."""

    title: str
    url: str
    snippet: str


class WebSearchOutput(BaseModel):
    """Output from WebSearch tool."""

    results: list[WebSearchResult]
    query: str


async def web_search_call(
    input_data: WebSearchInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[WebSearchOutput]:
    """Perform web search."""
    # This is a placeholder - real implementation would use a search API
    # like Google Custom Search, Bing API, or DuckDuckGo

    # Simulated results
    results = [
        WebSearchResult(
            title=f"Result for: {input_data.query}",
            url="https://example.com",
            snippet="This is a simulated search result. In production, integrate with a real search API.",
        )
    ]

    return ToolResult(data=WebSearchOutput(results=results, query=input_data.query))


async def web_search_description(input_data: WebSearchInput, options: dict[str, Any]) -> str:
    """Get description for web search."""
    return f"Searching for: {input_data.query[:50]}"


def render_web_search_use(input_data: WebSearchInput, options: dict[str, Any]) -> str:
    """Render web search tool use message."""
    return f"🌐 Searching: '{input_data.query[:50]}...'"


# Create the WebSearch tool
WebSearchTool = build_tool(
    name="WebSearch",
    description=web_search_description,
    input_schema=WebSearchInput,
    output_schema=WebSearchOutput,
    call=web_search_call,
    aliases=["search", "web", "google"],
    search_hint="Search the web for information",
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
    render_tool_use_message=render_web_search_use,
)

# Register the tool
register_tool(WebSearchTool)
