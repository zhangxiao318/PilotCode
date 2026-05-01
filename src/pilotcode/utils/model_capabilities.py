"""Model capability matrix for provider-specific feature detection.

Inspired by opencode's models.dev schema. Each model declares a fine-grained
capability matrix so the rest of the codebase can adapt UI, parameters, and
message formatting without hard-coding provider names everywhere.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class ModelCapabilities:
    """Fine-grained capability matrix for a model.

    Fields default to the most common OpenAI-compatible baseline.
    Override per-model in ``models.json`` via the ``capabilities`` key.
    """

    # Generation controls
    temperature: bool = True
    top_p: bool = True
    top_k: bool = False

    # Reasoning / thinking mode
    reasoning: bool = False

    # Tool calling
    tool_call: bool = True

    # File / attachment input
    attachment: bool = False

    # Input modalities
    image_input: bool = False
    audio_input: bool = False
    video_input: bool = False
    pdf_input: bool = False

    # Output modalities
    text_output: bool = True
    image_output: bool = False
    audio_output: bool = False
    video_output: bool = False

    # Content format quirks
    # True  -> content array with interleaved text/image/tool
    # dict  -> e.g. {"field": "reasoning_content"} for providers that
    #          put reasoning in a custom top-level field on the message
    interleaved: bool | dict = False

    # Provider-specific quirks
    # Anthropic always requires explicit tool_choice even when "auto"
    requires_tool_choice_explicit: bool = False
    # DeepSeek-style reasoning_content echo field on assistant messages
    reasoning_content_field: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelCapabilities":
        """Create capabilities from a dict (e.g. from models.json)."""
        if not data:
            return cls()

        kwargs: dict[str, Any] = {}

        # Handle ``modalities`` shortcut (opencode-style)
        if "modalities" in data:
            modalities = data["modalities"]
            if isinstance(modalities, dict):
                inp = modalities.get("input", [])
                out = modalities.get("output", [])
                kwargs["image_input"] = "image" in inp
                kwargs["audio_input"] = "audio" in inp
                kwargs["video_input"] = "video" in inp
                kwargs["pdf_input"] = "pdf" in inp
                kwargs["image_output"] = "image" in out
                kwargs["audio_output"] = "audio" in out
                kwargs["video_output"] = "video" in out
                kwargs["text_output"] = "text" in out

        # Field-name remapping from legacy / opencode keys
        remap: dict[str, str] = {
            "tool_calling": "tool_call",
            "supports_tools": "tool_call",
            "supports_tool_choice": "requires_tool_choice_explicit",
            "supports_vision": "image_input",
            "reasoning_content": "reasoning_content_field",
        }

        for src, dst in remap.items():
            if src in data:
                kwargs[dst] = data[src]

        # Direct passthrough for keys that match our field names
        for field_name in cls.__dataclass_fields__:
            if field_name in data and field_name not in kwargs:
                kwargs[field_name] = data[field_name]

        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict (for JSON/config).

        Only includes fields that differ from the factory defaults so the
        output stays concise.
        """
        result: dict[str, Any] = {}
        defaults = ModelCapabilities()
        for field_name in self.__dataclass_fields__:
            val = getattr(self, field_name)
            default = getattr(defaults, field_name)
            if val != default:
                result[field_name] = val
        return result
