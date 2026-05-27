"""Tests for reasoning content compression."""

from __future__ import annotations


from pilotcode.utils.reasoning_compressor import compress_reasoning


class TestCompressReasoning:
    def test_none_returns_none(self):
        assert compress_reasoning(None) is None

    def test_short_reasoning_unchanged(self):
        text = "I decided to fix the bug."
        assert compress_reasoning(text) == text

    def test_long_reasoning_with_keywords(self):
        reasoning = "\n".join(
            [
                "Let me think about this...",
                "First, I need to understand the structure.",
                "Because the error occurs in login.py, I should check the auth module.",
                "Therefore, my plan is to edit src/auth.py and add validation.",
                "Wait, let me reconsider.",
                "Actually, the root cause is in the database layer.",
                "So I will modify src/db.py instead.",
            ]
            * 10
        )  # Make it long enough to trigger compression
        result = compress_reasoning(reasoning)
        assert result is not None
        assert result.startswith("[Thinking summary]")
        assert "Because" in result or "because" in result
        assert "Therefore" in result or "therefore" in result
        assert len(result) < len(reasoning)

    def test_long_reasoning_without_keywords_fallback(self):
        reasoning = "Line one.\nLine two.\nLine three.\n" * 100
        result = compress_reasoning(reasoning)
        assert result is not None
        assert result.endswith("...")
        assert len(result) <= 303  # 300 + "..."

    def test_chinese_reasoning(self):
        reasoning = "\n".join(
            [
                "让我想想这个问题...",
                "首先我需要理解代码结构。",
                "因为错误发生在 login.py，我应该检查 auth 模块。",
                "因此我的计划是编辑 src/auth.py 并添加验证。",
                "等等，让我重新考虑一下。",
                "实际上根因在数据库层。",
                "所以我要修改 src/db.py。",
            ]
            * 10
        )
        result = compress_reasoning(reasoning)
        assert result is not None
        assert result.startswith("[Thinking summary]")
        assert "因为" in result or "根因" in result
        assert len(result) < len(reasoning)

    def test_max_length_parameter(self):
        text = "A" * 500
        result = compress_reasoning(text, max_length=1000)
        assert result == text  # Below threshold, no compression

    def test_max_length_parameter_triggers(self):
        text = "A" * 500
        result = compress_reasoning(text, max_length=100)
        assert result is not None
        assert result.endswith("...")
