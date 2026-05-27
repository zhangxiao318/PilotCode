"""Tests for dynamic thinking mode control."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from pilotcode.query_engine import QueryEngine, QueryEngineConfig


class TestShouldEnableThinking:
    """Test _should_enable_thinking heuristic."""

    @pytest.fixture
    def engine(self, tmp_path):
        config = QueryEngineConfig(
            cwd=str(tmp_path),
            tools=[],
            enable_thinking=None,  # auto
        )
        return QueryEngine(config=config)

    def test_greeting_disabled(self, engine):
        assert engine._should_enable_thinking("hello") is False
        assert engine._should_enable_thinking("你好") is False
        assert engine._should_enable_thinking("在吗") is False
        assert engine._should_enable_thinking("introduce yourself") is False

    def test_short_prompt_disabled(self, engine):
        assert engine._should_enable_thinking("ok") is False
        assert engine._should_enable_thinking("yes") is False

    def test_complex_keywords_enabled(self, engine):
        assert engine._should_enable_thinking("fix the bug in login module") is True
        assert engine._should_enable_thinking("refactor this module for better performance") is True
        assert engine._should_enable_thinking("optimize the database query performance") is True
        assert (
            engine._should_enable_thinking(
                "请帮我设计一个高可用的微服务架构方案，包含服务发现和负载均衡"
            )
            is True
        )
        assert (
            engine._should_enable_thinking("我需要修复这个用户登录模块的错误，请分析根本原因")
            is True
        )

    def test_changed_files_enabled(self, engine):
        engine._changed_files = ["src/main.py"]
        assert engine._should_enable_thinking("continue with the implementation") is True

    def test_simple_query_disabled(self, engine):
        assert engine._should_enable_thinking("what time is it?") is False
        assert engine._should_enable_thinking("show me the files") is False

    def test_force_enable_override(self, tmp_path):
        from tests.mock_llm import MockModelClient

        config = QueryEngineConfig(
            cwd=str(tmp_path),
            tools=[],
            enable_thinking=True,  # force on
            model_client=MockModelClient(),  # Use mock client that supports reasoning
        )
        engine = QueryEngine(config=config)
        assert engine._build_extra_body("hello") == {"enable_thinking": True}

    def test_force_disable_override(self, tmp_path):
        from tests.mock_llm import MockModelClient

        config = QueryEngineConfig(
            cwd=str(tmp_path),
            tools=[],
            enable_thinking=False,  # force off
            model_client=MockModelClient(),  # Use mock client that supports reasoning
        )
        engine = QueryEngine(config=config)
        assert engine._build_extra_body("fix bug") == {"enable_thinking": False}

    def test_non_reasoning_provider_returns_none(self, tmp_path):
        config = QueryEngineConfig(
            cwd=str(tmp_path),
            tools=[],
            enable_thinking=None,
        )
        engine = QueryEngine(config=config)
        # Mock client to not support reasoning
        engine.client = MagicMock()
        engine.client.supports_reasoning_content = False
        assert engine._build_extra_body("fix bug") is None
