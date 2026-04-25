"""Web fetch tool for retrieving web page content."""

import httpx
from typing import Any
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class WebFetchInput(BaseModel):
    """Input for WebFetch tool."""

    url: str = Field(description="URL to fetch")
    max_length: int = Field(default=50000, description="Maximum content length")


class WebFetchOutput(BaseModel):
    """Output from WebFetch tool."""

    url: str
    content: str
    title: str | None = None
    status_code: int


async def web_fetch_call(
    input_data: WebFetchInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[WebFetchOutput]:
    """Fetch web page content."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        async with httpx.AsyncClient(
            timeout=30.0, follow_redirects=True, headers=headers
        ) as client:
            response = await client.get(input_data.url)
            response.raise_for_status()

            # Get content
            content = response.text

            # Extract title (simple regex)
            import re

            title_match = re.search(
                r"<title[^>]*>(.*?)</title>", content, re.IGNORECASE | re.DOTALL
            )
            title = title_match.group(1).strip() if title_match else None

            # Strip HTML tags for plain text
            # Simple HTML tag removal
            text_content = re.sub(r"<[^>]+>", " ", content)
            text_content = re.sub(r"\s+", " ", text_content).strip()

            # Truncate if too long
            if len(text_content) > input_data.max_length:
                text_content = text_content[: input_data.max_length] + "\n... [content truncated]"

            return ToolResult(
                data=WebFetchOutput(
                    url=str(response.url),
                    content=text_content,
                    title=title,
                    status_code=response.status_code,
                )
            )
    except httpx.HTTPError as e:
        # Not all HTTPError exceptions have a response (e.g., ConnectError)
        status_code = 0
        if hasattr(e, "response") and e.response is not None:
            status_code = getattr(e.response, "status_code", 0)
        return ToolResult(
            data=WebFetchOutput(
                url=input_data.url, content="", title=None, status_code=status_code
            ),
            error=f"HTTP error: {str(e)}",
        )
    except Exception as e:
        return ToolResult(
            data=WebFetchOutput(url=input_data.url, content="", title=None, status_code=0),
            error=str(e),
        )


async def web_fetch_description(input_data: WebFetchInput, options: dict[str, Any]) -> str:
    """Get description for web fetch."""
    return f"Fetching: {input_data.url[:60]}"


def render_web_fetch_use(input_data: WebFetchInput, options: dict[str, Any]) -> str:
    """Render web fetch tool use message."""
    url = input_data.url[:50] + "..." if len(input_data.url) > 50 else input_data.url
    return f"🌐 Fetching: {url}"


# Create the WebFetch tool
WebFetchTool = build_tool(
    name="WebFetch",
    description=web_fetch_description,
    input_schema=WebFetchInput,
    output_schema=WebFetchOutput,
    call=web_fetch_call,
    aliases=["fetch", "curl", "wget"],
    search_hint="Fetch content from a URL",
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
    render_tool_use_message=render_web_fetch_use,
    max_result_size_chars=50_000,
)

# Register the tool
register_tool(WebFetchTool)
