"""Command type definitions."""

from typing import Literal, Callable, Awaitable, Any
from pydantic import BaseModel
from .message import ContentBlock


CommandType = Literal["prompt", "local", "local_jsx"]


class CommandContext(BaseModel):
    """Context for command execution."""
    cwd: str
    verbose: bool = False
    query_engine: Any | None = None
    
    class Config:
        arbitrary_types_allowed = True


class Command(BaseModel):
    """Base command definition."""
    name: str
    description: str
    type: CommandType
    aliases: list[str] = []
    is_enabled: bool = True
    is_hidden: bool = False
    
    class Config:
        arbitrary_types_allowed = True


class PromptCommand(Command):
    """Prompt command - expands to message content."""
    type: Literal["prompt"] = "prompt"
    progress_message: str
    content_length: int
    get_prompt: Callable[[list[str], CommandContext], Awaitable[list[ContentBlock]]]
    
    class Config:
        arbitrary_types_allowed = True


class LocalCommandResult(BaseModel):
    """Result from local command execution."""
    success: bool
    message: str | None = None
    data: Any = None


class LocalCommand(Command):
    """Local command - executes Python code."""
    type: Literal["local"] = "local"
    supports_non_interactive: bool = True
    call: Callable[[list[str], CommandContext], Awaitable[LocalCommandResult]]
    
    class Config:
        arbitrary_types_allowed = True


class LocalJSXCommand(Command):
    """Local JSX command - renders TUI component."""
    type: Literal["local_jsx"] = "local_jsx"
    call: Callable[[list[str], CommandContext], Awaitable[Any]]  # Returns component
    
    class Config:
        arbitrary_types_allowed = True
