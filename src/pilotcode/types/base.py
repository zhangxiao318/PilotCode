"""Base type definitions."""

from typing import TypeAlias, Union
from datetime import datetime
from uuid import UUID  # noqa: F401 - Re-exported in __init__.py

# Type aliases
AgentId: TypeAlias = str
ToolName: TypeAlias = str
CommandName: TypeAlias = str
SessionId: TypeAlias = str
Timestamp: TypeAlias = datetime

# JSON types
JSONValue: TypeAlias = Union[str, int, float, bool, None, list["JSONValue"], dict[str, "JSONValue"]]
JSONObject: TypeAlias = dict[str, JSONValue]
