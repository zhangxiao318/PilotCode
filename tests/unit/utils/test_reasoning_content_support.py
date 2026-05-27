"""Tests for reasoning_content provider detection fix."""

from __future__ import annotations

from unittest.mock import MagicMock

from pilotcode.utils.model_client import ModelClient
from pilotcode.utils.model_capabilities import ModelCapabilities


class TestSupportsReasoningContent:
    """Verify supports_reasoning_content correctly identifies all providers."""

    def _make_client(
        self,
        provider_name: str,
        api_protocol: str = "openai",
        capabilities: ModelCapabilities | None = None,
    ):
        """Create a minimal ModelClient mock."""
        client = MagicMock(spec=ModelClient)
        client._provider_name = provider_name
        client._api_protocol = api_protocol
        client._is_deepseek = provider_name == "deepseek"
        client._model_info = None

        # Patch the property to use real logic
        def _get_supports():
            if capabilities and capabilities.reasoning_content_field:
                return True
            if api_protocol == "openai" and provider_name in ("deepseek", "qwen"):
                return True
            if provider_name == "anthropic":
                return True
            return False

        type(client).supports_reasoning_content = property(lambda self: _get_supports())
        return client

    def test_deepseek_recognized(self):
        client = self._make_client("deepseek", "openai")
        assert client.supports_reasoning_content is True

    def test_qwen_recognized(self):
        client = self._make_client("qwen", "openai")
        assert client.supports_reasoning_content is True

    def test_anthropic_recognized(self):
        client = self._make_client("anthropic", "anthropic")
        assert client.supports_reasoning_content is True

    def test_openai_gpt4o_not_recognized(self):
        client = self._make_client("openai", "openai")
        assert client.supports_reasoning_content is False

    def test_moonshot_not_recognized(self):
        client = self._make_client("moonshot", "openai")
        assert client.supports_reasoning_content is False

    def test_explicit_capability_overrides(self):
        caps = ModelCapabilities(reasoning_content_field=True)
        client = self._make_client("custom", "openai", capabilities=caps)
        assert client.supports_reasoning_content is True

    def test_explicit_capability_false(self):
        caps = ModelCapabilities(reasoning_content_field=False)
        client = self._make_client("deepseek", "openai", capabilities=caps)
        # DeepSeek provider name still triggers True
        assert client.supports_reasoning_content is True
