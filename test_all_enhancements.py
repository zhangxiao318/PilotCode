#!/usr/bin/env python3
"""Comprehensive test for all TUI-v2 enhancements."""

import asyncio
import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import pytest
from textual.pilot import Pilot
from textual.app import App
from textual.widgets import Static

from pilotcode.tui_v2.components.prompt.input import PromptInput, PromptWithMode
from pilotcode.tui_v2.components.message.virtual_list import HybridMessageList
from pilotcode.tui_v2.components.message.display import MessageDisplay
from pilotcode.tui_v2.components.search_bar import SearchBar, SearchMode
from pilotcode.tui_v2.components.diff_view import DiffView, DiffSummary, create_diff
from pilotcode.tui_v2.components.session_fork import SessionForkManager, SessionForked
from pilotcode.tui_v2.components.frecency_history import FrecencyHistory, FrecencyInputHistory
from pilotcode.tui_v2.providers.theme_enhanced import ThemeManager, Theme, BUILT_IN_THEMES
from pilotcode.tui_v2.controller.controller import UIMessage, MessageType


print("=" * 70)
print("TUI-v2 Enhancements Comprehensive Test")
print("=" * 70)


# ============================================================================
# Test 1: Message Display Components
# ============================================================================
def test_message_display():
    """Test MessageDisplay component."""
    print("\n📦 Test 1: Message Display Components")
    
    # Test different message types
    msg_user = UIMessage(type=MessageType.USER, content="Hello", is_complete=True)
    msg_assistant = UIMessage(type=MessageType.ASSISTANT, content="Hi there", is_complete=True)
    msg_system = UIMessage(type=MessageType.SYSTEM, content="Welcome", is_complete=True)
    msg_error = UIMessage(type=MessageType.ERROR, content="Error!", is_complete=True)
    
    display_user = MessageDisplay(msg_user)
    display_assistant = MessageDisplay(msg_assistant)
    
    assert display_user.message == msg_user
    assert display_assistant.message == msg_assistant
    
    print("  ✅ MessageDisplay creation")
    print("  ✅ Different message types")


# ============================================================================
# Test 2: Hybrid Message List
# ============================================================================
@pytest.mark.asyncio
async def test_hybrid_message_list():
    """Test HybridMessageList."""
    print("\n📦 Test 2: Hybrid Message List")
    
    class TestApp(App):
        def compose(self):
            self.ml = HybridMessageList()
            yield self.ml
    
    app = TestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        
        # Add messages
        msg1 = UIMessage(type=MessageType.SYSTEM, content="Welcome", is_complete=True)
        msg2 = UIMessage(type=MessageType.USER, content="Hello", is_complete=True)
        msg3 = UIMessage(type=MessageType.ASSISTANT, content="Hi!", is_complete=True)
        
        app.ml.add_message(msg1)
        app.ml.add_message(msg2)
        app.ml.add_message(msg3)
        
        await pilot.pause()
        
        assert app.ml.get_message_count() == 3
        
        # Test clear
        app.ml.clear_messages()
        assert app.ml.get_message_count() == 0
        
        print("  ✅ Message list creation")
        print("  ✅ Adding messages")
        print("  ✅ Message count tracking")
        print("  ✅ Clear messages")


# ============================================================================
# Test 3: Input with Syntax Highlighting
# ============================================================================
def test_input_syntax_highlighting():
    """Test PromptInput syntax highlighting."""
    print("\n📦 Test 3: Input Syntax Highlighting")
    
    input_widget = PromptInput()
    
    # Test file reference parsing
    text = "Check @file.txt and @\"path/to/file.py\" then /help"
    files = input_widget.get_file_references(text)
    assert len(files) == 2
    assert "file.txt" in files
    print(f"  ✅ File references: {files}")
    
    # Test command parsing
    cmd = input_widget.get_command("/help")
    assert cmd == "help"
    print(f"  ✅ Command parsing: /{cmd}")
    
    cmd2 = input_widget.get_command("hello world")
    assert cmd2 is None
    print("  ✅ Non-command detection")
    
    # Test highlighted text generation
    highlighted = input_widget.get_highlighted_text(text)
    assert len(highlighted) == len(text)
    print("  ✅ Syntax highlighting text generation")


# ============================================================================
# Test 4: Prompt Input Submission
# ============================================================================
@pytest.mark.asyncio
async def test_prompt_input_submission():
    """Test PromptInput submission."""
    print("\n📦 Test 4: Prompt Input Submission")
    
    class TestApp(App):
        def __init__(self):
            super().__init__()
            self.submitted = None
        
        def compose(self):
            self.input = PromptInput()
            yield self.input
        
        def on_prompt_input_submitted(self, event):
            self.submitted = event.text
    
    app = TestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        
        # Type and submit
        await pilot.press(*list("test message"))
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        
        assert app.submitted == "test message"
        print("  ✅ Text input")
        print("  ✅ Enter submission")


# ============================================================================
# Test 5: Search Bar
# ============================================================================
@pytest.mark.asyncio
async def test_search_bar():
    """Test SearchBar component."""
    print("\n📦 Test 5: Search Bar")
    
    class TestApp(App):
        def compose(self):
            self.search = SearchBar()
            yield self.search
    
    app = TestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        
        # Show search bar
        app.search.show()
        await pilot.pause()
        
        assert not app.search.has_class("hidden")
        print("  ✅ Search bar visibility")
        
        # Hide search bar
        app.search.hide()
        await pilot.pause()
        
        assert app.search.has_class("hidden")
        print("  ✅ Hide search bar")


# ============================================================================
# Test 6: Diff Visualization
# ============================================================================
def test_diff_visualization():
    """Test DiffView component."""
    print("\n📦 Test 6: Diff Visualization")
    
    # Create diff
    old_code = '''def hello():
    print("world")
'''
    new_code = '''def hello():
    print("hello world")
    return 42
'''
    
    diff_text = create_diff(old_code, new_code, "test.py")
    assert "def hello()" in diff_text
    assert "-" in diff_text  # Has deletions
    assert "+" in diff_text  # Has additions
    print("  ✅ Diff creation")
    
    # Create DiffView
    diff_view = DiffView(diff_text, filename="test.py", language="python")
    assert diff_view.filename == "test.py"
    assert diff_view.language == "python"
    print("  ✅ DiffView creation")
    
    # Check stats
    additions, deletions = diff_view._get_stats()
    assert additions > 0
    assert deletions > 0
    print(f"  ✅ Diff stats: +{additions}/-{deletions}")


# ============================================================================
# Test 7: Session Fork Manager
# ============================================================================
def test_session_fork_manager():
    """Test SessionForkManager."""
    print("\n📦 Test 7: Session Fork Manager")
    
    # Use temp directory for testing
    temp_dir = Path(tempfile.mkdtemp())
    
    try:
        manager = SessionForkManager(storage_dir=temp_dir)
        
        # Create messages
        messages = [
            UIMessage(type=MessageType.SYSTEM, content="Welcome", is_complete=True),
            UIMessage(type=MessageType.USER, content="Hello", is_complete=True),
            UIMessage(type=MessageType.ASSISTANT, content="Hi!", is_complete=True),
        ]
        
        # Fork session
        fork_id = manager.fork_session(
            parent_id="parent-123",
            messages=messages,
            fork_at_index=1,
            fork_name="test-fork"
        )
        
        assert fork_id is not None
        print(f"  ✅ Session fork created: {fork_id[:8]}")
        
        # Get forks
        forks = manager.get_forks("parent-123")
        assert len(forks) == 1
        assert forks[0]["name"] == "test-fork"
        print("  ✅ Fork retrieval")
        
        # Load fork messages
        loaded = manager.load_session_messages(fork_id)
        assert loaded is not None
        assert len(loaded) == 2  # Up to fork_at_index + 1
        print("  ✅ Fork message persistence")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================================
# Test 8: Frecency History
# ============================================================================
def test_frecency_history():
    """Test FrecencyHistory."""
    print("\n📦 Test 8: Frecency History")
    
    # Use temp directory
    temp_dir = Path(tempfile.mkdtemp())
    
    try:
        history = FrecencyHistory(
            storage_file=temp_dir / "test_history.json",
            max_entries=100
        )
        
        # Add entries
        history.add("Hello world")
        history.add("How are you")
        history.add("Hello world")  # Increases frequency
        
        # Get suggestions
        suggestions = history.get_suggestions("Hel")
        assert len(suggestions) > 0
        print(f"  ✅ Suggestions: {len(suggestions)} items")
        
        # Check frequency
        hello_entry = None
        for entry in history._entries.values():
            if entry.text == "Hello world":
                hello_entry = entry
                break
        
        assert hello_entry is not None
        assert hello_entry.frequency == 2
        print(f"  ✅ Frequency tracking: {hello_entry.frequency}")
        
        # Test frecency score
        score = hello_entry.frecency_score
        assert score > 0
        print(f"  ✅ Frecency score: {score:.2f}")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================================
# Test 9: Frecency Input History (Categories)
# ============================================================================
def test_frecency_input_history():
    """Test FrecencyInputHistory with categories."""
    print("\n📦 Test 9: Frecency Input History (Categories)")
    
    temp_dir = Path(tempfile.mkdtemp())
    
    try:
        history = FrecencyInputHistory(storage_dir=temp_dir)
        
        # Add different types
        history.add("Hello world")  # General
        history.add("/help")  # Command
        history.add("Check @file.txt")  # File
        
        # Check categorization
        assert len(history.general._entries) == 3
        assert len(history.commands._entries) == 1
        assert len(history.files._entries) == 1
        print("  ✅ Category separation")
        
        # Get command suggestions
        cmd_suggestions = history.get_command_suggestions("/")
        assert len(cmd_suggestions) == 1
        assert cmd_suggestions[0].text == "/help"
        print("  ✅ Command suggestions")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================================
# Test 10: Theme Manager
# ============================================================================
def test_theme_manager():
    """Test ThemeManager."""
    print("\n📦 Test 10: Theme Manager")
    
    temp_dir = Path(tempfile.mkdtemp())
    
    try:
        tm = ThemeManager(storage_dir=temp_dir)
        
        # Check built-in themes
        themes = tm.list_themes()
        assert len(themes) >= 7
        print(f"  ✅ Built-in themes: {len(themes)}")
        
        # Check specific themes exist
        expected_themes = ["default", "light", "dracula", "monokai", "nord", "gruvbox", "high-contrast"]
        for theme_name in expected_themes:
            assert theme_name in themes
        print(f"  ✅ Expected themes present")
        
        # Get theme
        theme = tm.get_theme("dracula")
        assert theme.name == "dracula"
        assert theme.background == "#282a36"
        print("  ✅ Theme retrieval")
        
        # Set theme
        result = tm.set_theme("nord")
        assert result is True
        assert tm.get_current_theme_name() == "nord"
        print("  ✅ Theme switching")
        
        # Get theme CSS
        css = tm.get_theme_css()
        assert "background:" in css
        assert "color:" in css
        print("  ✅ CSS generation")
        
        # Test auto-detection
        detected = tm.auto_detect_theme()
        assert detected in ["default", "light"]
        print(f"  ✅ Auto-detection: {detected}")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================================
# Test 11: Custom Theme
# ============================================================================
def test_custom_theme():
    """Test custom theme creation."""
    print("\n📦 Test 11: Custom Theme")
    
    temp_dir = Path(tempfile.mkdtemp())
    
    try:
        tm = ThemeManager(storage_dir=temp_dir)
        
        # Create custom theme
        custom = Theme(
            name="custom-test",
            background="#000000",
            text="#ffffff",
            primary="#ff0000"
        )
        
        # Add custom theme
        result = tm.add_custom_theme("my-theme", custom)
        assert result is True
        print("  ✅ Custom theme added")
        
        # Check it exists
        assert "my-theme" in tm.list_themes()
        print("  ✅ Custom theme in list")
        
        # Cannot override built-in
        result2 = tm.add_custom_theme("default", custom)
        assert result2 is False
        print("  ✅ Built-in theme protection")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================================
# Test 12: PromptWithMode
# ============================================================================
@pytest.mark.asyncio
async def test_prompt_with_mode():
    """Test PromptWithMode component."""
    print("\n📦 Test 12: PromptWithMode")
    
    class TestApp(App):
        def __init__(self):
            super().__init__()
            self.submitted = None
        
        def compose(self):
            self.prompt = PromptWithMode()
            yield self.prompt
        
        def on_prompt_with_mode_submitted(self, event):
            self.submitted = event.text
    
    app = TestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        
        # Type with syntax elements
        await pilot.press(*list("@test.txt /help"))
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        
        assert app.submitted == "@test.txt /help"
        print("  ✅ PromptWithMode submission")
        print("  ✅ Syntax element handling")


# ============================================================================
# Main Test Runner
# ============================================================================
def run_all_tests():
    """Run all tests."""
    tests = [
        ("Message Display", test_message_display),
        ("Hybrid Message List", test_hybrid_message_list),
        ("Input Syntax Highlighting", test_input_syntax_highlighting),
        ("Prompt Input Submission", test_prompt_input_submission),
        ("Search Bar", test_search_bar),
        ("Diff Visualization", test_diff_visualization),
        ("Session Fork Manager", test_session_fork_manager),
        ("Frecency History", test_frecency_history),
        ("Frecency Input History", test_frecency_input_history),
        ("Theme Manager", test_theme_manager),
        ("Custom Theme", test_custom_theme),
        ("PromptWithMode", test_prompt_with_mode),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            print(f"\n{'─' * 70}")
            if asyncio.iscoroutinefunction(test_func):
                asyncio.run(test_func())
            else:
                test_func()
            passed += 1
        except Exception as e:
            print(f"\n❌ FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 70)
    
    if failed == 0:
        print("\n🎉 All TUI-v2 enhancements are working correctly!")
    else:
        print(f"\n⚠️ {failed} test(s) failed")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
