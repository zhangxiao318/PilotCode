"""Pytest configuration and shared fixtures."""

import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pilotcode.state.app_state import AppState, get_default_app_state
from pilotcode.state.store import Store, set_global_store
from pilotcode.tools.base import ToolResult, ToolUseContext
from pilotcode.tools.registry import get_all_tools, get_tool_by_name


# ============================================================================
# Session Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def test_fixtures_dir(project_root) -> Path:
    """Return the test fixtures directory."""
    return project_root / "tests" / "fixtures"


# ============================================================================
# Function Fixtures - Environment
# ============================================================================

@pytest.fixture
def temp_dir() -> Path:
    """Create a temporary directory for test files."""
    tmp = tempfile.mkdtemp(prefix="pilotcode_test_")
    path = Path(tmp)
    yield path
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def temp_git_repo(temp_dir) -> Path:
    """Create a temporary git repository."""
    import subprocess
    
    # Initialize git repo
    subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], 
                   cwd=temp_dir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"],
                   cwd=temp_dir, capture_output=True, check=True)
    
    # Create initial file and commit
    (temp_dir / "README.md").write_text("# Test Repo\n")
    subprocess.run(["git", "add", "."], cwd=temp_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"],
                   cwd=temp_dir, capture_output=True, check=True)
    
    return temp_dir


@pytest.fixture
def clean_env(monkeypatch):
    """Provide a clean environment without user config."""
    # Save original env vars
    original_home = os.environ.get("HOME")
    original_xdg_config = os.environ.get("XDG_CONFIG_HOME")
    
    # Create temp config dir
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("HOME", tmp)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(Path(tmp) / ".config"))
        yield tmp
    
    # Restore (though monkeypatch should handle this)
    if original_home:
        os.environ["HOME"] = original_home
    if original_xdg_config:
        os.environ["XDG_CONFIG_HOME"] = original_xdg_config


# ============================================================================
# Function Fixtures - Application State
# ============================================================================

@pytest.fixture
def fresh_app_state(clean_env) -> AppState:
    """Create a fresh app state for each test."""
    return get_default_app_state()


@pytest.fixture
def app_store(fresh_app_state) -> Store:
    """Create and configure a fresh app store."""
    store = Store(fresh_app_state)
    set_global_store(store)
    return store


@pytest.fixture
def tool_context(app_store) -> ToolUseContext:
    """Create a tool execution context."""
    return ToolUseContext(
        get_app_state=app_store.get_state,
        set_app_state=lambda f: app_store.set_state(f)
    )


# ============================================================================
# Function Fixtures - Callbacks
# ============================================================================

@pytest.fixture
def allow_callback() -> Callable:
    """Mock permission callback that allows all operations."""
    async def callback(*args, **kwargs) -> dict:
        return {"behavior": "allow"}
    return callback


@pytest.fixture
def deny_callback() -> Callable:
    """Mock permission callback that denies all operations."""
    async def callback(*args, **kwargs) -> dict:
        return {"behavior": "deny"}
    return callback


@pytest.fixture
def mock_progress_callback() -> MagicMock:
    """Mock progress callback."""
    return MagicMock()


@pytest.fixture
def mock_llm_response() -> MagicMock:
    """Mock LLM response."""
    mock = MagicMock()
    mock.choices = [MagicMock()]
    mock.choices[0].message.content = "Test response"
    mock.choices[0].message.tool_calls = None
    return mock


# ============================================================================
# Function Fixtures - Test Data
# ============================================================================

@pytest.fixture
def sample_python_file(temp_dir) -> Path:
    """Create a sample Python file for testing."""
    file_path = temp_dir / "sample.py"
    content = '''#!/usr/bin/env python3
"""Sample file for testing."""

def hello():
    """Say hello."""
    return "Hello, World!"

def add(a, b):
    """Add two numbers."""
    return a + b

if __name__ == "__main__":
    print(hello())
    print(add(1, 2))
'''
    file_path.write_text(content)
    return file_path


@pytest.fixture
def sample_json_file(temp_dir) -> Path:
    """Create a sample JSON file for testing."""
    file_path = temp_dir / "sample.json"
    data = {
        "name": "test",
        "version": "1.0.0",
        "dependencies": ["dep1", "dep2"]
    }
    file_path.write_text(json.dumps(data, indent=2))
    return file_path


@pytest.fixture
def empty_file(temp_dir) -> Path:
    """Create an empty file."""
    file_path = temp_dir / "empty.txt"
    file_path.touch()
    return file_path


@pytest.fixture
def large_file(temp_dir) -> Path:
    """Create a large file for testing truncation."""
    file_path = temp_dir / "large.txt"
    # Create ~100KB file
    lines = [f"Line {i}: " + "x" * 100 for i in range(1000)]
    file_path.write_text("\n".join(lines))
    return file_path


@pytest.fixture
def binary_file(temp_dir) -> Path:
    """Create a binary file for testing."""
    file_path = temp_dir / "binary.bin"
    file_path.write_bytes(bytes(range(256)))
    return file_path


@pytest.fixture
def test_files_dir(temp_dir, sample_python_file, sample_json_file) -> Path:
    """Create a directory with multiple test files."""
    # Create subdirectories
    (temp_dir / "src" / "utils").mkdir(parents=True)
    (temp_dir / "tests").mkdir(parents=True)
    
    # Create files in different locations
    (temp_dir / "src" / "main.py").write_text("def main(): pass")
    (temp_dir / "src" / "utils" / "helpers.py").write_text("def helper(): pass")
    (temp_dir / "tests" / "test_main.py").write_text("def test_main(): pass")
    (temp_dir / "README.md").write_text("# Project\n")
    (temp_dir / ".gitignore").write_text("__pycache__/\n")
    
    return temp_dir


# ============================================================================
# Helper Functions
# ============================================================================

async def run_tool_test(
    tool_name: str,
    input_data: dict,
    context: ToolUseContext,
    allow_callback: Callable,
) -> ToolResult:
    """Helper function to run a tool test."""
    tool = get_tool_by_name(tool_name)
    if tool is None:
        raise ValueError(f"Tool {tool_name} not found")
    
    parsed = tool.input_schema(**input_data)
    result = await tool.call(
        parsed,
        context,
        allow_callback,
        None,  # parent_message
        lambda x: None,  # on_progress
    )
    return result


@pytest.helpers = type('obj', (object,), {
    'run_tool_test': run_tool_test,
})()
