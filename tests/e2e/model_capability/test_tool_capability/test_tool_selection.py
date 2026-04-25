"""Layer 2: Tool Selection Strategy.

Tests whether the LLM, when given access to the full PilotCode tool set,
selects the most appropriate tool for each task.

Attribution rules:
- Uses brute-force FileRead instead of Grep/CodeSearch -> llm_function_calling
- Uses wrong tool entirely -> llm_function_calling
- Correct tool but wrong params -> llm_function_calling
- Correct tool + params, but tool execution fails -> pilotcode_tool
"""

from __future__ import annotations

import asyncio
import pytest

from ..engine_helper import run_with_tools, ToolRunResult


@pytest.mark.llm_e2e
class TestSearchVsRead:
    """Search tasks should prefer search tools over reading every file."""

    async def test_search_pattern_should_use_grep(self, model_capability_client, e2e_timeout):
        """Searching for a text pattern should use Grep, not FileRead all files."""
        qe = model_capability_client
        result: ToolRunResult = await asyncio.wait_for(
            run_with_tools(
                qe,
                "Search for 'class Tool' definition in src/pilotcode/tools directory",
                timeout=e2e_timeout,
                max_turns=10,
            ),
            timeout=e2e_timeout + 30,
        )

        tool_names = [tc.name for tc in result.tool_calls]
        preferred = {"Grep", "CodeSearch", "LSP", "CodeContext"}
        acceptable = preferred | {"Glob"}  # Glob to find files first is OK

        # Should not read more than 4 files individually (model may read a few extras)
        file_read_count = tool_names.count("FileRead")
        assert file_read_count <= 4, (
            f"Should use search tools, not brute-force FileRead. "
            f"FileRead count: {file_read_count}, tools: {tool_names}. "
            f"Response: {result.final_response!r}"
        )

        # Should use at least one preferred search tool
        assert any(t in tool_names for t in preferred), (
            f"Should use a search tool (Grep/CodeSearch/LSP), got: {tool_names}. "
            f"Response: {result.final_response!r}"
        )

    async def test_find_files_should_use_glob(self, model_capability_client, e2e_timeout):
        """Finding files by pattern should use Glob or Bash."""
        qe = model_capability_client
        result: ToolRunResult = await asyncio.wait_for(
            run_with_tools(
                qe,
                "List all Python files in src/pilotcode/tools directory",
                timeout=e2e_timeout,
                max_turns=8,
            ),
            timeout=e2e_timeout + 30,
        )

        tool_names = [tc.name for tc in result.tool_calls]
        acceptable = {"Glob", "Bash", "FileRead"}  # FileRead after Glob is fine
        # At minimum Glob or Bash should appear
        assert "Glob" in tool_names or "Bash" in tool_names, (
            f"Should use Glob or Bash for file listing, got: {tool_names}\n"
            f"Final response: {result.final_response!r}"
        )


@pytest.mark.llm_e2e
class TestBatchOperations:
    """Batch operations should not loop over individual tool calls."""

    async def test_list_files_should_not_read_each(self, model_capability_client, e2e_timeout):
        """Listing files should not trigger reading each file individually."""
        qe = model_capability_client
        result: ToolRunResult = await asyncio.wait_for(
            run_with_tools(
                qe,
                "List all filenames in src/pilotcode/tools directory. I only need the names.",
                timeout=e2e_timeout,
                max_turns=8,
            ),
            timeout=e2e_timeout + 30,
        )

        tool_names = [tc.name for tc in result.tool_calls]
        file_read_count = tool_names.count("FileRead")
        assert file_read_count <= 2, (
            f"Should not read each file individually. FileRead count: {file_read_count}, "
            f"tools: {tool_names}"
        )


@pytest.mark.llm_e2e
class TestCodeIntelligence:
    """Code analysis tasks should use semantic/code search when available."""

    async def test_find_symbol_should_use_search(self, model_capability_client, e2e_timeout):
        """Finding a class/function definition should use search tools."""
        qe = model_capability_client
        result: ToolRunResult = await asyncio.wait_for(
            run_with_tools(
                qe,
                "Where is the QueryEngine class defined? What file and line?",
                timeout=e2e_timeout,
                max_turns=10,
            ),
            timeout=e2e_timeout + 30,
        )

        tool_names = [tc.name for tc in result.tool_calls]
        # Should not read every file
        file_read_count = tool_names.count("FileRead")
        assert file_read_count <= 3, (
            f"Should use search tools to locate symbol, not read every file. "
            f"FileRead count: {file_read_count}, tools: {tool_names}"
        )
