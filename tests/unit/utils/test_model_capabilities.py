"""Tests for model_capabilities module."""

import pytest
from pilotcode.utils.model_capabilities import ModelCapabilities


class TestModelCapabilities:
    """Tests for ModelCapabilities dataclass."""

    def test_defaults(self):
        """Test default values."""
        caps = ModelCapabilities()
        assert caps.temperature is True
        assert caps.reasoning is False
        assert caps.tool_call is True
        assert caps.image_input is False
        assert caps.text_output is True

    def test_from_dict_empty(self):
        """Test from_dict with empty dict."""
        caps = ModelCapabilities.from_dict({})
        assert caps.temperature is True
        assert caps.reasoning is False

    def test_from_dict_direct_fields(self):
        """Test from_dict with direct field names."""
        caps = ModelCapabilities.from_dict(
            {"reasoning": True, "image_input": True, "temperature": False}
        )
        assert caps.reasoning is True
        assert caps.image_input is True
        assert caps.temperature is False

    def test_from_dict_modalities(self):
        """Test from_dict with modalities shortcut."""
        caps = ModelCapabilities.from_dict(
            {
                "modalities": {
                    "input": ["text", "image", "pdf"],
                    "output": ["text", "audio"],
                }
            }
        )
        assert caps.image_input is True
        assert caps.pdf_input is True
        assert caps.audio_input is False
        assert caps.audio_output is True
        assert caps.text_output is True

    def test_from_dict_remap(self):
        """Test field name remapping."""
        caps = ModelCapabilities.from_dict({"supports_tools": False, "supports_vision": True})
        assert caps.tool_call is False
        assert caps.image_input is True

    def test_from_dict_reasoning_content(self):
        """Test reasoning_content remap."""
        caps = ModelCapabilities.from_dict({"reasoning_content": True})
        assert caps.reasoning_content_field is True

    def test_to_dict(self):
        """Test serialization to dict."""
        caps = ModelCapabilities(
            reasoning=True,
            image_input=True,
            tool_call=False,
            interleaved={"field": "reasoning_content"},
        )
        d = caps.to_dict()
        assert d["reasoning"] is True
        assert d["image_input"] is True
        assert d["tool_call"] is False
        assert d["interleaved"] == {"field": "reasoning_content"}
        # Defaults that are True should appear, defaults that are False should not
        assert "temperature" not in d  # True but not overridden
        assert "audio_input" not in d  # False default


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
