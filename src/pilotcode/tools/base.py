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


@dataclass
class ToolUseContext:
    """Context for tool execution."""

    options: dict[str, Any] = field(default_factory=dict)
    abort_controller: asyncio.Event = field(default_factory=asyncio.Event)
    read_file_state: dict[str, Any] = field(default_factory=dict)
    get_app_state: Callable[[], "AppState"] | None = None
    set_app_state: Callable[[Callable[["AppState"], "AppState"]], None] | None = None

    def is_aborted(self) -> bool:
        return self.abort_controller.is_set()


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
