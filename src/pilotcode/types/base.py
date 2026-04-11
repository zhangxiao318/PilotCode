"""Base type definitions."""

from typing import TypeAlias, Union
from datetime import datetime

# Type aliases
AgentId: TypeAlias = str
ToolName: TypeAlias = str
CommandName: TypeAlias = str
SessionId: TypeAlias = str
Timestamp: TypeAlias = datetime

# JSON types
JSONValue: TypeAlias = Union[str, int, float, bool, None, list["JSONValue"], dict[str, "JSONValue"]]
JSONObject: TypeAlias = dict[str, JSONValue]
