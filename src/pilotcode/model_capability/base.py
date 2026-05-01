"""Benchmark infrastructure: result types, LLM calling, JSON extraction."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pilotcode.utils.model_client import get_model_client, Message


@dataclass
class BenchmarkResult:
    """Result of a single benchmark test."""

    test_name: str
    dimension: str
    sub_dimension: str
    score: float  # 0.0 - 1.0
    raw_output: str = ""
    error: str | None = None
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BenchmarkConnectionError(Exception):
    """Raised when the benchmark cannot reach the model API."""


def _is_connection_error(exc: Exception) -> bool:
    """Check if an exception indicates the model API is unreachable."""
    name = type(exc).__name__
    if name in ("ConnectError", "ConnectTimeout", "TimeoutException", "NetworkError"):
        return True
    if name in ("HTTPStatusError", "RemoteProtocolError"):
        return True
    msg = str(exc).lower()
    indicators = [
        "connection",
        "connect",
        "unreachable",
        "refused",
        "timeout",
        "name or service not known",
        "no route to host",
        "all connection attempts failed",
    ]
    return any(ind in msg for ind in indicators)


async def _call_llm(
    messages: list[Message],
    temperature: float = 0.3,
    max_tokens: int | None = None,
) -> str:
    """Helper to call LLM and accumulate response.

    ``max_tokens`` is not clamped downward – if a caller explicitly passes a
    value it is honoured so that the model can be as verbose as it needs to be
    to answer the prompt correctly.  When ``max_tokens`` is omitted the
    model's reported capability (or a safe fallback) is used so that backends
    with a tiny default (e.g. llama-server's 256) do not silently truncate
    output.

    Raises:
        BenchmarkConnectionError: If the API is unreachable.
    """
    from pilotcode.utils.models_config import get_model_max_tokens

    client = get_model_client()

    if max_tokens is None:
        model_max = get_model_max_tokens()
        if model_max > 0:
            max_tokens = model_max

    try:
        accumulated = ""
        async for chunk in client.chat_completion(
            messages=messages,
            temperature=temperature,
            stream=False,
            max_tokens=max_tokens,
        ):
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            c = delta.get("content")
            if c:
                accumulated += c
        return accumulated.strip()
    except Exception as e:
        if _is_connection_error(e):
            raise BenchmarkConnectionError(
                f"Cannot reach model API at {client.base_url}: {e}"
            ) from e
        raise


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extract JSON object from text.

    Uses balanced-brace scanning so that trailing text containing
    ``{...}`` (e.g. code examples, status markers) does not cause
    greedy-regex over-matching.
    """
    # 1. Direct parse
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown fences and re-parse
    stripped = text.strip()
    for prefix in ("```json", "```"):
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix) :].strip()
        if stripped.endswith("```"):
            stripped = stripped[:-3].strip()
    try:
        result = json.loads(stripped)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # 3. Balanced-brace scan
    for match in re.finditer(r"\{", text):
        start = match.start()
        depth = 1
        for i in range(start + 1, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        result = json.loads(candidate)
                        if isinstance(result, dict):
                            return result
                    except json.JSONDecodeError:
                        pass
                    break
    return None


def _score_bool(condition: bool) -> float:
    return 1.0 if condition else 0.0


def _extract_code(raw: str) -> str:
    """Strip markdown fences and surrounding whitespace."""
    code = raw.strip()
    code = re.sub(r"^```(?:python)?\s*", "", code)
    code = re.sub(r"\s*```$", "", code)
    return code
