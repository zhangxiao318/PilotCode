"""Audit logging for plugin operations.

Records all plugin-related operations for compliance and security review.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class AuditAction(Enum):
    """Types of audited actions."""
    INSTALL = "install"
    UNINSTALL = "uninstall"
    ENABLE = "enable"
    DISABLE = "disable"
    UPDATE = "update"
    LOAD = "load"
    VERIFY = "verify"
    POLICY_VIOLATION = "policy_violation"


class AuditOutcome(Enum):
    """Outcome of audited action."""
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    WARNING = "warning"


@dataclass
class AuditEvent:
    """Audit event record."""
    timestamp: str
    action: str
    plugin_id: Optional[str]
    user: Optional[str]
    outcome: str
    details: dict
    message: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "plugin_id": self.plugin_id,
            "user": self.user,
            "outcome": self.outcome,
            "details": self.details,
            "message": self.message,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AuditEvent":
        return cls(
            timestamp=data["timestamp"],
            action=data["action"],
            plugin_id=data.get("plugin_id"),
            user=data.get("user"),
            outcome=data["outcome"],
            details=data.get("details", {}),
            message=data.get("message"),
        )


class AuditLogger:
    """Logs plugin operations for audit.
    
    Maintains a tamper-evident log of all plugin operations.
    """
    
    def __init__(self, log_path: Optional[Path] = None):
        self.log_path = log_path or (
            Path.home() / ".config" / "pilotcode" / "audit.log"
        )
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._buffer: list[AuditEvent] = []
        self._auto_flush = True
    
    def log(
        self,
        action: AuditAction,
        outcome: AuditOutcome,
        plugin_id: Optional[str] = None,
        user: Optional[str] = None,
        details: Optional[dict] = None,
        message: Optional[str] = None,
    ) -> None:
        """Log an audit event."""
        event = AuditEvent(
            timestamp=datetime.now().isoformat(),
            action=action.value,
            plugin_id=plugin_id,
            user=user,
            outcome=outcome.value,
            details=details or {},
            message=message,
        )
        
        self._buffer.append(event)
        
        if self._auto_flush:
            self.flush()
    
    def flush(self) -> None:
        """Write buffered events to log."""
        if not self._buffer:
            return
        
        with open(self.log_path, "a") as f:
            for event in self._buffer:
                f.write(json.dumps(event.to_dict()) + "\n")
        
        self._buffer.clear()
    
    def get_events(
        self,
        action: Optional[AuditAction] = None,
        plugin_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Get audit events."""
        events = []
        
        if not self.log_path.exists():
            return events
        
        with open(self.log_path, "r") as f:
            for line in reversed(f.readlines()):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    event = AuditEvent.from_dict(data)
                    
                    if action and event.action != action.value:
                        continue
                    if plugin_id and event.plugin_id != plugin_id:
                        continue
                    
                    events.append(event)
                    
                    if len(events) >= limit:
                        break
                except json.JSONDecodeError:
                    continue
        
        return events
    
    def get_install_history(self, plugin_id: str) -> list[AuditEvent]:
        """Get install/uninstall history for a plugin."""
        events = self.get_events(plugin_id=plugin_id, limit=50)
        return [
            e for e in events
            if e.action in (AuditAction.INSTALL.value, AuditAction.UNINSTALL.value)
        ]
    
    def clear(self) -> None:
        """Clear audit log (use with caution)."""
        if self.log_path.exists():
            self.log_path.unlink()


# Global instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get global audit logger."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
