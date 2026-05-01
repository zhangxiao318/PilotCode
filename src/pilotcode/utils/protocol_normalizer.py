"""Protocol normalization layer.

Converts between provider-native formats and the internal OpenAI-style
representation.  Inspired by opencode's ProviderTransform.message() and
response-handling paths.
"""

import asyncio
import json
from typing import Any, AsyncIterator


class NormalizationError(Exception):
    """Error during message or response normalization."""


class MessageNormalizer:
    """Normalize messages for different API protocols.

    Handles provider-specific edge cases:
    - Empty-content filtering (Anthropic rejects empty string messages)
    - Tool-call ID scrubbing (Claude: replace special chars; Mistral: truncate)
    - Message-sequence fixes (Mistral: tool msg cannot precede user msg directly)
    - Protocol-specific role / content conversion
    """

    def __init__(self, api_protocol: str, provider_name: str = "unknown"):
        self.api_protocol = api_protocol
        self.provider_name = provider_name

    def normalize(
        self,
        messages: list[Any],
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Normalize messages for the target protocol.

        Returns:
            (messages, system_text) where *system_text* is the extracted
            system prompt for Anthropic, or ``None`` for OpenAI.
        """
        msgs = self._ensure_dicts(messages)
        msgs = self._filter_empty_content(msgs)
        msgs = self._scrub_tool_call_ids(msgs)
        msgs = self._fix_message_sequences(msgs)

        if self.api_protocol == "anthropic":
            return self._normalize_for_anthropic(msgs)
        return self._normalize_for_openai(msgs)

    # ------------------------------------------------------------------
    # Shared preprocessing
    # ------------------------------------------------------------------

    def _ensure_dicts(self, messages: list[Any]) -> list[dict[str, Any]]:
        """Convert Message dataclasses to plain dicts."""
        result: list[dict[str, Any]] = []
        for msg in messages:
            if isinstance(msg, dict):
                result.append(dict(msg))
                continue

            # Assume Message dataclass (duck-type to avoid circular import)
            api_msg: dict[str, Any] = {"role": msg.role}
            if msg.content is not None:
                api_msg["content"] = msg.content
            if getattr(msg, "tool_calls", None):
                api_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            if getattr(msg, "tool_call_id", None):
                api_msg["tool_call_id"] = msg.tool_call_id
            if getattr(msg, "name", None):
                api_msg["name"] = msg.name
            if getattr(msg, "reasoning_content", None):
                api_msg["reasoning_content"] = msg.reasoning_content
            result.append(api_msg)
        return result

    def _filter_empty_content(self, msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter out messages with empty content.

        Anthropic rejects empty-string messages and empty text parts.
        We keep assistant messages that carry tool_calls even when content
        is empty, because they are structurally required.
        """
        if self.api_protocol != "anthropic":
            return msgs

        result: list[dict[str, Any]] = []
        for msg in msgs:
            content = msg.get("content", "")
            if content == "":
                if msg.get("role") == "assistant" and msg.get("tool_calls"):
                    result.append(msg)
                continue
            result.append(msg)
        return result

    def _scrub_tool_call_ids(self, msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Scrub tool-call IDs to match provider requirements.

        - Claude / Anthropic: replace non-alphanum / ``_`` / ``-`` with ``_``
        - Mistral: truncate to 9 alphanumeric chars, pad with ``0``
        """
        provider = self.provider_name.lower()

        if self.api_protocol == "anthropic" or provider == "anthropic":

            def scrub(id_str: str) -> str:
                return "".join(c if c.isalnum() or c in "_-" else "_" for c in id_str)

        elif "mistral" in provider:

            def scrub(id_str: str) -> str:
                cleaned = "".join(c for c in id_str if c.isalnum())
                return cleaned[:9].ljust(9, "0")

        else:
            return msgs

        for msg in msgs:
            role = msg.get("role", "")

            # Message-level tool_calls (OpenAI-style dicts)
            if role == "assistant" and "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    tc["id"] = scrub(tc.get("id", ""))

            # Array content parts (ai-sdk style)
            content = msg.get("content")
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    ptype = part.get("type", "")
                    if ptype in ("tool-call", "tool-result", "tool_use", "tool_result"):
                        for key in ("toolCallId", "tool_call_id", "tool_use_id"):
                            if key in part:
                                part[key] = scrub(part[key])

            # Tool message top-level ID
            if role == "tool" and "tool_call_id" in msg:
                msg["tool_call_id"] = scrub(msg["tool_call_id"])

        return msgs

    def _fix_message_sequences(self, msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fix message sequences that violate provider constraints.

        Mistral: a ``role: tool`` message cannot be followed directly by a
        ``role: user`` message.  Inject a minimal assistant turn in between.
        """
        if "mistral" not in self.provider_name.lower():
            return msgs

        result: list[dict[str, Any]] = []
        for i, msg in enumerate(msgs):
            result.append(msg)
            next_msg = msgs[i + 1] if i + 1 < len(msgs) else None
            if msg.get("role") == "tool" and next_msg and next_msg.get("role") == "user":
                result.append({"role": "assistant", "content": "Done."})
        return result

    # ------------------------------------------------------------------
    # Anthropic-specific normalization
    # ------------------------------------------------------------------

    def _normalize_for_anthropic(
        self, msgs: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Convert messages to Anthropic format.

        - Extract ``system`` messages to a top-level system string.
        - Convert ``role: tool`` → ``role: user`` with ``tool_result`` blocks.
        - Convert assistant ``tool_calls`` → ``tool_use`` blocks.
        """
        system_texts: list[str] = []
        anthropic_msgs: list[dict[str, Any]] = []

        for msg in msgs:
            role = msg.get("role", "")
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", [])
            tool_call_id = msg.get("tool_call_id", "")

            if role == "system":
                if isinstance(content, str) and content:
                    system_texts.append(content)
                continue

            if role == "tool":
                anthropic_msgs.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_call_id,
                                "content": content if isinstance(content, str) else str(content),
                            }
                        ],
                    }
                )
                continue

            if role == "assistant" and tool_calls:
                content_blocks: list[dict[str, Any]] = []
                if content:
                    content_blocks.append({"type": "text", "text": content})
                for tc in tool_calls:
                    tc_id = tc.get("id", "")
                    tc_name = tc.get("function", {}).get("name", "")
                    tc_args = tc.get("function", {}).get("arguments", "")
                    try:
                        input_data = json.loads(tc_args) if isinstance(tc_args, str) else tc_args
                    except json.JSONDecodeError:
                        input_data = {}
                    content_blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc_id,
                            "name": tc_name,
                            "input": input_data,
                        }
                    )
                anthropic_msgs.append({"role": "assistant", "content": content_blocks})
                continue

            # user or plain assistant without tool_calls
            anthropic_msgs.append(
                {
                    "role": role if role in ("user", "assistant") else "user",
                    "content": content,
                }
            )

        system = "\n".join(system_texts) if system_texts else None
        return anthropic_msgs, system

    # ------------------------------------------------------------------
    # OpenAI-compatible normalization
    # ------------------------------------------------------------------

    def _normalize_for_openai(
        self, msgs: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Convert messages to OpenAI-compatible format.

        - Ensure ``reasoning_content`` appears before ``content`` for DeepSeek
          field-order expectations.
        - Ensure ``content`` is always present (OpenAI requires the key).
        """
        result: list[dict[str, Any]] = []
        for msg in msgs:
            api_msg = dict(msg)

            # DeepSeek reasoning_content ordering
            if (
                self.provider_name == "deepseek"
                and api_msg.get("role") == "assistant"
                and "reasoning_content" in api_msg
            ):
                rc = api_msg.pop("reasoning_content")
                api_msg = {"role": api_msg["role"], "reasoning_content": rc, **api_msg}

            # Ensure content is present
            if "content" not in api_msg:
                api_msg["content"] = ""

            result.append(api_msg)
        return result, None


class ResponseNormalizer:
    """Normalize provider responses to OpenAI-style chunks."""

    def __init__(self, api_protocol: str):
        self.api_protocol = api_protocol

    async def normalize_stream(self, response: Any) -> AsyncIterator[dict[str, Any]]:
        """Normalize a streaming response."""
        if self.api_protocol == "anthropic":
            async for chunk in self._normalize_anthropic_stream(response):
                yield chunk
        else:
            raise NormalizationError("OpenAI stream pass-through should be handled by the caller")

    def normalize_response(self, data: dict[str, Any]) -> dict[str, Any]:
        """Normalize a non-streaming response."""
        if self.api_protocol == "anthropic":
            return self._normalize_anthropic_response(data)

        # OpenAI-compatible: wrap the single response as one chunk
        api_choices = data.get("choices") or []
        api_choice = api_choices[0] if api_choices else {}
        api_message = api_choice.get("message") or {}
        chunk: dict[str, Any] = {
            "choices": [
                {
                    "delta": api_message,
                    "finish_reason": api_choice.get("finish_reason"),
                }
            ]
        }
        if "usage" in data:
            chunk["usage"] = data["usage"]
        return chunk

    # ------------------------------------------------------------------
    # Anthropic stream normalization
    # ------------------------------------------------------------------

    async def _normalize_anthropic_stream(self, response: Any) -> AsyncIterator[dict[str, Any]]:
        """Convert Anthropic SSE stream to OpenAI-style chunks."""
        current_blocks: dict[int, dict[str, Any]] = {}
        accumulated_usage: dict[str, int] = {}

        async def _aiter_lines_with_timeout(resp: Any, to: float):
            it = resp.aiter_lines().__aiter__()
            while True:
                try:
                    line = await asyncio.wait_for(it.__anext__(), timeout=to)
                    yield line
                except asyncio.TimeoutError:
                    raise NormalizationError(f"Stream read timed out: no data received for {to}s")
                except StopAsyncIteration:
                    break

        async for line in _aiter_lines_with_timeout(response, 120):
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                event = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type", "")

            if event_type == "message_start":
                msg = event.get("message", {})
                usage = msg.get("usage", {})
                if usage:
                    accumulated_usage["prompt_tokens"] = usage.get("input_tokens", 0)
                yield {"choices": [{"delta": {"role": "assistant"}, "finish_reason": None}]}
                continue

            if event_type == "content_block_start":
                idx = event.get("index", 0)
                block = event.get("content_block", {})
                block_type = block.get("type", "")
                current_blocks[idx] = {"type": block_type}
                if block_type == "tool_use":
                    tool_id = block.get("id", "")
                    tool_name = block.get("name", "")
                    yield {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": idx,
                                            "id": tool_id,
                                            "type": "function",
                                            "function": {
                                                "name": tool_name,
                                                "arguments": "",
                                            },
                                        }
                                    ]
                                },
                                "finish_reason": None,
                            }
                        ]
                    }
                continue

            if event_type == "content_block_delta":
                idx = event.get("index", 0)
                delta = event.get("delta", {})
                delta_type = delta.get("type", "")
                if delta_type == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        yield {"choices": [{"delta": {"content": text}, "finish_reason": None}]}
                elif delta_type == "thinking_delta":
                    thinking = delta.get("thinking", "")
                    if thinking:
                        yield {
                            "choices": [
                                {
                                    "delta": {"reasoning_content": thinking},
                                    "finish_reason": None,
                                }
                            ]
                        }
                elif delta_type == "input_json_delta":
                    partial = delta.get("partial_json", "")
                    if partial:
                        yield {
                            "choices": [
                                {
                                    "delta": {
                                        "tool_calls": [
                                            {
                                                "index": idx,
                                                "function": {"arguments": partial},
                                            }
                                        ]
                                    },
                                    "finish_reason": None,
                                }
                            ]
                        }
                continue

            if event_type == "content_block_stop":
                idx = event.get("index", 0)
                current_blocks.pop(idx, None)
                continue

            if event_type == "message_delta":
                delta = event.get("delta", {})
                stop_reason = delta.get("stop_reason", "")
                finish = "stop" if stop_reason in ("end_turn", "stop_sequence") else stop_reason
                usage = event.get("usage", {})
                if usage:
                    accumulated_usage["completion_tokens"] = usage.get("output_tokens", 0)
                chunk: dict[str, Any] = {"choices": [{"delta": {}, "finish_reason": finish}]}
                if accumulated_usage:
                    chunk["usage"] = {
                        "prompt_tokens": accumulated_usage.get("prompt_tokens", 0),
                        "completion_tokens": accumulated_usage.get("completion_tokens", 0),
                        "total_tokens": sum(accumulated_usage.values()),
                    }
                yield chunk
                continue

            if event_type == "message_stop":
                continue

    # ------------------------------------------------------------------
    # Anthropic non-stream normalization
    # ------------------------------------------------------------------

    def _normalize_anthropic_response(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert Anthropic non-streaming response to OpenAI-style chunk."""
        content_blocks = data.get("content", [])
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        reasoning_parts: list[str] = []

        for block in content_blocks:
            block_type = block.get("type", "")
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            elif block_type == "thinking":
                reasoning_parts.append(block.get("thinking", ""))
            elif block_type == "tool_use":
                tool_input = block.get("input", {})
                tool_calls.append(
                    {
                        "id": block.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": (
                                json.dumps(tool_input)
                                if isinstance(tool_input, dict)
                                else str(tool_input)
                            ),
                        },
                    }
                )

        delta: dict[str, Any] = {"role": "assistant"}
        if text_parts:
            delta["content"] = "".join(text_parts)
        if reasoning_parts:
            delta["reasoning_content"] = "".join(reasoning_parts)
        if tool_calls:
            delta["tool_calls"] = tool_calls

        stop_reason = data.get("stop_reason", "")
        finish = "stop" if stop_reason in ("end_turn", "stop_sequence") else stop_reason

        chunk: dict[str, Any] = {"choices": [{"delta": delta, "finish_reason": finish}]}

        usage = data.get("usage", {})
        if usage:
            chunk["usage"] = {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            }

        return chunk
