"""Mock LLM client for testing without real API calls."""

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable
from uuid import uuid4

from pilotcode.utils.model_client import ModelClient, Message as APIMessage


def _to_api_message(msg: APIMessage | dict[str, Any]) -> APIMessage:
    """Normalize a message to APIMessage dataclass."""
    if isinstance(msg, APIMessage):
        return msg
    return APIMessage(
        role=msg["role"],
        content=msg.get("content"),
        tool_calls=msg.get("tool_calls"),
        tool_call_id=msg.get("tool_call_id"),
        name=msg.get("name"),
        reasoning_content=msg.get("reasoning_content"),
    )


@dataclass
class MockLLMResponse:
    """A single response from the mock LLM."""

    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = "stop"

    @classmethod
    def with_tool_call(
        cls,
        tool_name: str,
        arguments: dict[str, Any],
        content: str = "",
    ) -> "MockLLMResponse":
        """Create a response that calls a tool."""
        return cls(
            content=content,
            tool_calls=[
                {
                    "id": f"call_{uuid4().hex[:12]}",
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(arguments),
                    },
                }
            ],
            finish_reason="tool_calls",
        )

    @classmethod
    def with_text(cls, text: str) -> "MockLLMResponse":
        """Create a simple text response."""
        return cls(content=text, finish_reason="stop")


class MockModelClient(ModelClient):
    """Mock model client for testing.

    Usage:
        client = MockModelClient()
        client.set_responses([
            MockLLMResponse.with_tool_call("Bash", {"command": "echo hello"}),
            MockLLMResponse.with_text("Done!"),
        ])

        # Then use with query engine
    """

    def __init__(self):
        # Don't call super().__init__() to avoid creating httpx client
        self.api_key = "test-key"
        self.base_url = "http://localhost:9999"
        self.model = "mock-model"
        self._responses: list[MockLLMResponse] = []
        self._response_index: int = 0
        self._history: list[list[APIMessage]] = []
        self._call_count: int = 0
        self._on_chat_completion: Callable | None = None

    def set_responses(self, responses: list[MockLLMResponse]) -> None:
        """Set the sequence of responses to return."""
        self._responses = list(responses)
        self._response_index = 0

    def add_response(self, response: MockLLMResponse) -> None:
        """Add a single response to the queue."""
        self._responses.append(response)

    def get_history(self) -> list[list[APIMessage]]:
        """Get all chat completion calls made."""
        return self._history

    def get_last_messages(self) -> list[APIMessage] | None:
        """Get the messages from the most recent call."""
        if not self._history:
            return None
        return self._history[-1]

    @property
    def call_count(self) -> int:
        """Number of times chat_completion was called."""
        return self._call_count

    def set_on_chat_completion(self, callback: Callable) -> None:
        """Set a callback invoked on every chat_completion call."""
        self._on_chat_completion = callback

    async def chat_completion(
        self,
        messages: list[APIMessage] | list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = True,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield mock response chunks."""
        self._call_count += 1
        self._history.append([_to_api_message(m) for m in messages])

        if self._on_chat_completion:
            self._on_chat_completion(messages, tools)

        if self._response_index >= len(self._responses):
            # Default empty response if queue exhausted
            response = MockLLMResponse(content="", finish_reason="stop")
        else:
            response = self._responses[self._response_index]
            self._response_index += 1

        if stream:
            # Yield content in chunks to simulate streaming
            chunk_size = 4
            content = response.content
            for i in range(0, len(content), chunk_size):
                part = content[i : i + chunk_size]
                yield {
                    "choices": [
                        {
                            "delta": {"content": part},
                            "finish_reason": None,
                        }
                    ]
                }

            # Yield tool calls if any
            if response.tool_calls:
                for i, tc in enumerate(response.tool_calls):
                    yield {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": i,
                                            "id": tc["id"],
                                            "function": {
                                                "name": tc["function"]["name"],
                                                "arguments": tc["function"]["arguments"],
                                            },
                                        }
                                    ]
                                },
                                "finish_reason": None,
                            }
                        ]
                    }

            # Final chunk with finish_reason
            yield {
                "choices": [
                    {
                        "delta": {},
                        "finish_reason": response.finish_reason,
                    }
                ]
            }
        else:
            yield {
                "choices": [
                    {
                        "delta": {
                            "content": response.content,
                            "tool_calls": response.tool_calls or None,
                        },
                        "finish_reason": response.finish_reason,
                    }
                ]
            }

    async def close(self) -> None:
        """No-op for mock client."""
        pass
