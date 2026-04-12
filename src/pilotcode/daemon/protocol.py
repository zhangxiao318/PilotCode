"""JSON-RPC protocol definitions for PilotCode Daemon."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Any, Optional


@dataclass
class Request:
    """JSON-RPC Request."""
    
    jsonrpc: str = "2.0"
    id: int = 0
    method: str = ""
    params: dict = None
    
    def __post_init__(self):
        if self.params is None:
            self.params = {}
    
    @classmethod
    def from_json(cls, data: str) -> Optional[Request]:
        """Parse JSON string to Request."""
        try:
            obj = json.loads(data)
            return cls(
                jsonrpc=obj.get("jsonrpc", "2.0"),
                id=obj.get("id", 0),
                method=obj.get("method", ""),
                params=obj.get("params", {})
            )
        except (json.JSONDecodeError, KeyError) as e:
            print(f"[Daemon] Failed to parse request: {e}")
            return None
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass
class Response:
    """JSON-RPC Response."""
    
    jsonrpc: str = "2.0"
    id: int = 0
    result: Any = None
    error: Optional[dict] = None
    
    @classmethod
    def success(cls, id: int, result: Any) -> Response:
        """Create success response."""
        return cls(id=id, result=result)
    
    @classmethod
    def error_response(cls, id: int, code: int, message: str, data: Any = None) -> Response:
        """Create error response."""
        error_obj = {"code": code, "message": message}
        if data is not None:
            error_obj["data"] = data
        return cls(id=id, error=error_obj)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        obj = {
            "jsonrpc": self.jsonrpc,
            "id": self.id
        }
        if self.error is not None:
            obj["error"] = self.error
        else:
            obj["result"] = self.result
        return json.dumps(obj, ensure_ascii=False) + "\n"


@dataclass
class Notification:
    """JSON-RPC Notification (no response needed)."""
    
    jsonrpc: str = "2.0"
    method: str = ""
    params: dict = None
    
    def __post_init__(self):
        if self.params is None:
            self.params = {}
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps({
            "jsonrpc": self.jsonrpc,
            "method": self.method,
            "params": self.params
        }, ensure_ascii=False) + "\n"


# Error codes (following JSON-RPC spec)
class ErrorCode:
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    SERVER_ERROR = -32000
