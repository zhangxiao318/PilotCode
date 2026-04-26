"""Web search tool for searching the internet via Baidu."""

import asyncio
from typing import Any
from pydantic import BaseModel, Field

from .base import Tool, ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class WebSearchInput(BaseModel):
    """Input for WebSearch tool."""

    query: str = Field(description="Search query")
    limit: int = Field(default=5, description="Maximum number of results", ge=1, le=20)


class WebSearchResult(BaseModel):
    """Single search result."""

    title: str
    url: str
    snippet: str


class WebSearchOutput(BaseModel):
    """Output from WebSearch tool."""

    results: list[WebSearchResult]
    query: str


def _clean_snippet(text: str) -> str:
    """Collapse excessive whitespace in snippet."""
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return " ".join(lines)


def _do_baidu_search(query: str, limit: int) -> list[WebSearchResult]:
    """Synchronous wrapper around baidusearch."""
    try:
        from baidusearch.baidusearch import search as baidu_search
    except ImportError as exc:
        raise RuntimeError("baidusearch is not installed. Run: pip install baidusearch") from exc

    raw_results = baidu_search(query, num_results=limit)
    if not raw_results:
        return []

    results: list[WebSearchResult] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        title = item.get("title", "")
        url = item.get("url", "")
        abstract = item.get("abstract", "")
        # Skip items that look like Baidu anti-bot / verification pages
        if not title or not url or "安全验证" in title or "verify" in url.lower():
            continue
        results.append(
            WebSearchResult(
                title=_clean_snippet(title),
                url=url,
                snippet=_clean_snippet(abstract),
            )
        )
    return results


def _format_for_assistant(query: str, results: list[WebSearchResult]) -> str:
    """Format search results into a plain-text summary for the LLM."""
    if not results:
        return f"No results found for query: {query}"
    lines = [f"Search results for '{query}':", ""]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.title}")
        lines.append(f"   URL: {r.url}")
        if r.snippet:
            lines.append(f"   {r.snippet}")
        lines.append("")
    return "\n".join(lines)


async def web_search_call(
    input_data: WebSearchInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[WebSearchOutput]:
    """Perform web search via Baidu."""
    query = input_data.query.strip()
    if not query:
        return ToolResult(
            data=WebSearchOutput(results=[], query=""),
            error="Search query cannot be empty.",
        )

    try:
        results = await asyncio.to_thread(_do_baidu_search, query, input_data.limit)
    except Exception as exc:
        return ToolResult(
            data=WebSearchOutput(results=[], query=query),
            error=f"Web search failed: {exc}",
        )

    output = WebSearchOutput(results=results, query=query)
    assistant_text = _format_for_assistant(query, results)
    return ToolResult(data=output, output_for_assistant=assistant_text)


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
    max_result_size_chars=30_000,
)

# Register the tool
register_tool(WebSearchTool)
