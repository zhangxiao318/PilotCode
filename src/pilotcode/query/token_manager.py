"""Token management for QueryEngine.

Encapsulates token counting, estimation, baseline measurement,
overflow detection, and cost tracking.
"""

from __future__ import annotations

import json
import time
import hashlib
from dataclasses import dataclass
from typing import Any, Callable

from ..services.token_baseline import (
    TokenBaselineMeasurer,
    set_session_baseline,
    get_session_baseline,
)
from ..services.token_estimation import TokenEstimator
from ..services.precise_tokenizer import get_precise_tokenizer


@dataclass
class TokenUsage:
    """OpenCode-style token usage breakdown."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0

    @property
    def adjusted_prompt_tokens(self) -> int:
        return max(0, self.prompt_tokens - self.cache_read_tokens - self.cache_write_tokens)

    @property
    def output_tokens(self) -> int:
        return max(0, self.completion_tokens - self.reasoning_tokens)


class TokenManager:
    """Manages token counting, estimation, and budget tracking."""

    def __init__(
        self,
        session_id: str,
        context_window: int,
        max_output_tokens: int,
        base_url: str,
        model_name: str,
        tools: list[Any],
        messages_ref: list[Any],
        build_system_fn: Callable[[], Any],
        get_runtime_fn: Callable[[], str],
        get_app_state_fn: Callable[[], Any] | None = None,
        set_app_state_fn: Callable[[Callable[[Any], Any]], None] | None = None,
    ):
        self.session_id = session_id
        self.context_window = context_window
        self.max_output_tokens = max_output_tokens
        self.usable_context = max(1, context_window - max_output_tokens)
        self.model_name = model_name
        self.tools = tools
        self.messages = messages_ref  # reference to QueryEngine.messages
        self._build_system_message = build_system_fn
        self._get_runtime_context = get_runtime_fn
        self._get_app_state = get_app_state_fn
        self._set_app_state = set_app_state_fn

        # Estimators
        self._precise_tokenizer = get_precise_tokenizer(base_url=base_url, model_name=model_name)
        self._token_estimator = TokenEstimator(
            base_url=base_url,
            model_name=model_name,
            precise_tokenizer=self._precise_tokenizer,
        )

        # Caches / state
        self._last_api_usage: TokenUsage | None = None
        self._last_api_usage_hash: str | None = None
        self._last_precise_count: int | None = None
        self._last_precise_count_at: float = 0.0
        self._last_precise_count_hash: str | None = None
        # Exact base + delta estimation: store last known exact count and
        # only estimate the delta (new messages) on top of it.
        self._exact_prompt_base: int = 0  # Last exact prompt token count
        self._exact_base_message_count: int = 0  # messages at that point

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def count_tokens(self) -> int:
        """Count tokens in current conversation.

        Priority:
        1. API-reported usage (ground truth, hash must match)
        2. Precise backend tokenizer (/tokenize endpoint)
        3. Exact base + delta estimation (last exact + estimate new messages)
        4. Pure heuristic estimation (fallback)
        """
        current_hash = self._compute_state_hash()

        # Priority 1: API-reported usage — cached, hash must match exactly.
        # This is the only path that returns the true API total.
        if self._last_api_usage and current_hash == self._last_api_usage_hash:
            return self._last_api_usage.total_tokens

        # Priority 2: Precise tokenizer
        # Fast path: conversation state hasn't changed since last count.
        if self._last_precise_count is not None and current_hash == self._last_precise_count_hash:
            return self._last_precise_count

        # State changed: re-compute precise count. The precise tokenizer has
        # its own per-text cache, so repeated calls for unchanged text are cheap.
        now = time.monotonic()
        precise = self._count_with_precise_tokenizer()
        if precise is not None:
            self._last_precise_count = precise
            self._last_precise_count_at = now
            self._last_precise_count_hash = current_hash
            self._save_exact_base(precise)
            return precise

        # Priority 3: Cumulative from last known exact base + estimated delta.
        # When API reported usage, _save_exact_base(prompt_tok) was called,
        # so _exact_prompt_base holds the last API prompt_tokens as base.
        # When precise tokenizer ran earlier, it also saves the base.
        # Delta estimates only messages added since that base measurement.
        if self._exact_prompt_base > 0:
            delta = self._estimate_messages_delta()
            return max(self._exact_prompt_base + delta, self._exact_prompt_base)

        # Priority 4: Full heuristic fallback
        return self._heuristic_count_tokens()

    def _save_exact_base(self, count: int) -> None:
        """Save an exact token count as the base for delta estimation."""
        self._exact_prompt_base = count
        self._exact_base_message_count = len(self.messages)

    def _estimate_messages_delta(self) -> int:
        """Estimate tokens for new messages since last exact base."""
        extra = 0
        # Handle the case where messages were cleared or reset
        if self._exact_base_message_count >= len(self.messages):
            # If no new messages or messages were cleared, return 0
            return 0
        # Calculate delta from the base message count to current length
        for i in range(self._exact_base_message_count, len(self.messages)):
            m = self.messages[i]
            if hasattr(m, "content"):
                content = str(m.content)
            elif hasattr(m, "name") and hasattr(m, "input"):
                content = f"Tool: {m.name}\\nInput: {m.input}"
            else:
                content = str(m)
            extra += self._token_estimator.estimate_message(content)
        return extra

    def reset_cache(self) -> None:
        """Reset all cached token counts.

        Called after clear_history() so the next count_tokens() call
        recomputes from the (now empty) message list instead of returning
        stale cached values.
        """
        self._last_api_usage = None
        self._last_api_usage_hash = None
        self._last_precise_count = None
        self._last_precise_count_at = 0.0
        self._last_precise_count_hash = None
        self._exact_prompt_base = 0
        self._exact_base_message_count = 0

    def is_overflow(self) -> bool:
        """Check if conversation exceeds usable context."""
        count = self.count_tokens()
        reserved = min(20_000, self.max_output_tokens)
        usable = self.context_window - reserved
        if usable <= 0:
            usable = self.usable_context
        return count >= usable

    def get_token_budget(self) -> dict[str, Any]:
        """Get current token budget status, including baseline info."""
        budget = self._token_estimator.get_budget_status(self.count_tokens(), self.usable_context)
        baseline = get_session_baseline(self.session_id)
        if baseline:
            budget["baseline_tokens"] = baseline.breakdown.total
            budget["baseline_pct"] = round(baseline.baseline_percentage, 1)
            budget["remaining_after_baseline"] = baseline.remaining_for_conversation
        return budget

    def get_token_baseline(self) -> dict[str, Any] | None:
        """Get the measured token baseline for this session."""
        baseline = get_session_baseline(self.session_id)
        return baseline.to_dict() if baseline else None

    def get_token_baseline_report(self) -> str:
        """Get a human-readable token baseline report."""
        baseline = get_session_baseline(self.session_id)
        if baseline:
            return baseline.report()
        return "Token baseline not yet measured."

    def track_cost(self, tokens: int, cost_usd: float) -> None:
        """Track cost for this session.

        Accumulates into app_state for reporting.
        """
        if self._get_app_state:
            try:
                state = self._get_app_state()
                state.total_tokens += tokens
                state.total_cost_usd += cost_usd
                if self._set_app_state:
                    self._set_app_state(lambda s: state)
            except Exception:
                pass

    def record_api_usage(self, usage: dict[str, Any]) -> None:
        """Record API-reported token usage from a stream chunk."""
        prompt_tok = usage.get("prompt_tokens", 0)
        comp_tok = usage.get("completion_tokens", 0)
        total_tok = usage.get("total_tokens", 0)

        ptd = usage.get("prompt_tokens_details") or {}
        cache_read = ptd.get("cached_tokens", 0) if isinstance(ptd, dict) else 0
        cache_write = usage.get("cache_creation_input_tokens", 0)

        ctd = usage.get("completion_tokens_details") or {}
        reasoning = ctd.get("reasoning_tokens", 0) if isinstance(ctd, dict) else 0

        self._last_api_usage = TokenUsage(
            prompt_tokens=prompt_tok,
            completion_tokens=comp_tok,
            total_tokens=total_tok or (prompt_tok + comp_tok),
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            reasoning_tokens=reasoning,
        )
        self._last_api_usage_hash = self._compute_state_hash()

        # Save exact prompt base for delta estimation
        # Always save base to maintain consistency, even when prompt_tok is 0
        # This ensures token tracking continues to work properly
        self._save_exact_base(prompt_tok)

        # Also forward to external cost tracker
        try:
            from ..commands.cost_cmd import track_usage

            track_usage(self._last_api_usage.total_tokens, 0.0)
        except Exception:
            pass

    def measure_baseline(self) -> None:
        """Measure and cache the fresh-session token baseline."""
        # Skip baseline measurement when no backend is available to avoid
        # hanging on transformers import or unreachable tokenizer endpoints.
        # The baseline is best-effort; heuristic counting works fine without it.
        try:
            measurer = TokenBaselineMeasurer(estimator=self._token_estimator)
            baseline = measurer.measure(
                system_prompt=self._build_system_message().content,
                tools=self.tools,
                runtime_context=self._get_runtime_context(),
                context_window=self.context_window,
                max_output_tokens=self.max_output_tokens,
                model_name=self.model_name or "unknown",
            )
            set_session_baseline(self.session_id, baseline)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_state_hash(self) -> str:
        """Cheap hash of current conversation state."""
        parts: list[str] = []
        for m in self.messages:
            if hasattr(m, "content"):
                parts.append(f"{getattr(m, 'type', 'user')}:{m.content}")
            elif hasattr(m, "name") and hasattr(m, "input"):
                parts.append(f"tool:{m.name}:{m.input}")
            else:
                parts.append(str(m))
        if self.tools:
            try:
                parts.append(
                    json.dumps(
                        [t.to_dict() if hasattr(t, "to_dict") else t for t in self.tools],
                        sort_keys=True,
                    )
                )
            except Exception:
                pass
        # Use hashlib instead of hash() to avoid hash() returning 0
        # which was causing the token counting to not update properly
        combined = "|".join(parts)
        return hashlib.md5(combined.encode("utf-8")).hexdigest()

    def _count_with_precise_tokenizer(self) -> int | None:
        """Count tokens using the backend's /tokenize endpoint."""
        try:
            api_msgs: list[dict[str, Any]] = []
            system_msg = self._build_system_message()
            api_msgs.append({"role": "system", "content": system_msg.content})

            for m in self.messages:
                if hasattr(m, "content"):
                    api_msgs.append({"role": getattr(m, "type", "user"), "content": str(m.content)})
                elif hasattr(m, "name") and hasattr(m, "input"):
                    api_msgs.append(
                        {
                            "role": "assistant",
                            "content": f"Tool: {m.name}\\nInput: {m.input}",
                        }
                    )

            api_tools: list[dict[str, Any]] | None = None
            if self.tools:
                api_tools = []
                for tool in self.tools:
                    try:
                        if hasattr(tool, "to_dict"):
                            api_tools.append(tool.to_dict())
                        elif isinstance(tool, dict):
                            api_tools.append(tool)
                        else:
                            api_tools.append(json.loads(json.dumps(tool, default=str)))
                    except Exception:
                        continue
                if not api_tools:
                    api_tools = None

            count = self._precise_tokenizer.count_messages_with_tools(api_msgs, tools=api_tools)
            if count is not None:
                return count

            # Fallback: count text + tools individually
            total = 0
            total += self._precise_tokenizer.count_text(
                system_msg.content
            ) or self._token_estimator.estimate(system_msg.content)
            for m in self.messages:
                content = str(getattr(m, "content", getattr(m, "name", "")))
                total += self._precise_tokenizer.count_text(
                    content
                ) or self._token_estimator.estimate(content)

            if api_tools:
                for tool in api_tools:
                    try:
                        schema = json.dumps(tool, ensure_ascii=False)
                        total += self._precise_tokenizer.count_text(
                            schema
                        ) or self._token_estimator.estimate(schema)
                    except Exception:
                        total += 500
            return total
        except Exception:
            return None

    def _heuristic_count_tokens(self) -> int:
        """Pure heuristic token count (fallback)."""
        # Cloud API detection: if base_url is set and no local tokenize
        # backend was detected, assume we're talking to a remote API
        # whose token overhead may differ from local backends.
        is_cloud_api = bool(self._precise_tokenizer and self._precise_tokenizer.base_url)

        system_msg = self._build_system_message()
        return self._token_estimator.estimate_conversation(
            system_msg=system_msg.content,
            messages=self.messages,
            tools=self.tools,
            is_cloud_api=is_cloud_api,
        )
