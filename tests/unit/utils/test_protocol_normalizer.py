"""Tests for protocol_normalizer module."""

import pytest
from unittest.mock import MagicMock

from pilotcode.utils.protocol_normalizer import (
    MessageNormalizer,
    ResponseNormalizer,
)
from pilotcode.utils.model_client import Message, ToolCall


class TestMessageNormalizer:
    """Tests for MessageNormalizer."""

    def test_ensure_dicts_from_dataclass(self):
        """Test converting Message dataclasses to dicts."""
        normalizer = MessageNormalizer("openai")
        messages = [
            Message(role="system", content="Be helpful"),
            Message(role="user", content="Hello"),
            Message(
                role="assistant",
                content="",
                tool_calls=[ToolCall(id="call_1", name="Bash", arguments={"command": "ls"})],
            ),
            Message(role="tool", content="file.txt", tool_call_id="call_1"),
        ]
        msgs, system = normalizer.normalize(messages)
        assert system is None
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert msgs[2]["role"] == "assistant"
        assert "tool_calls" in msgs[2]
        assert msgs[3]["role"] == "tool"
        assert msgs[3]["tool_call_id"] == "call_1"

    def test_ensure_dicts_from_dict(self):
        """Test passing already-dict messages."""
        normalizer = MessageNormalizer("openai")
        messages = [
            {"role": "system", "content": "Be helpful"},
            {"role": "user", "content": "Hello"},
        ]
        msgs, system = normalizer.normalize(messages)
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"

    def test_openai_reasoning_content_ordering(self):
        """Test DeepSeek reasoning_content field ordering."""
        normalizer = MessageNormalizer("openai", provider_name="deepseek")
        messages = [{"role": "assistant", "content": "Hello", "reasoning_content": "thinking..."}]
        msgs, system = normalizer.normalize(messages)
        assert list(msgs[0].keys())[0] == "role"
        assert list(msgs[0].keys())[1] == "reasoning_content"
        assert msgs[0]["reasoning_content"] == "thinking..."

    def test_openai_content_default(self):
        """Test that content defaults to empty string."""
        normalizer = MessageNormalizer("openai")
        messages = [{"role": "assistant"}]
        msgs, system = normalizer.normalize(messages)
        assert msgs[0]["content"] == ""

    def test_anthropic_system_extraction(self):
        """Test Anthropic system message extraction."""
        normalizer = MessageNormalizer("anthropic")
        messages = [
            Message(role="system", content="Be helpful"),
            Message(role="user", content="Hello"),
        ]
        msgs, system = normalizer.normalize(messages)
        assert system == "Be helpful"
        assert all(m["role"] != "system" for m in msgs)
        assert msgs[0]["role"] == "user"

    def test_anthropic_multiple_system(self):
        """Test multiple system messages joined."""
        normalizer = MessageNormalizer("anthropic")
        messages = [
            Message(role="system", content="Rule 1"),
            Message(role="system", content="Rule 2"),
            Message(role="user", content="Hello"),
        ]
        msgs, system = normalizer.normalize(messages)
        assert system == "Rule 1\nRule 2"

    def test_anthropic_tool_message_conversion(self):
        """Test tool messages become user + tool_result."""
        normalizer = MessageNormalizer("anthropic")
        messages = [
            Message(role="user", content="Run ls"),
            Message(
                role="assistant",
                content="",
                tool_calls=[ToolCall(id="tu_1", name="Bash", arguments={"command": "ls"})],
            ),
            Message(role="tool", content="file.txt", tool_call_id="tu_1", name="Bash"),
        ]
        msgs, system = normalizer.normalize(messages)
        assert len(msgs) == 3
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"][0]["type"] == "tool_use"
        assert msgs[2]["role"] == "user"
        assert msgs[2]["content"][0]["type"] == "tool_result"
        assert msgs[2]["content"][0]["tool_use_id"] == "tu_1"

    def test_anthropic_filter_empty_content(self):
        """Test Anthropic empty content filtering."""
        normalizer = MessageNormalizer("anthropic")
        messages = [
            {"role": "user", "content": ""},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc1",
                        "type": "function",
                        "function": {"name": "Bash", "arguments": "{}"},
                    }
                ],
            },
            {"role": "user", "content": "Hello"},
        ]
        msgs, system = normalizer.normalize(messages)
        # Empty user message removed
        assert len(msgs) == 2
        assert msgs[0]["role"] == "assistant"
        assert msgs[1]["role"] == "user"

    def test_anthropic_assistant_tool_use(self):
        """Test assistant with tool_calls converted to tool_use blocks."""
        normalizer = MessageNormalizer("anthropic")
        messages = [
            Message(
                role="assistant",
                content="Let me check",
                tool_calls=[ToolCall(id="tu_1", name="Bash", arguments={"command": "ls"})],
            ),
        ]
        msgs, system = normalizer.normalize(messages)
        assert msgs[0]["role"] == "assistant"
        assert len(msgs[0]["content"]) == 2
        assert msgs[0]["content"][0]["type"] == "text"
        assert msgs[0]["content"][0]["text"] == "Let me check"
        assert msgs[0]["content"][1]["type"] == "tool_use"
        assert msgs[0]["content"][1]["name"] == "Bash"
        assert msgs[0]["content"][1]["input"] == {"command": "ls"}

    def test_anthropic_tool_id_scrubbing(self):
        """Test Anthropic tool call ID scrubbing."""
        normalizer = MessageNormalizer("anthropic")
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "tool-call", "toolCallId": "call@123!"},
                ],
            },
        ]
        msgs, system = normalizer.normalize(messages)
        assert msgs[0]["content"][0]["toolCallId"] == "call_123_"

    def test_mistral_tool_id_truncation(self):
        """Test Mistral tool call ID truncation."""
        normalizer = MessageNormalizer("openai", provider_name="mistral")
        messages = [
            {"role": "tool", "content": "result", "tool_call_id": "very_long_call_id_12345"},
        ]
        msgs, system = normalizer.normalize(messages)
        assert msgs[0]["tool_call_id"] == "verylongc"

    def test_mistral_sequence_fix(self):
        """Test Mistral tool->user sequence fix."""
        normalizer = MessageNormalizer("openai", provider_name="mistral")
        messages = [
            {"role": "tool", "content": "result", "tool_call_id": "tc1"},
            {"role": "user", "content": "Next"},
        ]
        msgs, system = normalizer.normalize(messages)
        assert len(msgs) == 3
        assert msgs[0]["role"] == "tool"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "Done."
        assert msgs[2]["role"] == "user"


class TestResponseNormalizer:
    """Tests for ResponseNormalizer."""

    def test_normalize_anthropic_response_text_only(self):
        """Non-streaming text response normalized to OpenAI chunk."""
        normalizer = ResponseNormalizer("anthropic")
        raw = {
            "content": [{"type": "text", "text": "Hello there"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }
        chunk = normalizer._normalize_anthropic_response(raw)
        assert chunk["choices"][0]["delta"]["content"] == "Hello there"
        assert chunk["choices"][0]["finish_reason"] == "stop"
        assert chunk["usage"]["prompt_tokens"] == 10
        assert chunk["usage"]["completion_tokens"] == 2

    def test_normalize_anthropic_response_with_tool_use(self):
        """Non-streaming tool_use response normalized to tool_calls."""
        normalizer = ResponseNormalizer("anthropic")
        raw = {
            "content": [
                {"type": "tool_use", "id": "tu_1", "name": "Bash", "input": {"command": "ls"}}
            ],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 15, "output_tokens": 20},
        }
        chunk = normalizer._normalize_anthropic_response(raw)
        tool_calls = chunk["choices"][0]["delta"]["tool_calls"]
        assert len(tool_calls) == 1
        assert tool_calls[0]["id"] == "tu_1"
        assert tool_calls[0]["function"]["name"] == "Bash"
        assert tool_calls[0]["function"]["arguments"] == '{"command": "ls"}'

    def test_normalize_anthropic_response_thinking(self):
        """Thinking blocks normalized to reasoning_content."""
        normalizer = ResponseNormalizer("anthropic")
        raw = {
            "content": [
                {"type": "thinking", "thinking": "Let me think..."},
                {"type": "text", "text": "Answer"},
            ],
            "stop_reason": "end_turn",
        }
        chunk = normalizer._normalize_anthropic_response(raw)
        assert chunk["choices"][0]["delta"]["reasoning_content"] == "Let me think..."
        assert chunk["choices"][0]["delta"]["content"] == "Answer"

    @pytest.mark.asyncio
    async def test_normalize_anthropic_stream_text(self):
        """Streaming text events yield OpenAI-style chunks."""
        normalizer = ResponseNormalizer("anthropic")
        raw_lines = [
            'data: {"type":"message_start","message":{"usage":{"input_tokens":5}}}',
            'data: {"type":"content_block_start","index":0,"content_block":{"type":"text"}}',
            'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}',
            'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" world"}}',
            'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":2}}',
        ]

        mock_resp = MagicMock()

        async def _aiter_lines():
            for line in raw_lines:
                yield line

        mock_resp.aiter_lines = _aiter_lines

        chunks = []
        async for chunk in normalizer._normalize_anthropic_stream(mock_resp):
            chunks.append(chunk)

        texts = [c["choices"][0]["delta"].get("content", "") for c in chunks]
        assert "".join(texts) == "Hello world"
        assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
        assert chunks[-1]["usage"]["completion_tokens"] == 2

    @pytest.mark.asyncio
    async def test_normalize_anthropic_stream_tool_use(self):
        """Streaming tool_use events yield tool_calls chunks."""
        normalizer = ResponseNormalizer("anthropic")
        raw_lines = [
            'data: {"type":"message_start","message":{"usage":{"input_tokens":5}}}',
            'data: {"type":"content_block_start","index":0,"content_block":{"type":"tool_use","id":"tu_1","name":"Bash"}}',
            'data: {"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta","partial_json":"{\\"command\\": \\"ls\\"}"}}',
            'data: {"type":"message_delta","delta":{"stop_reason":"tool_use"},"usage":{"output_tokens":10}}',
        ]

        mock_resp = MagicMock()

        async def _aiter_lines():
            for line in raw_lines:
                yield line

        mock_resp.aiter_lines = _aiter_lines

        chunks = []
        async for chunk in normalizer._normalize_anthropic_stream(mock_resp):
            chunks.append(chunk)

        tool_chunks = [c for c in chunks if "tool_calls" in c["choices"][0]["delta"]]
        assert len(tool_chunks) == 2
        assert tool_chunks[0]["choices"][0]["delta"]["tool_calls"][0]["function"]["name"] == "Bash"
        assert (
            tool_chunks[1]["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"]
            == '{"command": "ls"}'
        )

    @pytest.mark.asyncio
    async def test_normalize_anthropic_stream_thinking(self):
        """Streaming thinking_delta yields reasoning_content."""
        normalizer = ResponseNormalizer("anthropic")
        raw_lines = [
            'data: {"type":"message_start","message":{"usage":{"input_tokens":5}}}',
            'data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"Hmm..."}}',
            'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":2}}',
        ]

        mock_resp = MagicMock()

        async def _aiter_lines():
            for line in raw_lines:
                yield line

        mock_resp.aiter_lines = _aiter_lines

        chunks = []
        async for chunk in normalizer._normalize_anthropic_stream(mock_resp):
            chunks.append(chunk)

        reasoning = [c for c in chunks if "reasoning_content" in c["choices"][0]["delta"]]
        assert len(reasoning) == 1
        assert reasoning[0]["choices"][0]["delta"]["reasoning_content"] == "Hmm..."

    def test_normalize_openai_response(self):
        """OpenAI response wrapped as single chunk."""
        normalizer = ResponseNormalizer("openai")
        raw = {
            "choices": [
                {"message": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        }
        chunk = normalizer.normalize_response(raw)
        assert chunk["choices"][0]["delta"]["content"] == "Hello"
        assert chunk["choices"][0]["finish_reason"] == "stop"
        assert chunk["usage"]["prompt_tokens"] == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
