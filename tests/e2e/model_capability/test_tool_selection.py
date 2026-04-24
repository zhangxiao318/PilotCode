"""Tool Selection Capability Assessment.

Measures whether the LLM picks the *most appropriate* tool for a task,
rather than falling back to a generic one (e.g., reading every file
instead of using Grep/CodeSearch).
"""

import pytest
import asyncio


async def _run_turn(query_engine, query: str, timeout: float) -> tuple[str, list[str]]:
    content_parts = []
    tool_names = []

    async for result in query_engine.submit_message(query):
        msg = result.message
        msg_type = msg.__class__.__name__
        if msg_type == "ToolUseMessage":
            tool_names.append(msg.name)
        elif hasattr(msg, "content") and isinstance(msg.content, str):
            content_parts.append(msg.content)

    return "".join(content_parts), tool_names


@pytest.mark.llm_e2e
class TestSearchVsRead:
    """Search tasks should use Grep/CodeSearch, not brute-force FileRead."""

    async def test_search_pattern_should_use_grep(self, model_capability_client, e2e_timeout):
        """Searching for a text pattern should prefer Grep over FileRead."""
        qe = model_capability_client

        c, t = await asyncio.wait_for(
            _run_turn(qe, "在 src/pilotcode/tools 目录搜索 'class Tool' 的定义", e2e_timeout),
            timeout=e2e_timeout,
        )
        # We accept Grep, CodeSearch, or even LSP — anything better than raw FileRead storm
        preferred = {"Grep", "CodeSearch", "LSP", "CodeContext"}
        assert any(name in t for name in preferred), (
            f"Should use a search tool, got {t}. "
            f"Brute-force FileRead indicates poor tool selection."
        )

    async def test_find_files_should_use_glob(self, model_capability_client, e2e_timeout):
        """Finding files by pattern should use Glob."""
        qe = model_capability_client

        c, t = await asyncio.wait_for(
            _run_turn(qe, "当前目录有哪些 py 文件？", e2e_timeout),
            timeout=e2e_timeout,
        )
        acceptable = {"Glob", "Bash"}
        assert any(name in t for name in acceptable), f"Should use Glob or Bash, got {t}"


@pytest.mark.llm_e2e
class TestBatchVsIndividual:
    """Batch operations should use batch tools, not loop over individual calls."""

    async def test_batch_list_should_not_read_each(self, model_capability_client, e2e_timeout):
        """Listing files should not trigger 10+ FileReads."""
        qe = model_capability_client

        c, t = await asyncio.wait_for(
            _run_turn(qe, "列出 src/pilotcode/tools 目录下所有文件名", e2e_timeout),
            timeout=e2e_timeout,
        )
        file_read_count = t.count("FileRead")
        assert (
            file_read_count <= 3
        ), f"Should not read each file individually. FileRead count: {file_read_count}, tools: {t}"


@pytest.mark.llm_e2e
class TestCodeIntelligence:
    """Code analysis tasks should use LSP/CodeSearch when available."""

    async def test_find_definition_should_use_lsp_or_search(
        self, model_capability_client, e2e_timeout
    ):
        """Finding a symbol definition should use semantic/code search."""
        qe = model_capability_client

        c, t = await asyncio.wait_for(
            _run_turn(qe, "QueryEngine 类在哪个文件里定义的？", e2e_timeout),
            timeout=e2e_timeout,
        )
        preferred = {"LSP", "CodeSearch", "Grep", "CodeContext"}
        assert any(name in t for name in preferred), f"Should use code intelligence tool, got {t}"
