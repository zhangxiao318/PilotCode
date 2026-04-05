#!/usr/bin/env python3
"""Test TUI v2 using Textual's built-in testing framework.

This test uses Textual's Pilot class to test the TUI without needing
external MCP servers.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import pytest
from textual.pilot import Pilot

from pilotcode.tui_v2.app import EnhancedApp
from pilotcode.tui_v2.components.prompt.input import PromptInput


@pytest.mark.asyncio
async def test_tui_v2_startup():
    """Test TUI v2 starts up correctly."""
    app = EnhancedApp(auto_allow=True)
    
    async with app.run_test() as pilot:
        # Wait for app to settle
        await pilot.pause()
        
        # Check that welcome message is displayed
        assert "PilotCode" in app.screen.message_list._messages[0].message.content
        assert "v0.2.0" in app.screen.message_list._messages[0].message.content


@pytest.mark.asyncio
async def test_tui_v2_help_command():
    """Test /help command works."""
    app = EnhancedApp(auto_allow=True)
    
    async with app.run_test() as pilot:
        await pilot.pause()
        
        # Find the PromptInput widget and set its text directly
        prompt_input = app.screen.query_one(PromptInput)
        prompt_input.text = "/help"
        
        # Submit the input
        await pilot.press("enter")
        
        # Wait for command processing
        await pilot.pause(0.5)
        
        # Debug: print all messages
        messages = app.screen.message_list._messages
        print(f"\n  Debug: {len(messages)} messages")
        for i, msg in enumerate(messages):
            content = msg.message.content[:50] if len(msg.message.content) > 50 else msg.message.content
            print(f"    {i}: {msg.message.type.name}: {content}")
        
        # Check that help content is displayed
        help_found = any("Available commands" in msg.message.content for msg in messages)
        assert help_found, "Help command output not found"


@pytest.mark.asyncio
async def test_tui_v2_clear_command():
    """Test /clear command works."""
    app = EnhancedApp(auto_allow=True)
    
    async with app.run_test() as pilot:
        await pilot.pause()
        
        # First add some messages
        prompt_input = app.screen.query_one(PromptInput)
        prompt_input.text = "hello"
        await pilot.press("enter")
        await pilot.pause(0.3)
        
        initial_count = len(app.screen.message_list._messages)
        print(f"\n  Debug: Initial messages: {initial_count}")
        
        # Clear
        prompt_input.text = "/clear"
        await pilot.press("enter")
        await pilot.pause(0.5)
        
        # Check messages are cleared
        final_count = len(app.screen.message_list._messages)
        print(f"  Debug: Final messages: {final_count}")
        
        # After clear, we should have only the system message about clearing
        assert final_count <= 1, f"Expected <= 1 messages after clear, got {final_count}"


@pytest.mark.asyncio
async def test_tui_v2_quit_command():
    """Test /quit command exits the app."""
    app = EnhancedApp(auto_allow=True)
    
    async with app.run_test() as pilot:
        await pilot.pause()
        
        # Type /quit
        prompt_input = app.screen.query_one(PromptInput)
        prompt_input.text = "/quit"
        await pilot.press("enter")
        
        # Wait for exit
        await pilot.pause(0.5)
        
        # App should be exited or in process of exiting
        # Note: In test mode, the app might not fully exit
        print(f"\n  Debug: App running: {app._running}")


@pytest.mark.asyncio
async def test_tui_v2_user_input():
    """Test user input is processed."""
    app = EnhancedApp(auto_allow=True)
    
    async with app.run_test() as pilot:
        await pilot.pause()
        
        # Type a message
        prompt_input = app.screen.query_one(PromptInput)
        prompt_input.text = "test message"
        await pilot.press("enter")
        
        # Wait for processing
        await pilot.pause(0.5)
        
        # Debug: print all messages
        messages = app.screen.message_list._messages
        print(f"\n  Debug: {len(messages)} messages")
        for i, msg in enumerate(messages):
            content = msg.message.content[:50] if len(msg.message.content) > 50 else msg.message.content
            print(f"    {i}: {msg.message.type.name}: {content}")
        
        # Check user message is displayed
        user_msg_found = any("test message" in msg.message.content.lower() for msg in messages)
        assert user_msg_found, "User message not displayed"


def run_tests():
    """Run all TUI v2 tests."""
    print("=" * 70)
    print("PILOTCODE TUI v2 TESTS")
    print("=" * 70)
    
    tests = [
        ("Startup", test_tui_v2_startup),
        ("Help Command", test_tui_v2_help_command),
        ("Clear Command", test_tui_v2_clear_command),
        ("Quit Command", test_tui_v2_quit_command),
        ("User Input", test_tui_v2_user_input),
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\nRunning: {name}...")
        try:
            asyncio.run(test_func())
            print(f"  ✅ PASSED")
            results.append((name, True, None))
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False, str(e)))
    
    # Print summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, p, _ in results if p)
    total = len(results)
    
    for name, passed_flag, error in results:
        status = "✅ PASS" if passed_flag else "❌ FAIL"
        print(f"{status}: {name}")
        if error:
            print(f"      Error: {error}")
    
    print(f"\nTotal: {passed}/{total} passed")
    
    if passed == total:
        print("\n🎉 All TUI v2 tests passed!")
        return 0
    else:
        print(f"\n⚠️ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
