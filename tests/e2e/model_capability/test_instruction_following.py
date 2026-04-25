"""Instruction Following Capability Assessment.

Measures whether the LLM respects explicit constraints:
- Negation ("do not / 不要")
- Format requirements
- One-word answers
"""

import pytest
import asyncio

from .test_bare_llm.helpers import strip_thinking

_THINKING_MARKERS = (
    "The user is asking",
    "Analyze User Input",
    "Thinking Process",
    "thinking process",
    "Here's a thinking process",
)


async def _run_turn(query_engine, query: str, timeout: float) -> tuple[str, list[str]]:
    content_parts = []
    tool_names = []
    seen_thinking = False

    async for result in query_engine.submit_message(query):
        msg = result.message
        msg_type = msg.__class__.__name__
        if msg_type == "ToolUseMessage":
            tool_names.append(msg.name)
        elif (
            msg_type == "AssistantMessage"
            and hasattr(msg, "content")
            and isinstance(msg.content, str)
        ):
            chunk = msg.content
            stripped = chunk.strip()

            # Detect thinking content even without </think> tags
            if any(m in stripped for m in _THINKING_MARKERS):
                seen_thinking = True
                if "</think>" in chunk:
                    idx = chunk.rfind("</think>")
                    post = chunk[idx + len("</think>") :]
                    if post.strip() and len(post.strip()) <= 200:
                        content_parts.append(post)
                continue

            # After seeing thinking markers, only keep short, clean chunks
            if seen_thinking:
                if stripped and len(stripped) <= 200:
                    content_parts.append(chunk)
                continue

            content_parts.append(chunk)

    return strip_thinking("".join(content_parts)), tool_names


@pytest.mark.llm_e2e
class TestNegation:
    """LLM should respect 'do not' / '不要' instructions."""

    async def test_do_not_call_tool(self, model_capability_client, e2e_timeout):
        """User explicitly forbids a tool; LLM must not call it."""
        qe = model_capability_client

        # First, establish that the file exists in context
        await asyncio.wait_for(
            _run_turn(qe, "读取 README.md 的前3行", e2e_timeout),
            timeout=e2e_timeout,
        )

        # Now ask with negation
        c, t = await asyncio.wait_for(
            _run_turn(qe, "README.md 第一行说了什么？不要重新读取文件。", e2e_timeout),
            timeout=e2e_timeout,
        )
        assert "FileRead" not in t, f"Should NOT FileRead after negation, got {t}"
        assert len(c) > 5, f"Response too short: {c!r}"

    async def test_do_not_explain(self, model_capability_client, e2e_timeout):
        """User asks for a one-word answer; LLM should not ramble."""
        qe = model_capability_client

        c, t = await asyncio.wait_for(
            _run_turn(
                qe,
                "当前目录是 /home/zx/mycc/PilotCode 吗？只回答 Yes 或 No，不要解释。",
                e2e_timeout,
            ),
            timeout=e2e_timeout,
        )
        assert len(c.strip()) < 10, f"Should be short answer, got: {c!r}"


@pytest.mark.llm_e2e
class TestFormatConstraints:
    """LLM should follow output format instructions."""

    async def test_json_format(self, model_capability_client, e2e_timeout):
        """User asks for JSON; LLM should output valid JSON."""
        qe = model_capability_client

        c, t = await asyncio.wait_for(
            _run_turn(
                qe,
                "列出当前目录下前3个 Python 文件。用 JSON 格式输出，包含字段 name 和 size。",
                e2e_timeout,
            ),
            timeout=e2e_timeout,
        )
        # If the model called Glob first, that's fine — we check the final content
        assert "{" in c and "}" in c, f"Should contain JSON braces, got: {c!r}"

    async def test_list_format(self, model_capability_client, e2e_timeout):
        """User asks for a numbered list."""
        qe = model_capability_client

        c, t = await asyncio.wait_for(
            _run_turn(
                qe, "列出3个常见的 Python 内置函数。用编号列表格式（1. 2. 3.）。", e2e_timeout
            ),
            timeout=e2e_timeout,
        )
        assert "1." in c and "2." in c and "3." in c, f"Should contain numbered list, got: {c!r}"
