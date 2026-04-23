"""Tests for model router."""

import pytest
from unittest.mock import AsyncMock, patch

from pilotcode.utils.model_router import (
    ModelRouter,
    ModelTier,
    TaskType,
    ModelConfig,
    get_model_router,
    generate_title,
    binary_decision,
    simple_classify,
    quick_summarize,
    DEFAULT_MODELS,
    TASK_ROUTING,
)


class TestModelTier:
    """Tests for ModelTier enum."""

    def test_tier_values(self):
        """Test tier enum values."""
        assert ModelTier.FAST is not None
        assert ModelTier.BALANCED is not None
        assert ModelTier.POWERFUL is not None


class TestTaskType:
    """Tests for TaskType enum."""

    def test_task_types(self):
        """Test all task types exist."""
        assert TaskType.TITLE_GENERATION.value == "title_generation"
        assert TaskType.BINARY_DECISION.value == "binary_decision"
        assert TaskType.CODE_COMPLETION.value == "code_completion"
        assert TaskType.COMPLEX_ARCHITECTURE.value == "complex_architecture"


class TestModelConfig:
    """Tests for ModelConfig dataclass."""

    def test_config_creation(self):
        """Test creating model config."""
        config = ModelConfig(
            name="test-model",
            tier=ModelTier.BALANCED,
            context_window=100_000,
            cost_per_1k_input=0.01,
            cost_per_1k_output=0.03,
            supports_tools=True,
            supports_vision=True,
        )

        assert config.name == "test-model"
        assert config.tier == ModelTier.BALANCED
        assert config.context_window == 100_000
        assert config.supports_tools is True

    def test_config_defaults(self):
        """Test config defaults."""
        config = ModelConfig(
            name="test",
            tier=ModelTier.FAST,
            context_window=100_000,
            cost_per_1k_input=0.01,
            cost_per_1k_output=0.03,
            supports_tools=False,
            supports_vision=False,
        )

        assert config.supports_tools is False
        assert config.supports_vision is False


class TestModelRouter:
    """Tests for ModelRouter."""

    def test_singleton(self):
        """Test that global router is singleton."""
        router1 = get_model_router()
        router2 = get_model_router()
        assert router1 is router2

    def test_get_model_for_task(self):
        """Test getting model for task type."""
        router = ModelRouter()

        # Fast tasks should return fast model
        fast_model = router.get_model_for_task(TaskType.TITLE_GENERATION)
        assert fast_model.tier == ModelTier.FAST

        # Powerful tasks should return powerful model
        powerful_model = router.get_model_for_task(TaskType.COMPLEX_ARCHITECTURE)
        assert powerful_model.tier == ModelTier.POWERFUL

    def test_estimate_cost(self):
        """Test cost estimation."""
        router = ModelRouter()

        # Title generation uses fast model (cheaper)
        cost = router.estimate_cost(TaskType.TITLE_GENERATION, 1000, 500)
        assert cost > 0

        # Store fast tier cost
        fast_cost = cost

        # Complex architecture uses powerful model (more expensive)
        cost = router.estimate_cost(TaskType.COMPLEX_ARCHITECTURE, 1000, 500)
        powerful_cost = cost

        # Powerful should be more expensive
        assert powerful_cost > fast_cost

    def test_all_tasks_have_routing(self):
        """Test that all task types have routing defined."""
        for task in TaskType:
            assert task in TASK_ROUTING, f"Task {task} has no routing"

    def test_default_models_structure(self):
        """Test default models structure."""
        assert "fast" in DEFAULT_MODELS
        assert "balanced" in DEFAULT_MODELS
        assert "powerful" in DEFAULT_MODELS
        assert "default" in DEFAULT_MODELS


class TestGenerateTitle:
    """Tests for generate_title function."""

    @pytest.mark.asyncio
    async def test_generate_title_basic(self):
        """Test basic title generation."""
        mock_response = {"content": "Bug Fix in User Authentication"}

        with patch.object(ModelRouter, "route_query", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response

            title = await generate_title("Fixed a bug where users couldn't login")

            assert title == "Bug Fix in User Authentication"
            mock.assert_called_once()

            # Check it uses fast tier
            call_args = mock.call_args
            assert call_args[1]["task_type"] == TaskType.TITLE_GENERATION

    @pytest.mark.asyncio
    async def test_generate_title_truncation(self):
        """Test that long titles are truncated."""
        mock_response = {"content": "A" * 100}

        with patch.object(ModelRouter, "route_query", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response

            title = await generate_title("Some description", max_length=50)

            assert len(title) <= 50

    @pytest.mark.asyncio
    async def test_generate_title_fallback(self):
        """Test fallback when model fails."""
        mock_response = {"content": ""}

        with patch.object(ModelRouter, "route_query", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response

            description = "Short description"
            title = await generate_title(description, max_length=20)

            # Should fallback to truncated description
            assert len(title) <= 20


class TestBinaryDecision:
    """Tests for binary_decision function."""

    @pytest.mark.asyncio
    async def test_binary_decision_yes(self):
        """Test yes decision."""
        mock_response = {"content": "YES"}

        with patch.object(ModelRouter, "route_query", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response

            result = await binary_decision("Is this a test?")

            assert result is True

    @pytest.mark.asyncio
    async def test_binary_decision_no(self):
        """Test no decision."""
        mock_response = {"content": "NO"}

        with patch.object(ModelRouter, "route_query", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response

            result = await binary_decision("Is this a test?")

            assert result is False

    @pytest.mark.asyncio
    async def test_binary_decision_with_context(self):
        """Test decision with context."""
        mock_response = {"content": "TRUE"}

        with patch.object(ModelRouter, "route_query", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response

            result = await binary_decision("Should we proceed?", context="The system is ready")

            assert result is True


class TestSimpleClassify:
    """Tests for simple_classify function."""

    @pytest.mark.asyncio
    async def test_classify_basic(self):
        """Test basic classification."""
        mock_response = {"content": "bug"}

        with patch.object(ModelRouter, "route_query", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response

            result = await simple_classify(
                "The app crashes when I click login", ["bug", "feature", "question"]
            )

            assert result == "bug"

    @pytest.mark.asyncio
    async def test_classify_case_insensitive(self):
        """Test case-insensitive matching."""
        mock_response = {"content": "FEATURE"}

        with patch.object(ModelRouter, "route_query", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response

            result = await simple_classify("Add dark mode", ["bug", "feature", "question"])

            assert result == "feature"

    @pytest.mark.asyncio
    async def test_classify_fallback(self):
        """Test fallback to first category."""
        mock_response = {"content": "unknown"}

        with patch.object(ModelRouter, "route_query", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response

            result = await simple_classify(
                "Something weird happened", ["bug", "feature", "question"]
            )

            # Should fallback to first category
            assert result == "bug"

    @pytest.mark.asyncio
    async def test_classify_empty_categories(self):
        """Test with empty categories."""
        mock_response = {"content": "test"}

        with patch.object(ModelRouter, "route_query", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response

            result = await simple_classify("test", [])

            assert result == "unknown"


class TestQuickSummarize:
    """Tests for quick_summarize function."""

    @pytest.mark.asyncio
    async def test_summarize_basic(self):
        """Test basic summarization."""
        text = "This is a long text that needs to be summarized." * 10
        mock_response = {"content": "Text summary here."}

        with patch.object(ModelRouter, "route_query", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response

            result = await quick_summarize(text)

            assert result == "Text summary here."

    @pytest.mark.asyncio
    async def test_summarize_custom_sentences(self):
        """Test summarization with custom sentence limit."""
        text = "Long text here." * 20
        mock_response = {"content": "Summary."}

        with patch.object(ModelRouter, "route_query", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response

            await quick_summarize(text, max_sentences=1)

            # Check prompt includes sentence limit
            call_args = mock.call_args
            assert "1 sentences" in call_args[1]["system_prompt"]


class TestTaskRouting:
    """Tests for task routing configuration."""

    def test_fast_tasks(self):
        """Test that fast tasks route to fast tier."""
        fast_tasks = [
            TaskType.TITLE_GENERATION,
            TaskType.BINARY_DECISION,
            TaskType.SIMPLE_CLASSIFICATION,
            TaskType.TEXT_SUMMARIZATION_SHORT,
        ]

        for task in fast_tasks:
            assert TASK_ROUTING[task] == ModelTier.FAST, f"{task} should route to FAST"

    def test_powerful_tasks(self):
        """Test that complex tasks route to powerful tier."""
        powerful_tasks = [
            TaskType.COMPLEX_ARCHITECTURE,
            TaskType.LARGE_REFACTORING,
            TaskType.COMPREHENSIVE_ANALYSIS,
            TaskType.MULTI_FILE_CHANGE,
        ]

        for task in powerful_tasks:
            assert TASK_ROUTING[task] == ModelTier.POWERFUL, f"{task} should route to POWERFUL"


class TestCostEstimation:
    """Tests for cost estimation."""

    def test_fast_is_cheaper(self):
        """Test that fast tier is cheaper than powerful."""
        router = ModelRouter()

        # Same token count for both
        tokens = 1000

        fast_cost = router.estimate_cost(TaskType.TITLE_GENERATION, tokens, tokens)

        powerful_cost = router.estimate_cost(TaskType.COMPLEX_ARCHITECTURE, tokens, tokens)

        assert fast_cost < powerful_cost

    def test_zero_tokens(self):
        """Test cost estimation with zero tokens."""
        router = ModelRouter()

        cost = router.estimate_cost(TaskType.TITLE_GENERATION, 0, 0)

        assert cost == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
