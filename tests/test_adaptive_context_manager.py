"""Tests for adaptive context manager module."""

import pytest
import time
import tempfile
import os
from unittest.mock import Mock, patch

from pilotcode.services.adaptive_context_manager import (
    AdaptiveContextManager,
    AdaptiveContextConfig,
    TaskComplexity,
    CompressionDecision,
    AdaptiveContextStats,
    get_adaptive_context_manager,
    reset_adaptive_context_manager,
    create_adaptive_context_manager,
)
from pilotcode.services.context_manager import ContextMessage, MessagePriority
from pilotcode.services.task_aware_compression import CompressionMode
from pilotcode.services.compression_feedback import TaskOutcome


class TestAdaptiveContextConfig:
    """Tests for AdaptiveContextConfig."""
    
    def test_default_values(self):
        config = AdaptiveContextConfig()
        
        assert config.simple_task_tokens == 4000
        assert config.medium_task_tokens == 8000
        assert config.enable_value_estimation is True
        assert config.value_retention_target == 0.75


class TestTaskComplexityEstimation:
    """Tests for task complexity estimation."""
    
    def test_simple_task_detection(self):
        manager = AdaptiveContextManager()
        
        complexity = manager._estimate_complexity(
            "Explain what is Python",
            "explain"
        )
        
        assert complexity == TaskComplexity.SIMPLE
    
    def test_complex_task_detection(self):
        manager = AdaptiveContextManager()
        
        complexity = manager._estimate_complexity(
            "Implement a distributed microservices architecture with Kubernetes",
            "feature"
        )
        
        assert complexity in [TaskComplexity.COMPLEX, TaskComplexity.VERY_COMPLEX]
    
    def test_complex_indicators(self):
        manager = AdaptiveContextManager()
        
        complexity = manager._estimate_complexity(
            "Refactor and optimize the entire codebase",
            "refactor"
        )
        
        assert complexity == TaskComplexity.COMPLEX


class TestBudgetAdaptation:
    """Tests for budget adaptation."""
    
    def test_adapt_to_simple_task(self):
        manager = AdaptiveContextManager(AdaptiveContextConfig())
        manager.current_task_complexity = TaskComplexity.SIMPLE
        
        manager._adapt_budget_to_complexity()
        
        assert manager.budget.max_tokens == 4000
    
    def test_adapt_to_complex_task(self):
        config = AdaptiveContextConfig()
        manager = AdaptiveContextManager(config)
        manager.current_task_complexity = TaskComplexity.COMPLEX
        
        manager._adapt_budget_to_complexity()
        
        assert manager.budget.max_tokens == config.complex_task_tokens


class TestTaskContextManagement:
    """Tests for task context management."""
    
    def test_set_task_context(self):
        manager = AdaptiveContextManager()
        
        manager.set_task_context(
            description="Implement login feature",
            task_type="feature",
            current_files=["src/auth.py"],
            task_id="task_1",
        )
        
        assert manager.current_task_id == "task_1"
        assert manager.current_task_description == "Implement login feature"
        assert manager.current_files == ["src/auth.py"]
        assert manager.current_task_complexity == TaskComplexity.COMPLEX
    
    def test_infer_task_type(self):
        manager = AdaptiveContextManager()
        
        assert manager._infer_task_type("Fix the bug") == "debug"
        assert manager._infer_task_type("Add new feature") == "feature"
        assert manager._infer_task_type("Refactor code") == "refactor"
        assert manager._infer_task_type("Review the PR") == "review"


class TestAdaptiveCompression:
    """Tests for adaptive compression."""
    
    def test_adaptive_compact_without_task(self):
        manager = AdaptiveContextManager()
        
        # Add many messages to trigger compression
        for i in range(50):
            manager.add_message("user", f"Message {i} " * 100)
        
        result = manager.adaptive_compact()
        
        assert result is not None
    
    def test_adaptive_compact_with_task(self):
        manager = AdaptiveContextManager()
        
        manager.set_task_context(
            "Implement authentication",
            task_type="feature",
        )
        
        # Add messages
        for i in range(20):
            manager.add_message("user", f"Message {i} " * 50)
        
        result = manager.adaptive_compact()
        
        assert result.original_messages >= result.retained_messages
    
    def test_force_compact(self):
        manager = AdaptiveContextManager()
        
        # Add some messages
        for i in range(10):
            manager.add_message("user", f"Message {i}")
        
        result = manager.force_compact(CompressionMode.MODERATE)
        
        assert result is not None


class TestMessageValueScores:
    """Tests for message value scoring."""
    
    def test_get_message_value_scores_with_task(self):
        manager = AdaptiveContextManager()
        
        manager.set_task_context("Implement login")
        manager.add_message("user", "Create authentication system")
        
        scores = manager.get_message_value_scores()
        
        assert len(scores) == 1
        assert scores[0].total_score >= 0
    
    def test_get_message_value_scores_without_task(self):
        manager = AdaptiveContextManager()
        manager.add_message("user", "Hello")
        
        scores = manager.get_message_value_scores()
        
        assert scores == []


class TestTaskOutcomeRecording:
    """Tests for task outcome recording."""
    
    def test_record_success(self):
        manager = AdaptiveContextManager()
        
        manager.set_task_context("Test task")
        manager.add_message("user", "Test")
        
        # Force compression to trigger quality monitor setup
        manager.force_compact()
        
        manager.record_task_outcome(success=True)
        
        assert manager.current_task_id is None  # Reset
        assert manager.adaptive_stats.successful_tasks == 1
    
    def test_record_failure(self):
        manager = AdaptiveContextManager()
        
        manager.set_task_context("Test task")
        manager.add_message("user", "Test")
        
        # Force compression to trigger quality monitor setup
        manager.force_compact()
        
        manager.record_task_outcome(success=False, error_message="Error")
        
        assert manager.adaptive_stats.failed_tasks == 1


class TestStatsAndReporting:
    """Tests for statistics and reporting."""
    
    def test_get_adaptive_stats(self):
        manager = AdaptiveContextManager()
        
        stats = manager.get_adaptive_stats()
        
        assert "adaptive_stats" in stats
        assert "current_task" in stats
        assert "feedback_report" in stats
    
    def test_get_messages_with_scores(self):
        manager = AdaptiveContextManager()
        
        manager.set_task_context("Test task")
        manager.add_message("user", "Hello")
        
        messages = manager.get_messages_with_scores()
        
        assert len(messages) == 1
        assert "value_score" in messages[0]


class TestAdaptiveContextStats:
    """Tests for AdaptiveContextStats."""
    
    def test_record_compression(self):
        stats = AdaptiveContextStats()
        
        decision = CompressionDecision(
            timestamp=time.time(),
            original_tokens=5000,
            compressed_tokens=3000,
            strategy_used="moderate",
            value_retention=0.8,
            trigger_reason="critical",
        )
        
        stats.record_compression(decision)
        
        assert stats.total_compressions == 1
        assert stats.total_tokens_saved == 2000
        assert stats.avg_value_retention == 0.8
    
    def test_record_task_outcome(self):
        stats = AdaptiveContextStats()
        
        stats.record_task_outcome(success=True)
        stats.record_task_outcome(success=False)
        
        assert stats.successful_tasks == 1
        assert stats.failed_tasks == 1


class TestSerialization:
    """Tests for serialization."""
    
    def test_to_dict(self):
        manager = AdaptiveContextManager()
        manager.set_task_context("Test")
        
        data = manager.to_dict()
        
        assert "adaptive_config" in data
        assert "adaptive_stats" in data


class TestGlobalManager:
    """Tests for global manager functions."""
    
    def test_singleton(self):
        reset_adaptive_context_manager()
        
        m1 = get_adaptive_context_manager()
        m2 = get_adaptive_context_manager()
        
        assert m1 is m2
        
        reset_adaptive_context_manager()
    
    def test_create_new_manager(self):
        m1 = create_adaptive_context_manager()
        m2 = create_adaptive_context_manager()
        
        assert m1 is not m2  # Should be different instances


class TestIntegration:
    """Integration tests for adaptive context manager."""
    
    def test_full_workflow(self):
        """Test a complete workflow with compression and feedback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AdaptiveContextConfig(
                feedback_storage_path=os.path.join(tmpdir, "feedback.json"),
                memory_storage_path=os.path.join(tmpdir, "memory.json"),
            )
            
            manager = AdaptiveContextManager(config)
            
            # Set task context
            manager.set_task_context(
                "Implement user authentication with JWT",
                task_type="feature",
                current_files=["src/auth.py"],
            )
            
            # Simulate conversation
            manager.add_message("user", "I need to implement login")
            manager.add_message("assistant", "I'll help you create authentication")
            manager.add_message("user", "Use JWT tokens")
            
            # Force compression
            result = manager.force_compact(CompressionMode.LIGHT)
            
            # Record outcome
            manager.record_task_outcome(success=True)
            
            # Check stats
            stats = manager.get_adaptive_stats()
            assert stats["adaptive_stats"]["task_success_rate"] == 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
