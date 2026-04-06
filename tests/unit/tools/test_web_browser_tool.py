"""Tests for web browser tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pilotcode.tools.web_browser_tool import (
    WebBrowserInput,
    WebBrowserOutput,
    web_browser_call,
    get_or_create_session,
    close_session,
    navigate,
    click,
    fill,
    get_text,
)


class TestWebBrowserTool:
    """Test web browser tool functionality."""

    @pytest.fixture
    def mock_page(self):
        """Create mock page."""
        page = AsyncMock()
        page.url = "https://example.com"
        page.title = AsyncMock(return_value="Example")
        return page

    @pytest.fixture
    def mock_browser(self):
        """Create mock browser."""
        browser = AsyncMock()
        return browser

    @pytest.mark.asyncio
    async def test_navigate_success(self, mock_page):
        """Test successful navigation."""
        with patch("pilotcode.tools.web_browser_tool._browser_session") as mock_session:
            mock_session.page = mock_page
            mock_session.browser = MagicMock()

            result = await navigate("https://example.com")

            assert result["success"] is True
            assert result["url"] == "https://example.com"
            mock_page.goto.assert_called_once()

    @pytest.mark.asyncio
    async def test_navigate_error(self, mock_page):
        """Test navigation error."""
        with patch("pilotcode.tools.web_browser_tool._browser_session") as mock_session:
            mock_session.page = mock_page
            mock_session.browser = MagicMock()
            mock_page.goto = AsyncMock(side_effect=Exception("Navigation failed"))

            result = await navigate("https://example.com")

            assert result["success"] is False
            assert "Navigation failed" in result["error"]

    @pytest.mark.asyncio
    async def test_click_success(self, mock_page):
        """Test successful click."""
        with patch("pilotcode.tools.web_browser_tool._browser_session") as mock_session:
            mock_session.page = mock_page
            mock_session.browser = MagicMock()

            result = await click("#button")

            assert result["success"] is True
            mock_page.click.assert_called_once_with("#button", timeout=30000)

    @pytest.mark.asyncio
    async def test_fill_success(self, mock_page):
        """Test successful form fill."""
        with patch("pilotcode.tools.web_browser_tool._browser_session") as mock_session:
            mock_session.page = mock_page
            mock_session.browser = MagicMock()

            result = await fill("#input", "test text")

            assert result["success"] is True
            mock_page.fill.assert_called_once_with("#input", "test text", timeout=30000)

    @pytest.mark.asyncio
    async def test_get_text_success(self, mock_page):
        """Test successful text extraction."""
        with patch("pilotcode.tools.web_browser_tool._browser_session") as mock_session:
            mock_session.page = mock_page
            mock_session.browser = MagicMock()
            mock_page.evaluate = AsyncMock(return_value="Page text content")

            result = await get_text()

            assert result["success"] is True
            assert result["content"] == "Page text content"

    @pytest.mark.asyncio
    async def test_get_text_with_selector(self, mock_page):
        """Test text extraction with selector."""
        mock_element = AsyncMock()
        mock_element.text_content = AsyncMock(return_value="Element text")

        with patch("pilotcode.tools.web_browser_tool._browser_session") as mock_session:
            mock_session.page = mock_page
            mock_session.browser = MagicMock()
            mock_page.wait_for_selector = AsyncMock(return_value=mock_element)

            result = await get_text("#element")

            assert result["success"] is True
            assert result["content"] == "Element text"

    @pytest.mark.asyncio
    async def test_web_browser_call_navigate(self):
        """Test web browser call with navigate action."""
        input_data = WebBrowserInput(action="navigate", url="https://example.com")

        with patch("pilotcode.tools.web_browser_tool.HAS_PLAYWRIGHT", True):
            with patch(
                "pilotcode.tools.web_browser_tool.navigate",
                AsyncMock(
                    return_value={
                        "success": True,
                        "url": "https://example.com",
                        "title": "Example",
                        "content": "",
                    }
                ),
            ):
                result = await web_browser_call(input_data, None, None, None, None)

                assert result.data.success is True
                assert result.data.url == "https://example.com"

    @pytest.mark.asyncio
    async def test_web_browser_call_no_playwright(self):
        """Test web browser call without playwright installed."""
        input_data = WebBrowserInput(action="navigate", url="https://example.com")

        with patch("pilotcode.tools.web_browser_tool.HAS_PLAYWRIGHT", False):
            result = await web_browser_call(input_data, None, None, None, None)

            assert result.data.success is False
            assert "playwright is required" in result.error.lower()

    @pytest.mark.asyncio
    async def test_web_browser_call_close(self):
        """Test web browser call with close action."""
        input_data = WebBrowserInput(action="close")

        with patch("pilotcode.tools.web_browser_tool.HAS_PLAYWRIGHT", True):
            with patch("pilotcode.tools.web_browser_tool.close_session", AsyncMock()) as mock_close:
                result = await web_browser_call(input_data, None, None, None, None)

                assert result.data.success is True
                assert "Browser closed" in result.data.content
                mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_web_browser_call_unknown_action(self):
        """Test web browser call with unknown action."""
        input_data = WebBrowserInput(action="unknown_action")

        with patch("pilotcode.tools.web_browser_tool.HAS_PLAYWRIGHT", True):
            result = await web_browser_call(input_data, None, None, None, None)

            assert result.data.success is False
            assert "Unknown action" in result.error


class TestWebBrowserInput:
    """Test WebBrowserInput model."""

    def test_default_values(self):
        """Test default input values."""
        input_data = WebBrowserInput(action="navigate")

        assert input_data.url == ""
        assert input_data.selector == ""
        assert input_data.text == ""
        assert input_data.direction == "down"
        assert input_data.amount == 500
        assert input_data.timeout == 30000
        assert input_data.headless is True
