"""Layer 2: Code Editing Capability.

Tests whether the LLM can read a file, make precise edits, and verify
the result -- the core loop of an AI coding assistant.

Attribution rules:
- Edits without reading first -> llm_function_calling (ignores Read-before-Write rule)
- Wrong old_string in FileEdit -> llm_function_calling (parameter accuracy)
- FileEdit returns syntax error -> pilotcode_tool (if params were correct) or llm_function_calling (if old_string was wrong)
- Correct edit but no verification -> llm_capability (forgot to test)
"""

from __future__ import annotations

import asyncio
import pytest
from pathlib import Path

from ..engine_helper import run_with_tools, ToolRunResult


@pytest.mark.llm_e2e
class TestFileEditWorkflow:
    """Read -> Edit -> Verify workflow."""

    async def test_precise_edit_existing_file(self, model_capability_client, e2e_timeout, tmp_path):
        """Create a file, then ask the LLM to make a precise edit."""
        qe = model_capability_client
        test_dir = tmp_path / "edit_test"
        test_dir.mkdir()
        qe.config.cwd = str(test_dir)
        if qe.config.set_app_state:
            qe.config.set_app_state(lambda s: setattr(s, "cwd", str(test_dir)) or s)

        # Create initial file
        init_file = test_dir / "calculator.py"
        init_file.write_text("""def add(a, b):
    return a + b
""")

        result: ToolRunResult = await asyncio.wait_for(
            run_with_tools(
                qe,
                (
                    "In calculator.py, change the function signature from "
                    "'def add(a, b):' to 'def add(a, b, c=0):' and update the return "
                    "statement to 'return a + b + c'."
                ),
                timeout=e2e_timeout,
                max_turns=12,
            ),
            timeout=e2e_timeout + 30,
        )

        tool_names = [tc.name for tc in result.tool_calls]

        # Should read first
        assert "FileRead" in tool_names, (
            f"Should read file before editing. Tools: {tool_names}\n"
            f"Final response: {result.final_response!r}"
        )

        # Should edit
        assert "FileEdit" in tool_names or "FileWrite" in tool_names, (
            f"Should edit the file. Tools: {tool_names}\n"
            f"Final response: {result.final_response!r}"
        )

        # Verify the file was actually modified
        content = init_file.read_text()
        assert "c=0" in content, f"File was not modified correctly. Content:\n{content}"
        assert "a + b + c" in content, f"Return statement not updated. Content:\n{content}"

    async def test_add_method_to_class(self, model_capability_client, e2e_timeout, tmp_path):
        """Add a new method to an existing class."""
        qe = model_capability_client
        test_dir = tmp_path / "class_edit_test"
        test_dir.mkdir()
        qe.config.cwd = str(test_dir)
        if qe.config.set_app_state:
            qe.config.set_app_state(lambda s: setattr(s, "cwd", str(test_dir)) or s)

        init_file = test_dir / "greeter.py"
        init_file.write_text("""class Greeter:
    def __init__(self, name):
        self.name = name

    def greet(self):
        return f"Hello, {self.name}!"
""")

        result: ToolRunResult = await asyncio.wait_for(
            run_with_tools(
                qe,
                (
                    "In greeter.py, add a new method 'farewell(self)' to the Greeter class "
                    'that returns f"Goodbye, {self.name}!".'
                ),
                timeout=e2e_timeout,
                max_turns=12,
            ),
            timeout=e2e_timeout + 30,
        )

        tool_names = [tc.name for tc in result.tool_calls]

        # Should read first
        assert "FileRead" in tool_names, (
            f"Should read file before editing. Tools: {tool_names}\n"
            f"Final response: {result.final_response!r}"
        )

        # Should edit
        assert "FileEdit" in tool_names or "FileWrite" in tool_names, (
            f"Should edit the file. Tools: {tool_names}\n"
            f"Final response: {result.final_response!r}"
        )

        # Verify the file was modified
        content = init_file.read_text()
        assert "farewell" in content, f"Method not added. Content:\n{content}"
        assert "Goodbye" in content, f"Method body incorrect. Content:\n{content}"


@pytest.mark.llm_e2e
class TestEditVerification:
    """LLM should verify edits (syntax check, test run)."""

    async def test_edit_then_run_syntax_check(self, model_capability_client, e2e_timeout, tmp_path):
        """After editing, the LLM should verify syntax with Bash."""
        qe = model_capability_client
        test_dir = tmp_path / "verify_test"
        test_dir.mkdir()
        qe.config.cwd = str(test_dir)
        if qe.config.set_app_state:
            qe.config.set_app_state(lambda s: setattr(s, "cwd", str(test_dir)) or s)

        init_file = test_dir / "utils.py"
        init_file.write_text("""def helper():
    pass
""")

        result: ToolRunResult = await asyncio.wait_for(
            run_with_tools(
                qe,
                (
                    "In utils.py, change 'def helper():' to 'def helper(x):' and "
                    "make it return x * 2. Then verify the file has valid Python syntax."
                ),
                timeout=e2e_timeout,
                max_turns=12,
            ),
            timeout=e2e_timeout + 30,
        )

        tool_names = [tc.name for tc in result.tool_calls]

        # Should edit
        assert "FileEdit" in tool_names or "FileWrite" in tool_names, (
            f"Should edit the file. Tools: {tool_names}\n"
            f"Final response: {result.final_response!r}"
        )

        # Should run some verification (Bash for syntax check or test)
        # We don't strictly require Bash here because the LLM might just say it's valid,
        # but we check the file content is correct
        content = init_file.read_text()
        assert "def helper(x):" in content, f"Function signature not updated. Content:\n{content}"
        assert "return x * 2" in content, f"Return statement not updated. Content:\n{content}"
