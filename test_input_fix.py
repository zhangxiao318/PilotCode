#!/usr/bin/env python3
"""Automated test for input display and submission fix."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import pytest
from textual.pilot import Pilot
from textual.app import App, ComposeResult
from textual.widgets import Static

from pilotcode.tui_v2.components.prompt.input import PromptInput, PromptWithMode


class TestInputApp(App):
    """Test app for input widget."""
    
    CSS = """
    Screen { align: center middle; }
    #result { height: auto; margin: 1; }
    """
    
    def __init__(self):
        super().__init__()
        self.submitted_text = None
        self.input_widget = None
        self.result = None
    
    def compose(self) -> ComposeResult:
        yield Static("Test: Type 'hello' and press Enter", id="instruction")
        self.input_widget = PromptInput()
        yield self.input_widget
        self.result = Static("Result: ", id="result")
        yield self.result
    
    def on_mount(self):
        self.input_widget.focus()
    
    def on_prompt_input_submitted(self, event: PromptInput.Submitted):
        self.submitted_text = event.text
        self.result.update(f"Result: {event.text!r}")


class TestPromptWithModeApp(App):
    """Test app for PromptWithMode widget."""
    
    CSS = """
    Screen { align: center middle; }
    """
    
    def __init__(self):
        super().__init__()
        self.submitted_text = None
        self.prompt = None
    
    def compose(self) -> ComposeResult:
        yield Static("Test PromptWithMode")
        self.prompt = PromptWithMode()
        yield self.prompt
    
    def on_mount(self):
        self.prompt.prompt_input.focus()
    
    def on_prompt_with_mode_submitted(self, event: PromptWithMode.Submitted):
        self.submitted_text = event.text


@pytest.mark.asyncio
async def test_input_creation():
    """Test that PromptInput can be created."""
    app = TestInputApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.input_widget is not None
        print("✅ PromptInput created successfully")


@pytest.mark.asyncio
async def test_input_typing():
    """Test that typing updates the input text."""
    app = TestInputApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        
        # Type some text
        await pilot.press(*list("hello"))
        await pilot.pause()
        
        # Check text was entered
        assert app.input_widget.text == "hello", f"Expected 'hello', got {app.input_widget.text!r}"
        print("✅ Typing 'hello' works")


@pytest.mark.asyncio
async def test_input_submit():
    """Test that Enter submits the input."""
    app = TestInputApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        
        # Type and submit
        await pilot.press(*list("test message"))
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        
        # Check submission
        assert app.submitted_text == "test message", f"Expected 'test message', got {app.submitted_text!r}"
        print("✅ Enter key submission works")


@pytest.mark.asyncio
async def test_shift_enter_newline():
    """Test that Shift+Enter adds newline."""
    app = TestInputApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        
        # Type first line
        await pilot.press(*list("line1"))
        await pilot.pause()
        
        # Press Shift+Enter for newline
        await pilot.press("shift+enter")
        await pilot.pause()
        
        # Type second line
        await pilot.press(*list("line2"))
        await pilot.pause()
        
        # Check multiline text
        assert "line1" in app.input_widget.text
        assert "line2" in app.input_widget.text
        print("✅ Shift+Enter newline works")


@pytest.mark.asyncio
async def test_prompt_with_mode():
    """Test PromptWithMode widget."""
    app = TestPromptWithModeApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        
        # Type and submit
        await pilot.press(*list("@file.txt /help"))
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        
        assert app.submitted_text == "@file.txt /help"
        print("✅ PromptWithMode with syntax elements works")


def run_tests():
    """Run all tests and report results."""
    tests = [
        ("Input Creation", test_input_creation),
        ("Input Typing", test_input_typing),
        ("Input Submit", test_input_submit),
        ("Shift+Enter Newline", test_shift_enter_newline),
        ("PromptWithMode", test_prompt_with_mode),
    ]
    
    print("=" * 60)
    print("Running Input Fix Tests")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            print(f"\n🧪 Testing: {name}...")
            asyncio.run(test_func())
            passed += 1
        except Exception as e:
            print(f"❌ FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
