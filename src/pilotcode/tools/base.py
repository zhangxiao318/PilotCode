"""Base tool definitions."""

from typing import Any, Callable, Awaitable, TypeVar, Generic, TYPE_CHECKING
from dataclasses import dataclass, field
from pydantic import BaseModel
import asyncio

if TYPE_CHECKING:
    from ..state.app_state import AppState


# Type variables for generic Tool
InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT")
ProgressT = TypeVar("ProgressT", bound="ToolProgressData")


class ToolProgressData(BaseModel):
    """Base class for tool progress data."""

    pass


class ToolInput(BaseModel):
    """Base class for tool inputs."""

    pass


class ToolOutput(BaseModel):
    """Base class for tool outputs."""

    pass


@dataclass
class ToolResult(Generic[OutputT]):
    """Result of tool execution."""

    data: OutputT
    error: str | None = None
    output_for_assistant: str | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None

    def get_text_for_assistant(self) -> str:
        """Get a human-readable text representation for the LLM.

        Prefers output_for_assistant if available, otherwise serializes
        the data model or falls back to str().
        """
        if self.output_for_assistant:
            return self.output_for_assistant
        if self.error:
            return f"Error: {self.error}"
        if self.data is not None:
            if isinstance(self.data, BaseModel):
                return self.data.model_dump_json(indent=2, ensure_ascii=False)
            return str(self.data)
        return "Success"


@dataclass
class ToolUseContext:
    """Context for tool execution."""

    options: dict[str, Any] = field(default_factory=dict)
    abort_controller: asyncio.Event = field(default_factory=asyncio.Event)
    read_file_state: dict[str, Any] = field(default_factory=dict)
    get_app_state: Callable[[], "AppState"] | None = None
    set_app_state: Callable[[Callable[["AppState"], "AppState"]], None] | None = None
    cwd: str = ""

    def is_aborted(self) -> bool:
        return self.abort_controller.is_set()


def resolve_cwd(context: ToolUseContext) -> str:
    """Resolve the effective working directory from context.

    Priority:
        1. context.cwd (session-level injection)
        2. context.get_app_state().cwd (global state)
        3. os.getcwd() (process fallback)
    """
    import os

    if context.cwd:
        return context.cwd
    if context.get_app_state:
        app_state = context.get_app_state()
        cwd = getattr(app_state, "cwd", None)
        if cwd:
            return cwd
    return os.getcwd()


# Type for the call function
ToolCallFn = Callable[
    [Any, ToolUseContext, Callable[..., Awaitable[Any]], Any, Callable[[Any], None]],
    Awaitable[ToolResult[Any]],
]


class Tool:
    """Tool definition."""

    def __init__(
        self,
        name: str,
        description: str | Callable[[Any, dict[str, Any]], Awaitable[str]],
        input_schema: type[BaseModel],
        call: ToolCallFn,
        output_schema: type[BaseModel] | None = None,
        aliases: list[str] | None = None,
        search_hint: str = "",
        max_result_size_chars: int = 100000,
        should_defer: bool = False,
        always_load: bool = False,
        strict: bool = False,
        is_read_only: Callable[[Any], bool] | None = None,
        is_destructive: Callable[[Any], bool] | None = None,
        is_concurrency_safe: Callable[[Any], bool] | None = None,
        is_enabled: Callable[[], bool] | None = None,
        user_facing_name: Callable[[Any], str] | None = None,
        prompt: Callable[[dict[str, Any]], Awaitable[str]] | None = None,
        check_permissions: Callable[[Any, ToolUseContext], Awaitable[Any]] | None = None,
        validate_input: (
            Callable[[Any, ToolUseContext], Awaitable[tuple[bool, str | None]]] | None
        ) = None,
        render_tool_use_message: Callable[[Any, dict[str, Any]], str] | None = None,
        render_tool_result_message: Callable[[Any, list[Any], dict[str, Any]], str] | None = None,
        render_tool_use_progress: Callable[[list[Any], dict[str, Any]], str] | None = None,
        render_tool_use_rejected: Callable[[Any, dict[str, Any]], str] | None = None,
        _slim_schema: bool = True,
    ):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.output_schema = output_schema
        self.call = call
        self.aliases = aliases or []
        self.search_hint = search_hint
        self.max_result_size_chars = max_result_size_chars
        self.should_defer = should_defer
        self.always_load = always_load
        self.strict = strict
        self.is_read_only = is_read_only or (lambda _: False)
        self.is_destructive = is_destructive or (lambda _: False)
        self.is_concurrency_safe = is_concurrency_safe or (lambda _: False)
        self.is_enabled = is_enabled or (lambda: True)
        self.user_facing_name = user_facing_name
        self.prompt = prompt
        self.check_permissions = check_permissions
        self.validate_input = validate_input
        self.render_tool_use_message = render_tool_use_message
        self.render_tool_result_message = render_tool_result_message
        self.render_tool_use_progress = render_tool_use_progress
        self.render_tool_use_rejected = render_tool_use_rejected

    def to_openai_schema(self) -> dict[str, Any]:
        """Convert tool to slim OpenAI function-calling schema.

        Strips Pydantic JSON Schema bloat ($defs, title, long descriptions,
        redundant anyOf wrappers) to minimize token usage.
        """
        raw = (
            self.input_schema.model_json_schema()
            if hasattr(self.input_schema, "model_json_schema")
            else {"type": "object"}
        )
        slim_params = _slim_json_schema(raw)
        desc = self.description
        if callable(desc):
            desc = f"{self.name} tool"
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": desc,
                "parameters": slim_params,
            },
        }


def _slim_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Strip bloat from Pydantic JSON Schema.

    Keeps only: type, properties (name+type+description+enum),
    required, additionalProperties.
    """
    if not isinstance(schema, dict):
        return schema

    slim: dict[str, Any] = {}

    # Preserve structural keys
    for key in ("type", "required", "additionalProperties", "enum"):
        if key in schema:
            slim[key] = schema[key]

    # Recurse into properties
    if "properties" in schema:
        slim["properties"] = {}
        for prop_name, prop_schema in schema["properties"].items():
            slim_prop: dict[str, Any] = {}
            if isinstance(prop_schema, dict):
                # Keep type (or infer from anyOf)
                if "type" in prop_schema:
                    slim_prop["type"] = prop_schema["type"]
                elif "anyOf" in prop_schema:
                    # Collapse anyOf [string, null] -> type string + nullable feel
                    types = [
                        item.get("type")
                        for item in prop_schema["anyOf"]
                        if isinstance(item, dict) and "type" in item
                    ]
                    if "null" in types:
                        types.remove("null")
                    if types:
                        slim_prop["type"] = types[0]
                    # Keep enum if present
                    if "enum" in prop_schema:
                        slim_prop["enum"] = prop_schema["enum"]
                # Keep description (trimmed)
                if "description" in prop_schema:
                    d = prop_schema["description"]
                    if isinstance(d, str):
                        # Truncate very long descriptions to first sentence
                        first_sentence = d.split(".")[0] + "." if "." in d else d[:80]
                        slim_prop["description"] = first_sentence[:120]
                # Keep enum
                if "enum" in prop_schema:
                    slim_prop["enum"] = prop_schema["enum"]
                # Keep default for high-signal params (action, limit, max_results)
                if "default" in prop_schema and prop_name in (
                    "action",
                    "limit",
                    "max_results",
                    "max_count",
                    "timeout",
                    "max_tokens",
                    "context_lines",
                    "head_limit",
                    "offset",
                ):
                    slim_prop["default"] = prop_schema["default"]
                # Recurse into nested objects (shallow only)
                if prop_schema.get("type") == "object" and "properties" in prop_schema:
                    slim_prop["properties"] = {
                        k: {
                            "type": v.get("type", "string"),
                            "description": v.get("description", "")[:60],
                        }
                        for k, v in prop_schema["properties"].items()
                        if isinstance(v, dict)
                    }
                if prop_schema.get("type") == "array" and "items" in prop_schema:
                    items = prop_schema["items"]
                    if isinstance(items, dict):
                        slim_prop["items"] = {"type": items.get("type", "string")}
            slim["properties"][prop_name] = slim_prop

    # Drop empty objects
    if not slim.get("properties") and "type" not in slim:
        slim["type"] = "object"

    return slim


def build_tool(
    name: str,
    description: str | Callable[[Any, dict], Awaitable[str]],
    input_schema: type[BaseModel],
    call: ToolCallFn,
    output_schema: type[BaseModel] | None = None,
    **kwargs,
) -> Tool:
    """Build a tool with defaults."""
    return Tool(
        name=name,
        description=description,
        input_schema=input_schema,
        call=call,
        output_schema=output_schema,
        **kwargs,
    )


def tool_matches_name(tool: Tool, name: str) -> bool:
    """Check if tool matches name (including aliases)."""
    if tool.name == name:
        return True
    return name in tool.aliases


# Type alias for Tools list
Tools = list[Tool]
