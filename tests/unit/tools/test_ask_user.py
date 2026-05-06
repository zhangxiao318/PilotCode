"""Tests for AskUser tool async callback integration."""

import asyncio
import pytest
from pilotcode.tools.ask_user_tool import (
    AskUserInput,
    AskUserOutput,
    ask_user_call,
)
from pilotcode.tools.base import ToolUseContext


class FakeContext:
    """Minimal fake context for ask_user_call."""

    def __init__(self, response: str = "fake answer"):
        self.response = response

    async def ask_user_callback(self, question: str, options: list[str] | None = None) -> str:
        return self.response


@pytest.mark.asyncio
async def test_ask_user_uses_callback_when_available():
    """AskUser should use async callback instead of blocking input()."""

    async def mock_callback(question: str, options: list[str] | None = None) -> str:
        assert question == "What is your favorite color?"
        assert options == ["Red", "Green", "Blue"]
        return "Green"

    ctx = ToolUseContext(ask_user_callback=mock_callback)
    input_data = AskUserInput(
        question="What is your favorite color?",
        options=["Red", "Green", "Blue"],
    )

    result = await ask_user_call(
        input_data=input_data,
        context=ctx,
        can_use_tool=None,
        parent_message=None,
        on_progress=None,
    )

    assert not result.is_error
    assert result.data.response == "Green"
    assert result.data.question == "What is your favorite color?"


@pytest.mark.asyncio
async def test_ask_user_callback_no_options():
    """AskUser callback should work without options."""

    async def mock_callback(question: str, options: list[str] | None = None) -> str:
        assert question == "What is your name?"
        assert options is None
        return "Alice"

    ctx = ToolUseContext(ask_user_callback=mock_callback)
    input_data = AskUserInput(question="What is your name?")

    result = await ask_user_call(
        input_data=input_data,
        context=ctx,
        can_use_tool=None,
        parent_message=None,
        on_progress=None,
    )

    assert result.data.response == "Alice"


@pytest.mark.asyncio
async def test_ask_user_no_callback_returns_result():
    """AskUser without callback still produces a result (uses fallback)."""
    # This test verifies the code path exists; we mock stdin to avoid blocking
    import unittest.mock

    ctx = ToolUseContext()  # No ask_user_callback
    input_data = AskUserInput(question="Test?")

    with unittest.mock.patch("builtins.input", return_value="manual answer"):
        result = await ask_user_call(
            input_data=input_data,
            context=ctx,
            can_use_tool=None,
            parent_message=None,
            on_progress=None,
        )

    assert result.data.response == "manual answer"
