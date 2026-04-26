"""Multi-model routing for cost and performance optimization.

Following Claude Code's approach of routing different tasks to different models:
- Simple/quick tasks (title generation, binary decisions) → fast/cheap models
- Complex tasks (code generation, analysis) → powerful models
"""

import os
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, AsyncIterator

from .model_client import ModelClient
from .models_config import get_all_models, get_model_info, ModelInfo


class ModelTier(Enum):
    """Model tiers for different use cases."""

    FAST = auto()  # Fast/cheap models for simple tasks
    BALANCED = auto()  # Balanced performance/cost
    POWERFUL = auto()  # Most capable models


class TaskType(Enum):
    """Types of tasks for routing decisions."""

    # Fast tier tasks
    TITLE_GENERATION = "title_generation"
    BINARY_DECISION = "binary_decision"
    SIMPLE_CLASSIFICATION = "simple_classification"
    TEXT_SUMMARIZATION_SHORT = "text_summarization_short"

    # Balanced tier tasks
    CODE_COMPLETION = "code_completion"
    CODE_REVIEW = "code_review"
    BUG_ANALYSIS = "bug_analysis"
    GENERAL_QUESTION = "general_question"

    # Powerful tier tasks
    COMPLEX_ARCHITECTURE = "complex_architecture"
    LARGE_REFACTORING = "large_refactoring"
    COMPREHENSIVE_ANALYSIS = "comprehensive_analysis"
    MULTI_FILE_CHANGE = "multi_file_change"


@dataclass
class ModelConfig:
    """Configuration for a model."""

    name: str
    tier: ModelTier
    context_window: int
    cost_per_1k_input: float  # USD
    cost_per_1k_output: float  # USD
    supports_tools: bool = True
    supports_vision: bool = False


def _infer_tier(model_info: ModelInfo) -> ModelTier:
    """Infer model tier from model metadata."""
    name = model_info.name.lower()
    # Fast tier indicators
    if any(k in name for k in ("flash", "lite", "mini", "haiku", "fast")):
        return ModelTier.FAST
    # Powerful tier indicators
    if any(k in name for k in ("pro", "max", "opus", "gpt-4o", "claude-3-5", "claude-4")):
        return ModelTier.POWERFUL
    # Balanced is the default
    return ModelTier.BALANCED


def _build_default_models() -> dict[str, ModelConfig]:
    """Build DEFAULT_MODELS from the user's *configured* models only.

    models.json contains metadata for 15+ providers, but most users only
    have API keys for 1-3 of them. We filter to models that the user has
    actually configured (api_key present in settings.json, model_overrides,
    or environment variables).
    """
    from .config import get_global_config

    config = get_global_config()
    all_models = get_all_models()

    # Determine which models the user has actually configured
    def _is_configured(name: str) -> bool:
        """Check if user has provided an api_key for this model."""
        # Explicit override in settings.json?
        override = config.model_overrides.get(name, {})
        if override.get("api_key"):
            return True
        # Is this the default model and global api_key is set?
        if name == config.default_model and config.api_key:
            return True
        # Environment variable for this provider?
        info = get_model_info(name)
        if info and info.env_key:
            import os

            if os.environ.get(info.env_key):
                return True
        return False

    # If no models.json, fall back to env vars
    if not all_models:
        return {
            "fast": ModelConfig(
                name=os.environ.get("PILOTCODE_FAST_MODEL", "deepseek-v4-flash"),
                tier=ModelTier.FAST,
                context_window=1_000_000,
                cost_per_1k_input=0.0005,
                cost_per_1k_output=0.0015,
                supports_tools=True,
            ),
            "balanced": ModelConfig(
                name=os.environ.get("PILOTCODE_BALANCED_MODEL", "deepseek"),
                tier=ModelTier.BALANCED,
                context_window=1_000_000,
                cost_per_1k_input=0.001,
                cost_per_1k_output=0.002,
                supports_tools=True,
            ),
            "powerful": ModelConfig(
                name=os.environ.get("PILOTCODE_POWERFUL_MODEL", "deepseek-v4-pro"),
                tier=ModelTier.POWERFUL,
                context_window=1_000_000,
                cost_per_1k_input=0.003,
                cost_per_1k_output=0.006,
                supports_tools=True,
            ),
            "default": ModelConfig(
                name=os.environ.get("PILOTCODE_DEFAULT_MODEL", "deepseek"),
                tier=ModelTier.BALANCED,
                context_window=1_000_000,
                cost_per_1k_input=0.001,
                cost_per_1k_output=0.002,
                supports_tools=True,
            ),
        }

    # Group *configured* models by inferred tier
    by_tier: dict[ModelTier, list[ModelInfo]] = {
        ModelTier.FAST: [],
        ModelTier.BALANCED: [],
        ModelTier.POWERFUL: [],
    }
    for key, info in all_models.items():
        if info.disabled:
            continue
        if not _is_configured(key):
            continue
        tier = _infer_tier(info)
        by_tier[tier].append(info)

    # The user's default model is the ultimate fallback
    default_model_key = config.default_model or "deepseek"
    default_info = get_model_info(default_model_key)
    default_tier = _infer_tier(default_info) if default_info else ModelTier.BALANCED

    def _pick(tier: ModelTier, fallback_name: str) -> ModelConfig:
        candidates = by_tier.get(tier, [])
        info = candidates[0] if candidates else get_model_info(fallback_name)
        if info is None:
            info = default_info
        if info is None:
            info = list(all_models.values())[0]
        # Tier-specific cost defaults
        cost_map = {
            ModelTier.FAST: (0.0005, 0.0015),
            ModelTier.BALANCED: (0.003, 0.015),
            ModelTier.POWERFUL: (0.015, 0.075),
        }
        in_cost, out_cost = cost_map.get(tier, (0.003, 0.015))
        return ModelConfig(
            name=info.default_model or info.name,
            tier=tier,
            context_window=info.context_window,
            cost_per_1k_input=in_cost,
            cost_per_1k_output=out_cost,
            supports_tools=info.supports_tools,
            supports_vision=info.supports_vision,
        )

    return {
        "fast": _pick(ModelTier.FAST, default_model_key),
        "balanced": _pick(ModelTier.BALANCED, default_model_key),
        "powerful": _pick(ModelTier.POWERFUL, default_model_key),
        "default": _pick(default_tier, default_model_key),
    }


# Lazily evaluated so that models.json is loaded at import time
DEFAULT_MODELS: dict[str, ModelConfig] = _build_default_models()


# Task to tier mapping
TASK_ROUTING: dict[TaskType, ModelTier] = {
    # Fast tasks
    TaskType.TITLE_GENERATION: ModelTier.FAST,
    TaskType.BINARY_DECISION: ModelTier.FAST,
    TaskType.SIMPLE_CLASSIFICATION: ModelTier.FAST,
    TaskType.TEXT_SUMMARIZATION_SHORT: ModelTier.FAST,
    # Balanced tasks
    TaskType.CODE_COMPLETION: ModelTier.BALANCED,
    TaskType.CODE_REVIEW: ModelTier.BALANCED,
    TaskType.BUG_ANALYSIS: ModelTier.BALANCED,
    TaskType.GENERAL_QUESTION: ModelTier.BALANCED,
    # Powerful tasks
    TaskType.COMPLEX_ARCHITECTURE: ModelTier.POWERFUL,
    TaskType.LARGE_REFACTORING: ModelTier.POWERFUL,
    TaskType.COMPREHENSIVE_ANALYSIS: ModelTier.POWERFUL,
    TaskType.MULTI_FILE_CHANGE: ModelTier.POWERFUL,
}


class ModelRouter:
    """Routes requests to appropriate models based on task type.

    Similar to Claude Code's internal model selection:
    - Simple tasks (title generation, binary feedback) use fast models
    - Complex tasks use powerful models
    """

    def __init__(self, models: dict[str, ModelConfig] | None = None):
        self.models = models or DEFAULT_MODELS
        self._clients: dict[str, ModelClient] = {}

    def _get_client(self, model_name: str) -> ModelClient:
        """Get or create model client for a model."""
        if model_name not in self._clients:
            self._clients[model_name] = ModelClient(
                model=model_name if model_name != "default" else None
            )
        return self._clients[model_name]

    def get_model_for_task(self, task_type: TaskType) -> ModelConfig:
        """Get the appropriate model for a task type."""
        tier = TASK_ROUTING.get(task_type, ModelTier.BALANCED)
        return self.get_model_for_tier(tier)

    def get_model_for_tier(self, tier: ModelTier) -> ModelConfig:
        """Get the model configured for a specific tier."""
        for key, config in self.models.items():
            if config.tier == tier:
                return config
        # Fallback to default
        return self.models.get("default", list(self.models.values())[0])

    def estimate_cost(self, task_type: TaskType, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost for a task.

        Returns:
            Estimated cost in USD
        """
        model = self.get_model_for_task(task_type)
        input_cost = (input_tokens / 1000) * model.cost_per_1k_input
        output_cost = (output_tokens / 1000) * model.cost_per_1k_output
        return input_cost + output_cost

    async def route_query(
        self, task_type: TaskType, system_prompt: str, user_prompt: str, **kwargs
    ) -> dict[str, Any]:
        """Route a query to the appropriate model.

        Args:
            task_type: Type of task for routing decision
            system_prompt: System prompt
            user_prompt: User prompt
            **kwargs: Additional arguments for the model

        Returns:
            Model response
        """
        model = self.get_model_for_task(task_type)
        client = self._get_client(model.name)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        return await client.chat_completion(messages, **kwargs)

    async def route_stream(
        self, task_type: TaskType, system_prompt: str, user_prompt: str, **kwargs
    ) -> AsyncIterator[str]:
        """Route a streaming query to the appropriate model."""
        model = self.get_model_for_task(task_type)
        client = self._get_client(model.name)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        async for chunk in client.chat_completion(messages, stream=True, **kwargs):
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            content = delta.get("content", "")
            if content:
                yield content

    async def broadcast(
        self,
        messages: list[dict[str, Any]],
        model_names: list[str],
        **kwargs,
    ) -> dict[str, Any]:
        """Send the same request to multiple models in parallel.

        Args:
            messages: OpenAI-compatible message list.
            model_names: List of model names to query.
            **kwargs: Extra arguments passed to each client's chat_completion.

        Returns:
            Dict mapping model name to the full response dict (non-streaming).
        """
        import asyncio

        async def _query_one(name: str) -> tuple[str, Any]:
            client = self._get_client(name)
            chunks = []
            async for chunk in client.chat_completion(messages, stream=False, **kwargs):
                chunks.append(chunk)
            # Non-streaming mode yields a single chunk with full response
            return name, chunks[0] if chunks else {}

        results = await asyncio.gather(
            *[_query_one(n) for n in model_names], return_exceptions=True
        )
        output: dict[str, Any] = {}
        for name, result in zip(model_names, results):
            if isinstance(result, Exception):
                output[name] = {"error": str(result)}
            else:
                output[name] = result[1]
        return output


# Global router instance
_router: ModelRouter | None = None


def get_model_router() -> ModelRouter:
    """Get global model router."""
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router


# Convenience functions for common fast operations


async def generate_title(description: str, max_length: int = 80) -> str:
    """Generate a concise title for a description (uses fast model).

    Following Claude Code's pattern of using Haiku for title generation.
    """
    router = get_model_router()

    system_prompt = (
        f"Generate a concise title (max {max_length} chars) that captures "
        "the key point of the input. Do not include quotes or prefixes. "
        "If you cannot generate a title, use 'Untitled'."
    )

    response = await router.route_query(
        task_type=TaskType.TITLE_GENERATION,
        system_prompt=system_prompt,
        user_prompt=description,
        stream=False,
    )

    content = response.get("content", "")
    if content:
        title = content.strip().strip('"').strip("'")
        if len(title) > max_length:
            title = title[: max_length - 3] + "..."
        return title

    # Fallback
    return (
        description[:max_length]
        if len(description) <= max_length
        else description[: max_length - 3] + "..."
    )


async def binary_decision(question: str, context: str | None = None) -> bool:
    """Make a binary yes/no decision (uses fast model).

    For simple boolean decisions that don't need powerful models.
    """
    router = get_model_router()

    system_prompt = (
        "You are a decision-making assistant. Respond with ONLY 'YES' or 'NO'. "
        "No explanation, no additional text."
    )

    user_prompt = question
    if context:
        user_prompt = f"Context: {context}\n\nQuestion: {question}"

    response = await router.route_query(
        task_type=TaskType.BINARY_DECISION,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        stream=False,
    )

    content = response.get("content", "").strip().upper()
    return content.startswith("YES") or content == "TRUE" or content == "1"


async def simple_classify(text: str, categories: list[str]) -> str:
    """Classify text into one of the given categories (uses fast model)."""
    router = get_model_router()

    categories_str = ", ".join(categories)
    system_prompt = (
        f"Classify the input into exactly one of these categories: {categories_str}. "
        "Respond with ONLY the category name. No other text."
    )

    response = await router.route_query(
        task_type=TaskType.SIMPLE_CLASSIFICATION,
        system_prompt=system_prompt,
        user_prompt=text,
        stream=False,
    )

    content = response.get("content", "").strip()

    # Find matching category (case-insensitive)
    content_lower = content.lower()
    for category in categories:
        if category.lower() in content_lower or content_lower in category.lower():
            return category

    # Fallback to first category if no match
    return categories[0] if categories else "unknown"


async def quick_summarize(text: str, max_sentences: int = 3) -> str:
    """Generate a quick summary (uses fast model).

    For short summaries where full model capability isn't needed.
    """
    router = get_model_router()

    system_prompt = (
        f"Summarize the following text in at most {max_sentences} sentences. "
        "Be concise and capture the main points."
    )

    response = await router.route_query(
        task_type=TaskType.TEXT_SUMMARIZATION_SHORT,
        system_prompt=system_prompt,
        user_prompt=text,
        stream=False,
    )

    return response.get("content", "").strip()
