"""Pytest configuration and shared fixtures."""

import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import sys
sys.path.insert(0, 'src')

from pilotcode.state.app_state import get_default_app_state
from pilotcode.state.store import Store, set_global_store
from pilotcode.tools.base import ToolUseContext


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    tmp = tempfile.mkdtemp(prefix="pilotcode_test_")
    yield Path(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def app_state():
    """Create a fresh app state for each test."""
    store = Store(get_default_app_state())
    set_global_store(store)
    return store


@pytest.fixture
def tool_context(app_state):
    """Create a tool execution context."""
    return ToolUseContext(
        get_app_state=app_state.get_state,
        set_app_state=lambda f: app_state.set_state(f)
    )


@pytest.fixture
def allow_callback():
    """Mock permission callback that allows all operations."""
    async def callback(*args, **kwargs):
        return {"behavior": "allow"}
    return callback


@pytest.fixture
def deny_callback():
    """Mock permission callback that denies all operations."""
    async def callback(*args, **kwargs):
        return {"behavior": "deny"}
    return callback


@pytest.fixture
def sample_python_file(temp_dir):
    """Create a sample Python file for testing."""
    file_path = temp_dir / "sample.py"
    content = '''#!/usr/bin/env python3
"""Sample file for testing."""

def hello():
    """Say hello."""
    return "Hello, World!"

if __name__ == "__main__":
    print(hello())
'''
    file_path.write_text(content)
    return file_path


@pytest.fixture
def empty_file(temp_dir):
    """Create an empty file."""
    file_path = temp_dir / "empty.txt"
    file_path.touch()
    return file_path


@pytest.fixture(autouse=True)
def reset_global_state():
    """Reset global state before each test."""
    # Cleanup code here if needed
    yield
    # Post-test cleanup
