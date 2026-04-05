"""Tests for Analytics Service."""

import pytest
import tempfile
import time
from unittest.mock import MagicMock, patch

from pilotcode.services.analytics_service import (
    AnalyticsService,
    AnalyticsConfig,
    AnalyticsEvent,
    AnalyticsEventType,
    UsageStats,
    SessionStats,
    get_analytics_service,
    clear_analytics_service,
    create_analytics_service,
)


# Fixtures
@pytest.fixture
def basic_config():
    """Create basic analytics config."""
    return AnalyticsConfig(
        enabled=True,
        track_commands=True,
        track_tools=True,
        track_tokens=True,
        track_costs=True,
        track_errors=True,
    )


@pytest.fixture
def analytics_service(basic_config):
    """Create an analytics service."""
    return AnalyticsService(basic_config)


# Test AnalyticsEvent
class TestAnalyticsEvent:
    """Test AnalyticsEvent dataclass."""
    
    def test_event_creation(self):
        """Test creating analytics event."""
        event = AnalyticsEvent(
            event_type=AnalyticsEventType.COMMAND,
            name="/help",
            duration_ms=100.0,
            tokens_input=10,
            tokens_output=20,
        )
        
        assert event.event_type == AnalyticsEventType.COMMAND
        assert event.name == "/help"
        assert event.duration_ms == 100.0
        assert event.tokens_input == 10
        assert event.tokens_output == 20
    
    def test_event_to_dict(self):
        """Test event serialization."""
        event = AnalyticsEvent(
            event_type=AnalyticsEventType.TOOL,
            name="FileRead",
            success=True,
        )
        
        data = event.to_dict()
        
        assert data["event_type"] == "tool"
        assert data["name"] == "FileRead"
        assert data["success"] is True
    
    def test_event_from_dict(self):
        """Test event deserialization."""
        data = {
            "event_type": "command",
            "name": "/test",
            "timestamp": 12345.0,
            "duration_ms": 50.0,
            "tokens_input": 0,
            "tokens_output": 0,
            "cost": 0.0,
            "success": True,
            "error_message": None,
            "metadata": {},
            "session_id": "test_session",
        }
        
        event = AnalyticsEvent.from_dict(data)
        
        assert event.event_type == AnalyticsEventType.COMMAND
        assert event.name == "/test"
        assert event.session_id == "test_session"


# Test UsageStats
class TestUsageStats:
    """Test UsageStats dataclass."""
    
    def test_stats_creation(self):
        """Test creating usage stats."""
        stats = UsageStats(
            total_commands=10,
            total_tools=5,
            total_cost=1.5,
        )
        
        assert stats.total_commands == 10
        assert stats.total_tools == 5
        assert stats.total_cost == 1.5
    
    def test_stats_to_dict(self):
        """Test stats serialization."""
        stats = UsageStats(
            total_commands=5,
            commands_by_name={"/help": 3, "/test": 2},
        )
        
        data = stats.to_dict()
        
        assert data["total_commands"] == 5
        assert data["commands_by_name"]["/help"] == 3


# Test SessionStats
class TestSessionStats:
    """Test SessionStats dataclass."""
    
    def test_session_creation(self):
        """Test creating session stats."""
        session = SessionStats(
            session_id="test_123",
            start_time=time.time(),
        )
        
        assert session.session_id == "test_123"
        assert session.event_count == 0
        assert session.total_cost == 0.0
    
    def test_session_duration(self):
        """Test session duration calculation."""
        start = time.time()
        session = SessionStats(
            session_id="test",
            start_time=start,
        )
        
        # Duration should be small
        assert session.duration_seconds >= 0
        assert session.duration_seconds < 1.0
        
        # End session
        session.end_time = start + 10.0
        assert session.duration_seconds == 10.0
    
    def test_session_to_dict(self):
        """Test session serialization."""
        session = SessionStats(
            session_id="test",
            start_time=1000.0,
            end_time=1010.0,
            commands_used={"/help", "/test"},
        )
        
        data = session.to_dict()
        
        assert data["session_id"] == "test"
        assert data["duration_seconds"] == 10.0
        assert "/help" in data["commands_used"]


# Test AnalyticsService basic functionality
class TestAnalyticsServiceBasic:
    """Test basic AnalyticsService functionality."""
    
    def test_service_creation(self, basic_config):
        """Test creating analytics service."""
        service = AnalyticsService(basic_config)
        
        assert service.config == basic_config
        assert len(service.events) == 0
        assert service.current_session is None
    
    def test_disabled_service(self):
        """Test disabled service doesn't track events."""
        config = AnalyticsConfig(enabled=False)
        service = AnalyticsService(config)
        
        service.track_command("/help")
        
        assert len(service.events) == 0
    
    def test_start_session(self, analytics_service):
        """Test starting a session."""
        session = analytics_service.start_session("test_session")
        
        assert session is not None
        assert session.session_id == "test_session"
        assert analytics_service.current_session == session
        assert len(analytics_service.events) == 1  # Session start event
    
    def test_end_session(self, analytics_service):
        """Test ending a session."""
        analytics_service.start_session("test")
        
        session = analytics_service.end_session()
        
        assert session is not None
        assert session.end_time is not None
        assert analytics_service.current_session is None
        assert len(analytics_service.events) == 2  # Start + end events


# Test event tracking
class TestEventTracking:
    """Test event tracking functionality."""
    
    def test_track_command(self, analytics_service):
        """Test tracking a command."""
        analytics_service.track_command("/help", duration_ms=100.0, success=True)
        
        assert len(analytics_service.events) == 1
        assert analytics_service.events[0].event_type == AnalyticsEventType.COMMAND
        assert analytics_service.events[0].name == "/help"
    
    def test_track_tool(self, analytics_service):
        """Test tracking a tool."""
        analytics_service.track_tool("FileRead", duration_ms=200.0, tokens=50)
        
        assert len(analytics_service.events) == 1
        assert analytics_service.events[0].event_type == AnalyticsEventType.TOOL
        assert analytics_service.events[0].tokens_output == 50
    
    def test_track_model_request(self, analytics_service):
        """Test tracking a model request."""
        analytics_service.track_model_request(
            model_name="gpt-4",
            tokens_input=1000,
            tokens_output=500,
            duration_ms=1500.0,
        )
        
        assert len(analytics_service.events) == 1
        assert analytics_service.events[0].tokens_input == 1000
        assert analytics_service.events[0].tokens_output == 500
        assert analytics_service.events[0].cost > 0  # Cost should be calculated
    
    def test_track_error(self, analytics_service):
        """Test tracking an error."""
        analytics_service.track_error(
            error_type="FileNotFound",
            error_message="File not found: test.txt",
        )
        
        assert len(analytics_service.events) == 1
        assert analytics_service.events[0].event_type == AnalyticsEventType.ERROR
        assert analytics_service.events[0].success is False
    
    def test_track_command_disabled(self):
        """Test tracking disabled for commands."""
        config = AnalyticsConfig(track_commands=False)
        service = AnalyticsService(config)
        
        service.track_command("/help")
        
        assert len(service.events) == 0
    
    def test_track_tool_disabled(self):
        """Test tracking disabled for tools."""
        config = AnalyticsConfig(track_tools=False)
        service = AnalyticsService(config)
        
        service.track_tool("FileRead")
        
        assert len(service.events) == 0


# Test statistics
class TestStatistics:
    """Test statistics aggregation."""
    
    def test_get_stats(self, analytics_service):
        """Test getting usage stats."""
        analytics_service.track_command("/help")
        analytics_service.track_command("/help")
        analytics_service.track_tool("FileRead")
        
        stats = analytics_service.get_stats()
        
        assert stats.total_commands == 2
        assert stats.total_tools == 1
        assert stats.commands_by_name["/help"] == 2
    
    def test_get_events_filtered(self, analytics_service):
        """Test getting filtered events."""
        analytics_service.track_command("/help")
        analytics_service.track_tool("FileRead")
        analytics_service.track_error("Error", "message")
        
        commands = analytics_service.get_events(event_type=AnalyticsEventType.COMMAND)
        
        assert len(commands) == 1
        assert commands[0].name == "/help"
    
    def test_get_events_with_limit(self, analytics_service):
        """Test getting events with limit."""
        for i in range(10):
            analytics_service.track_command(f"/cmd{i}")
        
        events = analytics_service.get_events(limit=5)
        
        assert len(events) == 5
    
    def test_get_summary(self, analytics_service):
        """Test getting summary."""
        analytics_service.start_session("test")
        analytics_service.track_command("/help")
        analytics_service.track_tool("FileRead")
        
        summary = analytics_service.get_summary()
        
        assert summary["session"] is not None
        # Events: session_start + command + tool
        assert summary["total_events"] == 3
        assert len(summary["top_commands"]) >= 1


# Test cost calculation
class TestCostCalculation:
    """Test cost calculation."""
    
    def test_cost_calculation(self):
        """Test cost is calculated correctly."""
        config = AnalyticsConfig(
            cost_per_1k_input=0.01,
            cost_per_1k_output=0.03,
        )
        service = AnalyticsService(config)
        
        service.track_model_request(tokens_input=1000, tokens_output=500)
        
        # Cost = (1000/1000)*0.01 + (500/1000)*0.03 = 0.01 + 0.015 = 0.025
        expected_cost = 0.025
        assert abs(service.events[0].cost - expected_cost) < 0.001
    
    def test_cost_tracking_disabled(self):
        """Test cost not tracked when disabled."""
        config = AnalyticsConfig(track_costs=False)
        service = AnalyticsService(config)
        
        service.track_model_request(tokens_input=1000, tokens_output=500)
        
        assert service.events[0].cost == 0.0


# Test session tracking
class TestSessionTracking:
    """Test session tracking."""
    
    def test_session_commands_tracking(self, analytics_service):
        """Test tracking commands in session."""
        analytics_service.start_session("test")
        analytics_service.track_command("/help")
        analytics_service.track_command("/test")
        
        session = analytics_service.get_session_stats()
        
        assert "/help" in session.commands_used
        assert "/test" in session.commands_used
        assert session.event_count == 2  # 2 commands (start event handled separately)
    
    def test_session_tools_tracking(self, analytics_service):
        """Test tracking tools in session."""
        analytics_service.start_session("test")
        analytics_service.track_tool("FileRead")
        analytics_service.track_tool("FileWrite")
        
        session = analytics_service.get_session_stats()
        
        assert "FileRead" in session.tools_used
        assert "FileWrite" in session.tools_used
    
    def test_session_cost_tracking(self, analytics_service):
        """Test tracking cost in session."""
        analytics_service.start_session("test")
        analytics_service.track_model_request(tokens_input=2000, tokens_output=1000)
        
        session = analytics_service.get_session_stats()
        
        assert session.total_cost > 0


# Test persistence
class TestPersistence:
    """Test save/load functionality."""
    
    def test_export_import(self, analytics_service, tmp_path):
        """Test exporting and importing analytics."""
        analytics_service.track_command("/help")
        analytics_service.track_tool("FileRead")
        
        filepath = tmp_path / "analytics.json"
        analytics_service.export_to_file(str(filepath))
        
        assert filepath.exists()
        
        # Import
        imported = AnalyticsService.import_from_file(str(filepath))
        
        assert len(imported.events) == 2
    
    def test_reset(self, analytics_service):
        """Test resetting analytics."""
        analytics_service.track_command("/help")
        analytics_service.track_tool("FileRead")
        
        analytics_service.reset()
        
        assert len(analytics_service.events) == 0
        assert analytics_service.get_stats().total_commands == 0


# Test global instance
class TestGlobalInstance:
    """Test global analytics service instance."""
    
    def test_get_analytics_service(self):
        """Test getting global instance."""
        clear_analytics_service()
        
        service1 = get_analytics_service()
        service2 = get_analytics_service()
        
        assert service1 is service2
    
    def test_clear_analytics_service(self):
        """Test clearing global instance."""
        service1 = get_analytics_service()
        clear_analytics_service()
        service2 = get_analytics_service()
        
        assert service1 is not service2
    
    def test_create_analytics_service(self):
        """Test creating new instance."""
        service1 = create_analytics_service()
        service2 = create_analytics_service()
        
        assert service1 is not service2


# Test event limits
class TestEventLimits:
    """Test event limit functionality."""
    
    def test_max_events_limit(self):
        """Test that events are trimmed when limit reached."""
        config = AnalyticsConfig(max_events=5)
        service = AnalyticsService(config)
        
        for i in range(10):
            service.track_command(f"/cmd{i}")
        
        assert len(service.events) == 5
    
    def test_events_kept_are_recent(self):
        """Test that most recent events are kept."""
        config = AnalyticsConfig(max_events=3)
        service = AnalyticsService(config)
        
        for i in range(5):
            service.track_command(f"/cmd{i}")
        
        # Should keep the last 3
        assert service.events[0].name == "/cmd2"
        assert service.events[2].name == "/cmd4"


# Test cost breakdown
class TestCostBreakdown:
    """Test cost breakdown functionality."""
    
    def test_get_cost_breakdown(self, analytics_service):
        """Test getting cost breakdown."""
        # Track model request with cost
        analytics_service.track_model_request(tokens_input=10000, tokens_output=5000)
        
        breakdown = analytics_service.get_cost_breakdown()
        
        assert breakdown["total"] > 0  # Should have some cost


# Test repr
class TestRepresentation:
    """Test string representation."""
    
    def test_repr(self, analytics_service):
        """Test __repr__ method."""
        repr_str = repr(analytics_service)
        
        assert "AnalyticsService" in repr_str
        assert "events=0" in repr_str
