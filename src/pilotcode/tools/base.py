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

    def to_openai_schema(self, ultra_slim: bool = False) -> dict[str, Any]:
        """Convert tool to OpenAI function-calling schema.

        Strips Pydantic JSON Schema bloat ($defs, title, long descriptions,
        redundant anyOf wrappers) to minimize token usage.

        When ultra_slim=True, also drops all parameter descriptions for
        maximum token savings (~50% smaller). Safe for strong models
        that understand parameter semantics from names alone.
        """
        raw = (
            self.input_schema.model_json_schema()
            if hasattr(self.input_schema, "model_json_schema")
            else {"type": "object"}
        )
        slim_params = _slim_json_schema(raw, strip_descriptions=ultra_slim)
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


# ── parameter names whose default values are always worth sending ──
_SIGNAL_DEFAULTS: frozenset[str] = frozenset(
    {
        "action",
        "limit",
        "max_results",
        "max_count",
        "timeout",
        "max_tokens",
        "context_lines",
        "head_limit",
        "offset",
        "search_type",
        "command",
        "language",
    }
)


def _resolve_ref(ref: str, defs: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve a ``$ref`` (e.g. ``#/$defs/Foo``) against a $defs dictionary."""
    if not ref.startswith("#/$defs/"):
        return None
    name = ref[len("#/$defs/") :]
    return defs.get(name)


def _collapse_anyof(
    options: list[dict[str, Any]],
    defs: dict[str, Any],
    strip_descriptions: bool = False,
) -> dict[str, Any]:
    """Extract type + enum + properties from an anyOf list.

    Fully resolves ``$ref`` entries inline, processing the resolved
    schema through ``_slim_property`` so nested object properties are
    slimmed (e.g. ``title`` stripped, descriptions truncated).
    """
    result: dict[str, Any] = {}
    for opt in options:
        if not isinstance(opt, dict):
            continue
        # Resolve $ref and slim the resolved schema
        if "$ref" in opt:
            resolved = _resolve_ref(opt["$ref"], defs)
            if resolved:
                opt = _slim_property(resolved, defs, strip_descriptions)
        if opt.get("type") == "null":
            continue
        # Merge type, enum, items, properties, required
        for key in ("type", "enum", "items", "properties", "required"):
            if key in opt and key not in result:
                result[key] = opt[key]
        # Stop after first real type
        if "type" in result:
            break
    return result


def _slim_property(
    prop_schema: dict[str, Any],
    defs: dict[str, Any],
    strip_descriptions: bool,
) -> dict[str, Any]:
    """Convert a single property schema to its slim form (recursive)."""
    if not isinstance(prop_schema, dict):
        return prop_schema

    slim: dict[str, Any] = {}

    # ── type: direct, or extracted from anyOf / allOf ──
    if "type" in prop_schema:
        slim["type"] = prop_schema["type"]
    elif "anyOf" in prop_schema:
        merged = _collapse_anyof(prop_schema["anyOf"], defs, strip_descriptions)
        slim.update(merged)
    elif "allOf" in prop_schema:
        # allOf is used by Pydantic v2 for inheritance; merge properties
        merged_type: str | None = None
        merged_enum: list | None = None
        merged_items: dict | None = None
        for part in prop_schema["allOf"]:
            if not isinstance(part, dict):
                continue
            if "$ref" in part:
                resolved = _resolve_ref(part["$ref"], defs)
                if resolved:
                    part = resolved
            if "type" in part and not merged_type:
                merged_type = part["type"]
            if "enum" in part and not merged_enum:
                merged_enum = part["enum"]
            if "items" in part and not merged_items:
                merged_items = part["items"]
        if merged_type:
            slim["type"] = merged_type
        if merged_enum:
            slim["enum"] = merged_enum
        if merged_items:
            slim["items"] = merged_items
    # Resolve bare $ref (uncommon but possible)
    elif "$ref" in prop_schema:
        resolved = _resolve_ref(prop_schema["$ref"], defs)
        if resolved:
            slim = _slim_property(resolved, defs, strip_descriptions)

    # ── description (optional) ──
    if not strip_descriptions and "description" in prop_schema:
        d = prop_schema["description"]
        if isinstance(d, str):
            first_sentence = (d.split(".")[0] + ".") if "." in d else d[:80]
            slim["description"] = first_sentence[:120]

    # ── enum (already handled by anyOf/allOf above, but also direct) ──
    if "enum" in prop_schema:
        slim["enum"] = prop_schema["enum"]

    # ── default (only for high-signal parameters) ──
    # We use a frozenset lookup; the caller also passes the property name.
    # This function doesn't know the name, so we keep *all* defaults here
    # and let the caller filter.  (Kept small to avoid bloat.)

    # ── nested object ──
    # Properties may come from the original prop_schema (direct) or from
    # a resolved $ref inside anyOf (merged by _collapse_anyof above).
    src_props = slim.get("properties") if slim.get("properties") else prop_schema.get("properties")
    if slim.get("type") == "object" and src_props:
        nested = {}
        for k, v in src_props.items():
            if isinstance(v, dict):
                nested[k] = _slim_property(v, defs, strip_descriptions)
        if nested:
            slim["properties"] = nested

    # ── array items ──
    if slim.get("type") == "array" and "items" in prop_schema:
        items = prop_schema["items"]
        if isinstance(items, dict):
            slim["items"] = _slim_property(items, defs, strip_descriptions)

    # ── additionalProperties (for dict/mapping types) ──
    if "additionalProperties" in prop_schema and isinstance(
        prop_schema["additionalProperties"], dict
    ):
        slim["additionalProperties"] = _slim_property(
            prop_schema["additionalProperties"], defs, strip_descriptions
        )

    return slim


def _slim_json_schema(schema: dict[str, Any], strip_descriptions: bool = False) -> dict[str, Any]:
    """Strip bloat from Pydantic JSON Schema.

    * Resolves ``$defs`` / ``$ref`` inline so the LLM never sees references.
    * Collapses ``anyOf`` / ``allOf`` to plain ``type`` + ``enum``.
    * Strips ``title`` everywhere (Pydantic auto-generates it).
    * Truncates descriptions to first sentence (or drops entirely with
      ``strip_descriptions=True``).

    Token savings typically 40-60 % vs raw ``model_json_schema()``.
    """
    if not isinstance(schema, dict):
        return schema

    # Collect $defs for resolution
    defs: dict[str, Any] = schema.get("$defs") or schema.get("definitions") or {}

    slim: dict[str, Any] = {}

    # Top-level structural keys (never include title or $defs)
    for key in ("type", "required", "additionalProperties", "enum"):
        if key in schema:
            slim[key] = schema[key]

    # Properties
    if "properties" in schema:
        slim["properties"] = {}
        for prop_name, prop_schema in schema["properties"].items():
            if not isinstance(prop_schema, dict):
                slim["properties"][prop_name] = prop_schema
                continue

            prop = _slim_property(prop_schema, defs, strip_descriptions)

            # Keep default only for high-signal parameter names
            if "default" in prop_schema and prop_name in _SIGNAL_DEFAULTS:
                prop["default"] = prop_schema["default"]

            slim["properties"][prop_name] = prop

    # Fallback: ensure type=object when nothing else gives a type
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
