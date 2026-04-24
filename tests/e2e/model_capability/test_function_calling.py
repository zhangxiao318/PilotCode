"""Function Calling Capability Assessment.

Measures how accurately the backend LLM decides to call tools,
selects the right tool, and fills parameters.
"""

import pytest
import asyncio
from typing import Any

# ---------------------------------------------------------------------------
# Test data: (query, expected_tool_name, description)
# ---------------------------------------------------------------------------

EXPLICIT_TOOL_CALLS = [
    ("用 Glob 查找所有 py 文件", "Glob", "explicit Glob request"),
    ("读取 README.md 的前10行", "FileRead", "explicit FileRead request"),
    ("执行 pwd 命令", "Bash", "explicit Bash request"),
    ("搜索代码里所有 TODO 注释", "Grep", "explicit Grep request"),
    ("索引当前代码库", "CodeIndex", "explicit CodeIndex request"),
]

IMPLICIT_TOOL_CALLS = [
    ("当前目录有哪些 Python 文件？", ["Glob", "Bash"], "implicit file listing"),
    ("pyproject.toml 里项目名称是什么？", ["FileRead", "Glob"], "implicit config read"),
    ("给我看看 src/pilotcode/tools/base.py 的内容", ["FileRead", "Glob"], "implicit file read"),
]

PARAM_ACCURACY_CASES = [
    (
        "用 Glob 查找 src/pilotcode/tools 目录下所有 py 文件",
        "Glob",
        {"pattern": "*.py", "path": "src/pilotcode/tools"},
        "parameter accuracy",
    ),
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _get_first_tool_call(query_engine, query: str, timeout: float) -> dict[str, Any] | None:
    """Submit a query and capture the first tool call (if any)."""
    tool_calls = []
    assistant_content = []

    try:
        async for result in query_engine.submit_message(query):
            msg = result.message
            msg_type = msg.__class__.__name__

            if msg_type == "ToolUseMessage":
                tool_calls.append(
                    {
                        "name": msg.name,
                        "input": msg.input,
                    }
                )
            elif hasattr(msg, "content") and isinstance(msg.content, str):
                assistant_content.append(msg.content)
    except asyncio.TimeoutError:
        pass

    if tool_calls:
        return {
            "tool_calls": tool_calls,
            "content": "".join(assistant_content),
        }
    return {"tool_calls": [], "content": "".join(assistant_content)}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.llm_e2e
class TestExplicitToolCalls:
    """LLM should call tools when user explicitly asks for an operation."""

    @pytest.mark.parametrize("query,expected_tool,desc", EXPLICIT_TOOL_CALLS)
    async def test_explicit(self, model_capability_client, e2e_timeout, query, expected_tool, desc):
        result = await asyncio.wait_for(
            _get_first_tool_call(model_capability_client, query, e2e_timeout),
            timeout=e2e_timeout,
        )
        names = [t["name"] for t in result["tool_calls"]]
        assert expected_tool in names, (
            f"[{desc}] Expected '{expected_tool}' in {names}, "
            f"content: {result['content'][:100]!r}"
        )


@pytest.mark.llm_e2e
class TestImplicitToolCalls:
    """LLM should infer tool usage from implicit user intent."""

    @pytest.mark.parametrize("query,expected_tools,desc", IMPLICIT_TOOL_CALLS)
    async def test_implicit(
        self, model_capability_client, e2e_timeout, query, expected_tools, desc
    ):
        result = await asyncio.wait_for(
            _get_first_tool_call(model_capability_client, query, e2e_timeout),
            timeout=e2e_timeout,
        )
        names = [t["name"] for t in result["tool_calls"]]
        assert any(t in names for t in expected_tools), (
            f"[{desc}] Expected one of {expected_tools} in {names}, "
            f"content: {result['content'][:100]!r}"
        )


@pytest.mark.llm_e2e
class TestParameterAccuracy:
    """LLM should fill tool parameters correctly."""

    @pytest.mark.parametrize("query,expected_tool,expected_params,desc", PARAM_ACCURACY_CASES)
    async def test_params(
        self, model_capability_client, e2e_timeout, query, expected_tool, expected_params, desc
    ):
        result = await asyncio.wait_for(
            _get_first_tool_call(model_capability_client, query, e2e_timeout),
            timeout=e2e_timeout,
        )
        names = [t["name"] for t in result["tool_calls"]]
        assert expected_tool in names, f"[{desc}] Tool not called: {names}"

        tool_call = next(t for t in result["tool_calls"] if t["name"] == expected_tool)
        for key, expected_val in expected_params.items():
            actual = tool_call["input"].get(key)
            assert (
                actual == expected_val
            ), f"[{desc}] Param '{key}' expected {expected_val!r}, got {actual!r}"
