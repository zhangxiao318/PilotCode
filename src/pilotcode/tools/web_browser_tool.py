"""Web Browser tool for interactive web automation.

This tool provides capabilities to:
- Navigate to URLs
- Click elements
- Fill forms
- Extract content
- Take screenshots
- Scroll pages
- Wait for elements
"""

import json
from typing import Any
from dataclasses import dataclass
from pydantic import BaseModel, Field

try:
    from playwright.async_api import async_playwright

    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class WebBrowserInput(BaseModel):
    """Input for WebBrowser tool."""

    action: str = Field(
        description="Action to perform: 'navigate', 'click', 'fill', 'type', 'select', 'screenshot', 'scroll', 'wait', 'get_text', 'get_html', 'evaluate', 'close'"
    )
    url: str = Field(default="", description="URL for navigate action")
    selector: str = Field(default="", description="CSS selector for element interaction")
    text: str = Field(default="", description="Text to type or fill")
    value: str = Field(default="", description="Value for select option")
    direction: str = Field(
        default="down", description="Scroll direction: 'up', 'down', 'left', 'right'"
    )
    amount: int = Field(default=500, description="Scroll amount in pixels")
    wait_for: str = Field(default="", description="Selector to wait for")
    timeout: int = Field(default=30000, description="Timeout in milliseconds")
    headless: bool = Field(default=True, description="Run browser in headless mode")
    script: str = Field(default="", description="JavaScript to evaluate")


class WebBrowserOutput(BaseModel):
    """Output from WebBrowser tool."""

    success: bool
    url: str = ""
    title: str = ""
    content: str = ""
    screenshot: str | None = None  # base64 encoded
    error: str | None = None


@dataclass
class BrowserSession:
    """Browser session state."""

    browser: Any = None
    context: Any = None
    page: Any = None
    current_url: str = ""


# Global browser session
_browser_session: BrowserSession | None = None


async def get_or_create_session(headless: bool = True) -> BrowserSession:
    """Get existing browser session or create new one."""
    global _browser_session

    if _browser_session is None or _browser_session.browser is None:
        if not HAS_PLAYWRIGHT:
            raise ImportError("playwright is required. Install with: pip install playwright")

        p = await async_playwright().start()
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        )
        page = await context.new_page()

        _browser_session = BrowserSession(browser=browser, context=context, page=page)

    return _browser_session


async def close_session() -> None:
    """Close browser session."""
    global _browser_session

    if _browser_session:
        if _browser_session.browser:
            await _browser_session.browser.close()
        _browser_session = None


async def navigate(url: str, timeout: int = 30000) -> dict:
    """Navigate to URL."""
    session = await get_or_create_session()

    try:
        await session.page.goto(url, wait_until="networkidle", timeout=timeout)
        session.current_url = session.page.url

        return {
            "success": True,
            "url": session.page.url,
            "title": await session.page.title(),
            "content": "",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def click(selector: str, timeout: int = 30000) -> dict:
    """Click an element."""
    session = await get_or_create_session()

    try:
        await session.page.click(selector, timeout=timeout)
        return {
            "success": True,
            "url": session.page.url,
            "title": await session.page.title(),
            "content": "",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def fill(selector: str, text: str, timeout: int = 30000) -> dict:
    """Fill a form field."""
    session = await get_or_create_session()

    try:
        await session.page.fill(selector, text, timeout=timeout)
        return {
            "success": True,
            "url": session.page.url,
            "title": await session.page.title(),
            "content": "",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def type_text(selector: str, text: str, timeout: int = 30000) -> dict:
    """Type text with key press simulation."""
    session = await get_or_create_session()

    try:
        await session.page.type(selector, text, timeout=timeout)
        return {
            "success": True,
            "url": session.page.url,
            "title": await session.page.title(),
            "content": "",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def select_option(selector: str, value: str, timeout: int = 30000) -> dict:
    """Select an option from dropdown."""
    session = await get_or_create_session()

    try:
        await session.page.select_option(selector, value, timeout=timeout)
        return {
            "success": True,
            "url": session.page.url,
            "title": await session.page.title(),
            "content": "",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_text(selector: str = "", timeout: int = 30000) -> dict:
    """Get text content from page or element."""
    session = await get_or_create_session()

    try:
        if selector:
            element = await session.page.wait_for_selector(selector, timeout=timeout)
            if element:
                text = await element.text_content()
            else:
                return {"success": False, "error": f"Element not found: {selector}"}
        else:
            # Get body text
            text = await session.page.evaluate("() => document.body.innerText")

        return {
            "success": True,
            "url": session.page.url,
            "title": await session.page.title(),
            "content": text or "",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_html(selector: str = "", timeout: int = 30000) -> dict:
    """Get HTML content from page or element."""
    session = await get_or_create_session()

    try:
        if selector:
            element = await session.page.wait_for_selector(selector, timeout=timeout)
            if element:
                html = await element.inner_html()
            else:
                return {"success": False, "error": f"Element not found: {selector}"}
        else:
            html = await session.page.content()

        return {
            "success": True,
            "url": session.page.url,
            "title": await session.page.title(),
            "content": html[:50000],  # Limit HTML size
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def scroll(direction: str = "down", amount: int = 500) -> dict:
    """Scroll the page."""
    session = await get_or_create_session()

    try:
        if direction == "down":
            await session.page.evaluate(f"() => window.scrollBy(0, {amount})")
        elif direction == "up":
            await session.page.evaluate(f"() => window.scrollBy(0, -{amount})")
        elif direction == "left":
            await session.page.evaluate(f"() => window.scrollBy(-{amount}, 0)")
        elif direction == "right":
            await session.page.evaluate(f"() => window.scrollBy({amount}, 0)")

        return {
            "success": True,
            "url": session.page.url,
            "title": await session.page.title(),
            "content": "",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def wait_for(selector: str, timeout: int = 30000) -> dict:
    """Wait for an element to appear."""
    session = await get_or_create_session()

    try:
        await session.page.wait_for_selector(selector, timeout=timeout)
        return {
            "success": True,
            "url": session.page.url,
            "title": await session.page.title(),
            "content": f"Element found: {selector}",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def screenshot(full_page: bool = False) -> dict:
    """Take a screenshot."""
    session = await get_or_create_session()

    try:
        import base64

        screenshot_bytes = await session.page.screenshot(full_page=full_page)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode()

        return {
            "success": True,
            "url": session.page.url,
            "title": await session.page.title(),
            "content": "Screenshot captured",
            "screenshot": screenshot_b64,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def evaluate_javascript(script: str) -> dict:
    """Execute JavaScript on the page."""
    session = await get_or_create_session()

    try:
        result = await session.page.evaluate(script)

        # Convert result to string if needed
        if result is not None:
            content = json.dumps(result, default=str, indent=2)
        else:
            content = "null"

        return {
            "success": True,
            "url": session.page.url,
            "title": await session.page.title(),
            "content": content[:10000],  # Limit result size
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def web_browser_call(
    input_data: WebBrowserInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[WebBrowserOutput]:
    """Execute web browser action."""
    if not HAS_PLAYWRIGHT:
        return ToolResult(
            data=WebBrowserOutput(success=False),
            error="playwright is required. Install with: pip install playwright && playwright install chromium",
        )

    try:
        if input_data.action == "navigate":
            result = await navigate(input_data.url, input_data.timeout)
        elif input_data.action == "click":
            result = await click(input_data.selector, input_data.timeout)
        elif input_data.action == "fill":
            result = await fill(input_data.selector, input_data.text, input_data.timeout)
        elif input_data.action == "type":
            result = await type_text(input_data.selector, input_data.text, input_data.timeout)
        elif input_data.action == "select":
            result = await select_option(input_data.selector, input_data.value, input_data.timeout)
        elif input_data.action == "get_text":
            result = await get_text(input_data.selector, input_data.timeout)
        elif input_data.action == "get_html":
            result = await get_html(input_data.selector, input_data.timeout)
        elif input_data.action == "scroll":
            result = await scroll(input_data.direction, input_data.amount)
        elif input_data.action == "wait":
            result = await wait_for(input_data.wait_for or input_data.selector, input_data.timeout)
        elif input_data.action == "screenshot":
            result = await screenshot()
        elif input_data.action == "evaluate":
            result = await evaluate_javascript(input_data.script)
        elif input_data.action == "close":
            await close_session()
            result = {"success": True, "url": "", "title": "", "content": "Browser closed"}
        else:
            return ToolResult(
                data=WebBrowserOutput(success=False), error=f"Unknown action: {input_data.action}"
            )

        return ToolResult(
            data=WebBrowserOutput(
                success=result.get("success", False),
                url=result.get("url", ""),
                title=result.get("title", ""),
                content=result.get("content", ""),
                screenshot=result.get("screenshot"),
                error=result.get("error"),
            )
        )

    except Exception as e:
        return ToolResult(data=WebBrowserOutput(success=False), error=str(e))


async def web_browser_description(input_data: WebBrowserInput, options: dict[str, Any]) -> str:
    """Get description for WebBrowser tool."""
    action_descriptions = {
        "navigate": f"Navigate to {input_data.url}",
        "click": f"Click element: {input_data.selector}",
        "fill": f"Fill form: {input_data.selector}",
        "type": f"Type text: {input_data.selector}",
        "select": f"Select option: {input_data.selector}",
        "get_text": f"Extract text from {input_data.selector or 'page'}",
        "get_html": f"Extract HTML from {input_data.selector or 'page'}",
        "scroll": f"Scroll {input_data.direction} by {input_data.amount}px",
        "wait": f"Wait for element: {input_data.wait_for or input_data.selector}",
        "screenshot": "Take screenshot",
        "evaluate": "Execute JavaScript",
        "close": "Close browser",
    }

    return action_descriptions.get(input_data.action, f"WebBrowser: {input_data.action}")


# Create the WebBrowser tool
WebBrowserTool = build_tool(
    name="WebBrowser",
    description=web_browser_description,
    input_schema=WebBrowserInput,
    output_schema=WebBrowserOutput,
    call=web_browser_call,
    aliases=["browser", "web_automation", "playwright"],
    search_hint="Automate web browser for interactive websites",
    is_read_only=lambda x: (
        x.action in ["get_text", "get_html", "screenshot", "evaluate"] if x else True
    ),
    is_concurrency_safe=lambda _: False,
)


register_tool(WebBrowserTool)
