"""Analytics Service - Usage analytics and metrics collection.

This module provides:
1. Usage tracking (commands, tools, tokens)
2. Cost analysis
3. Performance metrics
4. Error tracking
5. Session analytics

Features:
- Event-based analytics collection
- Aggregated statistics
- Cost estimation
- Performance tracking
- Export capabilities
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict
from enum import Enum

from pydantic import BaseModel, Field


class AnalyticsEventType(str, Enum):
    """Types of analytics events."""
    COMMAND = "command"
    TOOL = "tool"
    MODEL_REQUEST = "model_request"
    MODEL_RESPONSE = "model_response"
    ERROR = "error"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    FILE_OPERATION = "file_operation"
    GIT_OPERATION = "git_operation"


@dataclass
class AnalyticsEvent:
    """A single analytics event."""
    event_type: AnalyticsEventType
    name: str
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 0.0
    tokens_input: int = 0
    tokens_output: int = 0
    cost: float = 0.0
    success: bool = True
    error_message: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_type": self.event_type.value,
            "name": self.name,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "cost": self.cost,
            "success": self.success,
            "error_message": self.error_message,
            "metadata": self.metadata,
            "session_id": self.session_id,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnalyticsEvent:
        """Create from dictionary."""
        return cls(
            event_type=AnalyticsEventType(data["event_type"]),
            name=data["name"],
            timestamp=data.get("timestamp", time.time()),
            duration_ms=data.get("duration_ms", 0.0),
            tokens_input=data.get("tokens_input", 0),
            tokens_output=data.get("tokens_output", 0),
            cost=data.get("cost", 0.0),
            success=data.get("success", True),
            error_message=data.get("error_message"),
            metadata=data.get("metadata", {}),
            session_id=data.get("session_id", ""),
        )


@dataclass
class UsageStats:
    """Aggregated usage statistics."""
    total_commands: int = 0
    total_tools: int = 0
    total_model_requests: int = 0
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    total_cost: float = 0.0
    total_errors: int = 0
    total_duration_ms: float = 0.0
    
    # Breakdown by type
    commands_by_name: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    tools_by_name: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    errors_by_type: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "total_commands": self.total_commands,
            "total_tools": self.total_tools,
            "total_model_requests": self.total_model_requests,
            "total_tokens_input": self.total_tokens_input,
            "total_tokens_output": self.total_tokens_output,
            "total_cost": self.total_cost,
            "total_errors": self.total_errors,
            "total_duration_ms": self.total_duration_ms,
            "commands_by_name": dict(self.commands_by_name),
            "tools_by_name": dict(self.tools_by_name),
            "errors_by_type": dict(self.errors_by_type),
        }


@dataclass
class SessionStats:
    """Statistics for a single session."""
    session_id: str
    start_time: float
    end_time: Optional[float] = None
    event_count: int = 0
    commands_used: set[str] = field(default_factory=set)
    tools_used: set[str] = field(default_factory=set)
    total_cost: float = 0.0
    
    @property
    def duration_seconds(self) -> float:
        """Get session duration."""
        end = self.end_time or time.time()
        return end - self.start_time
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "event_count": self.event_count,
            "commands_used": list(self.commands_used),
            "tools_used": list(self.tools_used),
            "total_cost": self.total_cost,
        }


class AnalyticsConfig(BaseModel):
    """Configuration for AnalyticsService."""
    
    enabled: bool = Field(default=True, description="Enable analytics collection")
    track_commands: bool = Field(default=True, description="Track command usage")
    track_tools: bool = Field(default=True, description="Track tool usage")
    track_tokens: bool = Field(default=True, description="Track token usage")
    track_costs: bool = Field(default=True, description="Track costs")
    track_errors: bool = Field(default=True, description="Track errors")
    max_events: int = Field(default=10000, description="Maximum events to store in memory")
    cost_per_1k_input: float = Field(default=0.01, description="Cost per 1K input tokens")
    cost_per_1k_output: float = Field(default=0.03, description="Cost per 1K output tokens")


class AnalyticsService:
    """Service for collecting and analyzing usage analytics.
    
    Features:
    - Event-based analytics collection
    - Usage statistics aggregation
    - Cost estimation
    - Session tracking
    - Performance metrics
    
    Usage:
        analytics = AnalyticsService(config)
        
        # Track events
        analytics.track_command("/help", duration_ms=100)
        analytics.track_tool("FileRead", tokens=100)
        analytics.track_model_request(tokens_input=1000, tokens_output=500)
        
        # Get stats
        stats = analytics.get_stats()
        print(f"Total cost: ${stats.total_cost:.4f}")
    """
    
    def __init__(self, config: Optional[AnalyticsConfig] = None):
        self.config = config or AnalyticsConfig()
        self.events: list[AnalyticsEvent] = []
        self.current_session: Optional[SessionStats] = None
        self._total_stats = UsageStats()
        self._lock = None  # Would use asyncio.Lock in async context
    
    def start_session(self, session_id: Optional[str] = None) -> SessionStats:
        """Start a new analytics session."""
        if session_id is None:
            session_id = f"session_{int(time.time() * 1000)}"
        
        self.current_session = SessionStats(
            session_id=session_id,
            start_time=time.time(),
        )
        
        # Track session start
        self.track_event(AnalyticsEvent(
            event_type=AnalyticsEventType.SESSION_START,
            name="session_start",
            session_id=session_id,
        ))
        
        return self.current_session
    
    def end_session(self) -> Optional[SessionStats]:
        """End the current session."""
        if self.current_session:
            self.current_session.end_time = time.time()
            
            # Track session end
            self.track_event(AnalyticsEvent(
                event_type=AnalyticsEventType.SESSION_END,
                name="session_end",
                session_id=self.current_session.session_id,
                metadata={"duration_seconds": self.current_session.duration_seconds},
            ))
            
            session = self.current_session
            self.current_session = None
            return session
        
        return None
    
    def track_event(self, event: AnalyticsEvent) -> None:
        """Track a generic analytics event."""
        if not self.config.enabled:
            return
        
        # Set session ID if in session
        if self.current_session and not event.session_id:
            event.session_id = self.current_session.session_id
            self.current_session.event_count += 1
        
        # Add to events list
        self.events.append(event)
        
        # Update stats
        self._update_stats(event)
        
        # Trim if needed
        if len(self.events) > self.config.max_events:
            self.events = self.events[-self.config.max_events:]
    
    def track_command(
        self,
        command_name: str,
        duration_ms: float = 0.0,
        success: bool = True,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Track a command execution."""
        if not self.config.track_commands:
            return
        
        event = AnalyticsEvent(
            event_type=AnalyticsEventType.COMMAND,
            name=command_name,
            duration_ms=duration_ms,
            success=success,
            metadata=metadata or {},
        )
        
        self.track_event(event)
        
        if self.current_session:
            self.current_session.commands_used.add(command_name)
    
    def track_tool(
        self,
        tool_name: str,
        duration_ms: float = 0.0,
        tokens: int = 0,
        success: bool = True,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Track a tool execution."""
        if not self.config.track_tools:
            return
        
        event = AnalyticsEvent(
            event_type=AnalyticsEventType.TOOL,
            name=tool_name,
            duration_ms=duration_ms,
            tokens_output=tokens,
            success=success,
            metadata=metadata or {},
        )
        
        self.track_event(event)
        
        if self.current_session:
            self.current_session.tools_used.add(tool_name)
    
    def track_model_request(
        self,
        model_name: str = "default",
        tokens_input: int = 0,
        tokens_output: int = 0,
        duration_ms: float = 0.0,
    ) -> None:
        """Track a model API request."""
        if not self.config.track_tokens:
            return
        
        # Calculate cost
        cost = 0.0
        if self.config.track_costs:
            cost = (
                (tokens_input / 1000) * self.config.cost_per_1k_input +
                (tokens_output / 1000) * self.config.cost_per_1k_output
            )
        
        event = AnalyticsEvent(
            event_type=AnalyticsEventType.MODEL_REQUEST,
            name=model_name,
            duration_ms=duration_ms,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost=cost,
            metadata={"model": model_name},
        )
        
        self.track_event(event)
        
        if self.current_session:
            self.current_session.total_cost += cost
    
    def track_error(
        self,
        error_type: str,
        error_message: str,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Track an error."""
        if not self.config.track_errors:
            return
        
        event = AnalyticsEvent(
            event_type=AnalyticsEventType.ERROR,
            name=error_type,
            success=False,
            error_message=error_message,
            metadata=context or {},
        )
        
        self.track_event(event)
    
    def _update_stats(self, event: AnalyticsEvent) -> None:
        """Update aggregated statistics."""
        stats = self._total_stats
        
        if event.event_type == AnalyticsEventType.COMMAND:
            stats.total_commands += 1
            stats.commands_by_name[event.name] += 1
        
        elif event.event_type == AnalyticsEventType.TOOL:
            stats.total_tools += 1
            stats.tools_by_name[event.name] += 1
        
        elif event.event_type == AnalyticsEventType.MODEL_REQUEST:
            stats.total_model_requests += 1
            stats.total_tokens_input += event.tokens_input
            stats.total_tokens_output += event.tokens_output
            stats.total_cost += event.cost
        
        elif event.event_type == AnalyticsEventType.ERROR:
            stats.total_errors += 1
            stats.errors_by_type[event.name] += 1
        
        stats.total_duration_ms += event.duration_ms
    
    def get_stats(self) -> UsageStats:
        """Get aggregated usage statistics."""
        return self._total_stats
    
    def get_session_stats(self) -> Optional[SessionStats]:
        """Get current session statistics."""
        return self.current_session
    
    def get_events(
        self,
        event_type: Optional[AnalyticsEventType] = None,
        limit: Optional[int] = None,
    ) -> list[AnalyticsEvent]:
        """Get filtered events."""
        events = self.events
        
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        
        if limit:
            events = events[-limit:]
        
        return events
    
    def get_summary(self) -> dict[str, Any]:
        """Get a summary of analytics."""
        stats = self._total_stats
        
        return {
            "session": self.current_session.to_dict() if self.current_session else None,
            "stats": stats.to_dict(),
            "total_events": len(self.events),
            "top_commands": sorted(
                stats.commands_by_name.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:10],
            "top_tools": sorted(
                stats.tools_by_name.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:10],
            "recent_errors": [
                e.to_dict() for e in self.events
                if e.event_type == AnalyticsEventType.ERROR
            ][-10:],
        }
    
    def get_cost_breakdown(self) -> dict[str, float]:
        """Get cost breakdown by category."""
        costs = {
            "total": self._total_stats.total_cost,
            "by_command": {},
            "by_tool": {},
        }
        
        # Calculate costs by aggregating events
        for event in self.events:
            if event.cost > 0:
                if event.event_type == AnalyticsEventType.COMMAND:
                    costs["by_command"][event.name] = costs["by_command"].get(event.name, 0) + event.cost
                elif event.event_type == AnalyticsEventType.TOOL:
                    costs["by_tool"][event.name] = costs["by_tool"].get(event.name, 0) + event.cost
        
        return costs
    
    def reset(self) -> None:
        """Reset all analytics data."""
        self.events.clear()
        self._total_stats = UsageStats()
        self.current_session = None
    
    def export_to_file(self, filepath: str) -> None:
        """Export analytics data to file."""
        data = {
            "export_time": time.time(),
            "config": self.config.model_dump(),
            "summary": self.get_summary(),
            "events": [e.to_dict() for e in self.events],
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def import_from_file(cls, filepath: str) -> AnalyticsService:
        """Import analytics data from file."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        config = AnalyticsConfig(**data.get("config", {}))
        service = cls(config)
        
        # Restore events
        for event_data in data.get("events", []):
            service.events.append(AnalyticsEvent.from_dict(event_data))
        
        return service
    
    def __repr__(self) -> str:
        return f"AnalyticsService(events={len(self.events)}, session={self.current_session is not None})"


# Global instance management
_default_service: Optional[AnalyticsService] = None


def get_analytics_service(config: Optional[AnalyticsConfig] = None) -> AnalyticsService:
    """Get or create global analytics service instance."""
    global _default_service
    if _default_service is None:
        _default_service = AnalyticsService(config)
    return _default_service


def clear_analytics_service() -> None:
    """Clear the global analytics service instance."""
    global _default_service
    _default_service = None


def create_analytics_service(config: Optional[AnalyticsConfig] = None) -> AnalyticsService:
    """Create a new analytics service (not global)."""
    return AnalyticsService(config)
