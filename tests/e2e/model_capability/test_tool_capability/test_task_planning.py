"""Layer 2: Task Planning Capability.

Tests whether the LLM can decompose complex coding tasks into correct
multi-step sequences and execute them with appropriate tools.

Attribution rules:
- Wrong sequence (edit before read) -> llm_function_calling
- Missing steps (no test after edit) -> llm_capability / llm_function_calling
- Redundant steps (re-read same file multiple times) -> llm_function_calling
- Correct plan but tool execution fails -> pilotcode_tool
"""

from __future__ import annotations

import asyncio
import pytest
import tempfile
from pathlib import Path

from ..engine_helper import run_with_tools, ToolRunResult


@pytest.mark.llm_e2e
class TestMultiStepCodingTask:
    """Complex tasks requiring discover -> read -> modify -> verify."""

    async def test_find_and_read_then_answer(self, model_capability_client, e2e_timeout):
        """Find a file, read it, then answer a question without re-reading."""
        qe = model_capability_client
        result: ToolRunResult = await asyncio.wait_for(
            run_with_tools(
                qe,
                "Find the file that defines QueryEngineConfig, read it, then tell me what fields it has.",
                timeout=e2e_timeout,
                max_turns=12,
            ),
            timeout=e2e_timeout + 30,
        )

        tool_names = [tc.name for tc in result.tool_calls]

        # Should discover first
        has_discovery = any(t in tool_names for t in ("Glob", "Grep", "CodeSearch", "LSP"))
        assert has_discovery, f"Should discover file first, got tools: {tool_names}"

        # Should read the file
        assert "FileRead" in tool_names, f"Should read the discovered file, got tools: {tool_names}"

        # Should provide a non-empty answer
        assert (
            len(result.final_response) > 20
        ), f"Should provide an answer, got: {result.final_response[:200]!r}"

    async def test_add_function_and_run(self, model_capability_client, e2e_timeout, tmp_path):
        """Create a Python file with a function, then run it with Bash."""
        qe = model_capability_client
        # Create a temporary working directory for this test
        test_dir = tmp_path / "planning_test"
        test_dir.mkdir()
        qe.config.cwd = str(test_dir)

        result: ToolRunResult = await asyncio.wait_for(
            run_with_tools(
                qe,
                (
                    "Create a file called math_utils.py containing a function "
                    "'add(a, b)' that returns a + b. Then run a Python command to test it."
                ),
                timeout=e2e_timeout,
                max_turns=12,
            ),
            timeout=e2e_timeout + 30,
        )

        tool_names = [tc.name for tc in result.tool_calls]

        # Should write a file
        assert (
            "FileWrite" in tool_names or "FileEdit" in tool_names
        ), f"Should write or edit a file, got tools: {tool_names}"

        # Should run a test
        assert (
            "Bash" in tool_names
        ), f"Should run a bash command to test the code, got tools: {tool_names}"

        # Verify file was actually created
        created_file = test_dir / "math_utils.py"
        assert created_file.exists(), f"File was not created at {created_file}"


@pytest.mark.llm_e2e
class TestTaskDecomposition:
    """LLM should break down multi-part requests into logical steps."""

    async def test_count_and_report(self, model_capability_client, e2e_timeout):
        """Ask for multiple pieces of information in one query."""
        qe = model_capability_client
        result: ToolRunResult = await asyncio.wait_for(
            run_with_tools(
                qe,
                (
                    "How many Python files are in src/pilotcode/tools? "
                    "Also, what is the first line of src/pilotcode/query_engine.py?"
                ),
                timeout=e2e_timeout,
                max_turns=12,
            ),
            timeout=e2e_timeout + 30,
        )

        tool_names = [tc.name for tc in result.tool_calls]

        # Should use Glob or Bash for counting
        assert (
            "Glob" in tool_names or "Bash" in tool_names
        ), f"Should use Glob/Bash to count files, got: {tool_names}"

        # Should use FileRead for the first line
        assert (
            "FileRead" in tool_names
        ), f"Should use FileRead to read query_engine.py, got: {tool_names}"

        # Should answer both parts
        assert (
            len(result.final_response) > 30
        ), f"Should answer both questions, got: {result.final_response[:200]!r}"
