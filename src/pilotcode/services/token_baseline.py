"""Token baseline measurement for fresh sessions.

Measures the token consumption of a session before any user work:
- System prompt (instructions, environment context)
- Tool definitions (schema descriptions, parameters)
- Runtime context (OS, cwd, git status, etc.)

This helps users understand how their context budget is allocated
and detect when tool bloat or prompt inflation is eating into
the usable conversation space.

Reference: Claude Code's Fresh-Session Token Baseline (~31K tokens).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BaselineBreakdown:
    """Token breakdown for a fresh session baseline."""

    system_prompt: int = 0
    tool_definitions: int = 0
    runtime_context: int = 0
    total: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "system_prompt": self.system_prompt,
            "tool_definitions": self.tool_definitions,
            "runtime_context": self.runtime_context,
            "total": self.total,
        }


@dataclass
class TokenBaseline:
    """Measured token baseline for a session."""

    breakdown: BaselineBreakdown = field(default_factory=BaselineBreakdown)
    context_window: int = 0
    max_output_tokens: int = 0
    usable_context: int = 0
    measured_at: str = ""
    model_name: str = ""

    @property
    def baseline_percentage(self) -> float:
        """Baseline as percentage of usable context."""
        if self.usable_context <= 0:
            return 0.0
        return (self.breakdown.total / self.usable_context) * 100

    @property
    def remaining_for_conversation(self) -> int:
        """Tokens remaining for actual conversation after baseline."""
        return max(0, self.usable_context - self.breakdown.total)

    def to_dict(self) -> dict[str, Any]:
        return {
            "breakdown": self.breakdown.to_dict(),
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "usable_context": self.usable_context,
            "baseline_percentage": round(self.baseline_percentage, 1),
            "remaining_for_conversation": self.remaining_for_conversation,
            "measured_at": self.measured_at,
            "model_name": self.model_name,
        }

    def report(self) -> str:
        """Generate a human-readable baseline report."""
        lines = [
            f"Token Baseline Report ({self.model_name})",
            f"  Context window:      {self.context_window:,} tokens",
            f"  Max output:          {self.max_output_tokens:,} tokens",
            f"  Usable context:      {self.usable_context:,} tokens",
            "",
            "  Baseline breakdown:",
            f"    System prompt:     {self.breakdown.system_prompt:,} tokens",
            f"    Tool definitions:  {self.breakdown.tool_definitions:,} tokens",
            f"    Runtime context:   {self.breakdown.runtime_context:,} tokens",
            "    ─────────────────────────────",
            f"    Total baseline:    {self.breakdown.total:,} tokens ({self.baseline_percentage:.1f}%)",
            "",
            f"  Remaining for conversation: {self.remaining_for_conversation:,} tokens",
        ]
        return "\n".join(lines)


class TokenBaselineMeasurer:
    """Measures token baseline for a fresh session."""

    def __init__(self, estimator: Any | None = None):
        self._estimator = estimator

    def measure(
        self,
        system_prompt: str,
        tools: list[Any],
        runtime_context: str,
        context_window: int,
        max_output_tokens: int,
        model_name: str = "",
    ) -> TokenBaseline:
        """Measure token baseline for the given configuration.

        Args:
            system_prompt: The full system prompt text.
            tools: List of tool definitions (will be serialized to JSON).
            runtime_context: Runtime context text (OS, cwd, etc.).
            context_window: Total context window size.
            max_output_tokens: Max output tokens reserved.
            model_name: Name of the model for reporting.

        Returns:
            TokenBaseline with full breakdown.
        """
        from datetime import datetime, timezone

        # Estimate system prompt tokens
        sys_tokens = self._estimate_text(system_prompt)

        # Estimate tool definition tokens
        tool_tokens = self._estimate_tools(tools)

        # Estimate runtime context tokens
        runtime_tokens = self._estimate_text(runtime_context)

        usable = max(1, context_window - max_output_tokens)

        breakdown = BaselineBreakdown(
            system_prompt=sys_tokens,
            tool_definitions=tool_tokens,
            runtime_context=runtime_tokens,
            total=sys_tokens + tool_tokens + runtime_tokens,
        )

        return TokenBaseline(
            breakdown=breakdown,
            context_window=context_window,
            max_output_tokens=max_output_tokens,
            usable_context=usable,
            measured_at=datetime.now(timezone.utc).isoformat(),
            model_name=model_name,
        )

    def _estimate_text(self, text: str) -> int:
        """Estimate tokens for plain text."""
        if self._estimator is not None and hasattr(self._estimator, "estimate"):
            try:
                return self._estimator.estimate(text)
            except Exception:
                pass
        # Fallback: ~4 chars per token for English/code
        return max(1, len(text) // 4)

    def _estimate_tools(self, tools: list[Any]) -> int:
        """Estimate tokens for tool definitions."""
        import json

        total = 0
        for tool in tools:
            try:
                if hasattr(tool, "to_dict"):
                    schema = json.dumps(tool.to_dict(), ensure_ascii=False)
                elif hasattr(tool, "model_json_schema"):
                    schema = json.dumps(tool.model_json_schema(), ensure_ascii=False)
                elif hasattr(tool, "input_schema"):
                    schema = json.dumps(tool.input_schema.model_json_schema(), ensure_ascii=False)
                else:
                    schema = json.dumps(tool, ensure_ascii=False, default=str)
                total += self._estimate_text(schema)
                total += 4  # per-tool struct overhead
            except Exception:
                total += 500  # fallback per tool
        return total


# Global baseline cache (measured once per session)
_session_baselines: dict[str, TokenBaseline] = {}


def get_session_baseline(session_id: str) -> TokenBaseline | None:
    """Get previously measured baseline for a session."""
    return _session_baselines.get(session_id)


def set_session_baseline(session_id: str, baseline: TokenBaseline) -> None:
    """Store measured baseline for a session."""
    _session_baselines[session_id] = baseline
