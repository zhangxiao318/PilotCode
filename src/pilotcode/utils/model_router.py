"""Multi-model routing for cost and performance optimization.

Following Claude Code's approach of routing different tasks to different models:
- Simple/quick tasks (title generation, binary decisions) → fast/cheap models
- Complex tasks (code generation, analysis) → powerful models
"""

import os
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, AsyncIterator

from .model_client import ModelClient, get_model_client


class ModelTier(Enum):
    """Model tiers for different use cases."""
    FAST = auto()      # Fast/cheap models for simple tasks (Haiku equivalent)
    BALANCED = auto()  # Balanced performance/cost (Sonnet equivalent)
    POWERFUL = auto()  # Most capable models (Opus equivalent)


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


# Default model configurations
DEFAULT_MODELS: dict[str, ModelConfig] = {
    # Fast tier (Haiku-like)
    "fast": ModelConfig(
        name=os.environ.get("PILOTCODE_FAST_MODEL", "haiku"),
        tier=ModelTier.FAST,
        context_window=200_000,
        cost_per_1k_input=0.00025,
        cost_per_1k_output=0.00125,
        supports_tools=True,
    ),
    # Balanced tier (Sonnet-like)
    "balanced": ModelConfig(
        name=os.environ.get("PILOTCODE_BALANCED_MODEL", "sonnet"),
        tier=ModelTier.BALANCED,
        context_window=200_000,
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
        supports_tools=True,
        supports_vision=True,
    ),
    # Powerful tier (Opus-like)
    "powerful": ModelConfig(
        name=os.environ.get("PILOTCODE_POWERFUL_MODEL", "opus"),
        tier=ModelTier.POWERFUL,
        context_window=200_000,
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.075,
        supports_tools=True,
        supports_vision=True,
    ),
    # Default model
    "default": ModelConfig(
        name=os.environ.get("PILOTCODE_DEFAULT_MODEL", "default"),
        tier=ModelTier.BALANCED,
        context_window=200_000,
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
        supports_tools=True,
    ),
}


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
        
        # Find model for tier
        for key, config in self.models.items():
            if config.tier == tier:
                return config
        
        # Fallback to default
        return self.models.get("default", list(self.models.values())[0])
    
    def estimate_cost(
        self,
        task_type: TaskType,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """Estimate cost for a task.
        
        Returns:
            Estimated cost in USD
        """
        model = self.get_model_for_task(task_type)
        input_cost = (input_tokens / 1000) * model.cost_per_1k_input
        output_cost = (output_tokens / 1000) * model.cost_per_1k_output
        return input_cost + output_cost
    
    async def route_query(
        self,
        task_type: TaskType,
        system_prompt: str,
        user_prompt: str,
        **kwargs
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
        self,
        task_type: TaskType,
        system_prompt: str,
        user_prompt: str,
        **kwargs
    ) -> AsyncIterator[str]:
        """Route a streaming query to the appropriate model."""
        model = self.get_model_for_task(task_type)
        client = self._get_client(model.name)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        async for chunk in client.chat_completion_stream(messages, **kwargs):
            yield chunk


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
        stream=False
    )
    
    content = response.get("content", "")
    if content:
        title = content.strip().strip('"').strip("'")
        if len(title) > max_length:
            title = title[:max_length-3] + "..."
        return title
    
    # Fallback
    return description[:max_length] if len(description) <= max_length else description[:max_length-3] + "..."


async def binary_decision(
    question: str,
    context: str | None = None
) -> bool:
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
        stream=False
    )
    
    content = response.get("content", "").strip().upper()
    return content.startswith("YES") or content == "TRUE" or content == "1"


async def simple_classify(
    text: str,
    categories: list[str]
) -> str:
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
        stream=False
    )
    
    content = response.get("content", "").strip()
    
    # Find matching category (case-insensitive)
    content_lower = content.lower()
    for category in categories:
        if category.lower() in content_lower or content_lower in category.lower():
            return category
    
    # Fallback to first category if no match
    return categories[0] if categories else "unknown"


async def quick_summarize(
    text: str,
    max_sentences: int = 3
) -> str:
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
        stream=False
    )
    
    return response.get("content", "").strip()
