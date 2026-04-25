"""Context Retention Capability Assessment.

Measures whether the LLM remembers information across turns
without re-reading or re-searching.
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
    """Run one turn, return (assistant_content, tool_names_called)."""
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
class TestTwoTurnContext:
    """Two-turn conversation: read -> ask about it without re-reading."""

    async def test_file_content_remembered(self, model_capability_client, e2e_timeout):
        """Turn 1: read file. Turn 2: ask about content. Should NOT FileRead again."""
        qe = model_capability_client

        # Turn 1
        c1, t1 = await asyncio.wait_for(
            _run_turn(qe, "读取 README.md 的前5行", e2e_timeout), timeout=e2e_timeout
        )
        assert "FileRead" in t1, f"Turn 1 should FileRead, got {t1}"

        # Turn 2
        c2, t2 = await asyncio.wait_for(
            _run_turn(qe, "刚才读的文件第一行是什么？", e2e_timeout), timeout=e2e_timeout
        )
        assert "FileRead" not in t2, f"Turn 2 should NOT FileRead again, got {t2}"
        assert len(c2) > 5, f"Turn 2 response too short: {c2!r}"

    async def test_search_result_remembered(self, model_capability_client, e2e_timeout):
        """Turn 1: Glob. Turn 2: ask about findings without Glob again."""
        qe = model_capability_client

        c1, t1 = await asyncio.wait_for(
            _run_turn(qe, "列出 src/pilotcode/tools 目录下所有 py 文件", e2e_timeout),
            timeout=e2e_timeout,
        )
        assert "Glob" in t1 or "Bash" in t1, f"Turn 1 should list files, got {t1}"

        c2, t2 = await asyncio.wait_for(
            _run_turn(qe, "刚才列出的文件里有哪些？", e2e_timeout),
            timeout=e2e_timeout,
        )
        assert "Glob" not in t2, f"Turn 2 should NOT Glob again, got {t2}"
        assert len(c2) > 10, f"Turn 2 response too short: {c2!r}"


@pytest.mark.llm_e2e
class TestMultiTurnContext:
    """Three+ turns: chain of operations with cumulative context."""

    async def test_three_turn_chain(self, model_capability_client, e2e_timeout):
        """Turn 1: Glob. Turn 2: FileRead. Turn 3: summarize without re-reading."""
        qe = model_capability_client

        # Turn 1: find file
        c1, t1 = await asyncio.wait_for(
            _run_turn(qe, "用 Glob 查找 src/pilotcode/query_engine.py", e2e_timeout),
            timeout=e2e_timeout,
        )

        # Turn 2: read it
        c2, t2 = await asyncio.wait_for(
            _run_turn(qe, "读取这个文件的前20行", e2e_timeout),
            timeout=e2e_timeout,
        )
        assert "FileRead" in t2, f"Turn 2 should FileRead, got {t2}"

        # Turn 3: summarize — should NOT read again
        c3, t3 = await asyncio.wait_for(
            _run_turn(qe, "根据刚才读的内容，这个文件主要做什么？不要重新读取。", e2e_timeout),
            timeout=e2e_timeout,
        )
        assert "FileRead" not in t3, f"Turn 3 should NOT FileRead again, got {t3}"
        assert len(c3) > 20, f"Turn 3 response too short: {c3!r}"
