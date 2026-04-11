"""Tests for compression feedback module."""

import pytest
import time
import tempfile
import os
from unittest.mock import Mock, patch

from pilotcode.services.compression_feedback import (
    CompressionEvent,
    CompressionStatistics,
    CompressionFeedbackLoop,
    CompressionQualityMonitor,
    TaskOutcome,
    CompressionQuality,
    CompressionMode,
)
from pilotcode.services.task_aware_compression import (
    TaskAwareCompressionResult,
    TaskContext,
    RetentionDecision,
)


class TestCompressionEvent:
    """Tests for CompressionEvent."""

    def test_to_dict(self):
        event = CompressionEvent(
            event_id="evt_1",
            timestamp=time.time(),
            task_id="task_1",
            task_description="Test task",
            original_message_count=10,
            original_token_count=5000,
            compression_mode=CompressionMode.MODERATE,
            target_tokens=3000,
            compressed_message_count=6,
            compressed_token_count=2800,
            retained_message_ids=["m1", "m2"],
            removed_message_ids=["m3", "m4"],
            summarized_message_ids=["m5"],
            value_retention_rate=0.8,
            outcome=TaskOutcome.SUCCESS,
            quality_rating=CompressionQuality.GOOD,
        )

        d = event.to_dict()

        assert d["event_id"] == "evt_1"
        assert d["outcome"] == "success"
        assert d["quality_rating"] == 4

    def test_from_dict(self):
        data = {
            "event_id": "evt_1",
            "timestamp": time.time(),
            "task_id": "task_1",
            "task_description": "Test",
            "original_message_count": 10,
            "original_token_count": 5000,
            "compression_mode": "moderate",
            "target_tokens": 3000,
            "compressed_message_count": 6,
            "compressed_token_count": 2800,
            "retained_message_ids": ["m1"],
            "removed_message_ids": ["m2"],
            "summarized_message_ids": [],
            "value_retention_rate": 0.8,
            "outcome": "success",
            "quality_rating": 4,
            "outcome_timestamp": time.time(),
            "error_message": None,
        }

        event = CompressionEvent.from_dict(data)

        assert event.event_id == "evt_1"
        assert event.outcome == TaskOutcome.SUCCESS
        assert event.quality_rating == CompressionQuality.GOOD


class TestCompressionStatistics:
    """Tests for CompressionStatistics."""

    def test_record_completion_success(self):
        stats = CompressionStatistics()

        event = CompressionEvent(
            event_id="evt_1",
            timestamp=time.time(),
            task_id="task_1",
            task_description="Test",
            original_message_count=10,
            original_token_count=5000,
            compression_mode=CompressionMode.MODERATE,
            target_tokens=3000,
            compressed_message_count=6,
            compressed_token_count=2800,
            retained_message_ids=[],
            removed_message_ids=[],
            summarized_message_ids=[],
            value_retention_rate=0.8,
            outcome=TaskOutcome.SUCCESS,
        )

        stats.record_completion(event)

        assert stats.completed_tasks == 1
        assert stats.successful_tasks == 1
        assert stats.failed_tasks == 0

    def test_get_mode_success_rate(self):
        stats = CompressionStatistics()

        stats.success_rate_by_mode["moderate"] = (8, 10)  # 8 success out of 10

        rate = stats.get_mode_success_rate(CompressionMode.MODERATE)
        assert rate == 0.8

    def test_get_mode_success_rate_empty(self):
        stats = CompressionStatistics()

        rate = stats.get_mode_success_rate(CompressionMode.MODERATE)
        assert rate == 0.5  # Default


class TestCompressionFeedbackLoop:
    """Tests for CompressionFeedbackLoop."""

    def test_record_compression(self):
        loop = CompressionFeedbackLoop()

        result = TaskAwareCompressionResult(
            original_messages=10,
            retained_messages=6,
            summarized_messages=2,
            removed_messages=2,
            original_tokens=5000,
            compressed_tokens=3000,
            value_retention_rate=0.8,
        )

        event_id = loop.record_compression(result, "Test task", "task_1")

        assert event_id in loop.events
        assert "task_1" in loop.pending_events
        assert loop.statistics.total_compressions == 1

    def test_record_outcome(self):
        loop = CompressionFeedbackLoop()

        # First record compression
        result = TaskAwareCompressionResult(
            original_messages=10,
            retained_messages=6,
            summarized_messages=2,
            removed_messages=2,
            original_tokens=5000,
            compressed_tokens=3000,
            value_retention_rate=0.8,
        )
        event_id = loop.record_compression(result, "Test task", "task_1")

        # Then record outcome
        event = loop.record_outcome("task_1", TaskOutcome.SUCCESS)

        assert event.outcome == TaskOutcome.SUCCESS
        assert event.quality_rating is not None
        assert "task_1" not in loop.pending_events

    def test_infer_task_type(self):
        loop = CompressionFeedbackLoop()

        assert loop._infer_task_type("Fix the login bug") == "debug"
        assert loop._infer_task_type("Implement new feature") == "feature"
        assert loop._infer_task_type("Refactor the code") == "refactor"
        assert loop._infer_task_type("Review this PR") == "review"
        assert loop._infer_task_type("Random task") == "general"

    def test_get_recommended_mode_with_history(self):
        loop = CompressionFeedbackLoop()

        # Add some history
        loop.mode_effectiveness["moderate"] = [4, 5, 4, 5, 4]
        loop.mode_effectiveness["aggressive"] = [2, 3, 2, 2, 3]

        mode = loop.get_recommended_mode("Some task")

        assert mode == CompressionMode.MODERATE  # Higher average

    def test_get_recommended_mode_default(self):
        loop = CompressionFeedbackLoop()

        mode = loop.get_recommended_mode("Some task")

        assert mode == CompressionMode.MODERATE  # Default

    def test_get_compression_report(self):
        loop = CompressionFeedbackLoop()

        report = loop.get_compression_report()

        assert "statistics" in report
        assert "mode_effectiveness" in report
        assert "task_type_patterns" in report
        assert "recent_performance" in report

    def test_persistence(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            storage_path = f.name

        try:
            # Create and save
            loop1 = CompressionFeedbackLoop(storage_path=storage_path)
            result = TaskAwareCompressionResult(
                original_messages=10,
                retained_messages=6,
                summarized_messages=0,
                removed_messages=4,
                original_tokens=5000,
                compressed_tokens=3000,
                value_retention_rate=0.8,
            )
            loop1.record_compression(result, "Test task")

            # Load in new instance
            loop2 = CompressionFeedbackLoop(storage_path=storage_path)
            assert len(loop2.events) == 1
        finally:
            os.unlink(storage_path)


class TestCompressionQualityMonitor:
    """Tests for CompressionQualityMonitor."""

    def test_start_and_complete_task(self):
        loop = CompressionFeedbackLoop()
        monitor = CompressionQualityMonitor(loop)

        # Record compression first
        result = TaskAwareCompressionResult(
            original_messages=10,
            retained_messages=6,
            summarized_messages=0,
            removed_messages=4,
            original_tokens=5000,
            compressed_tokens=3000,
            value_retention_rate=0.8,
        )
        event_id = loop.record_compression(result, "Test task", "task_1")

        # Monitor task
        monitor.start_task(event_id)
        monitor.record_access("m1", found=True)
        monitor.report_helpfulness(0.8)

        event = monitor.complete_task(TaskOutcome.SUCCESS)

        assert event.outcome == TaskOutcome.SUCCESS

    def test_infer_quality_excellent(self):
        loop = CompressionFeedbackLoop()
        monitor = CompressionQualityMonitor(loop)

        monitor.messages_accessed = {"m1", "m2", "m3"}
        monitor.messages_missing = set()  # No missing
        monitor.compression_helpfulness = 0.9

        quality = monitor._infer_quality(TaskOutcome.SUCCESS)

        assert quality == CompressionQuality.EXCELLENT

    def test_infer_quality_bad(self):
        loop = CompressionFeedbackLoop()
        monitor = CompressionQualityMonitor(loop)

        monitor.messages_accessed = {"m1"}
        monitor.messages_missing = {"m2", "m3", "m4"}  # Many missing

        quality = monitor._infer_quality(TaskOutcome.FAILURE)

        assert quality == CompressionQuality.BAD


class TestGlobalFeedbackLoop:
    """Tests for global feedback loop."""

    def test_singleton(self):
        from pilotcode.services.compression_feedback import (
            get_compression_feedback_loop,
            reset_compression_feedback_loop,
        )

        reset_compression_feedback_loop()

        f1 = get_compression_feedback_loop()
        f2 = get_compression_feedback_loop()

        assert f1 is f2

        reset_compression_feedback_loop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
