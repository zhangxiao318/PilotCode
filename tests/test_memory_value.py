"""Tests for memory value estimation module."""

import pytest
import time
from unittest.mock import Mock, patch

from pilotcode.services.memory_value import (
    InformationDensityCalculator,
    TaskRelevanceCalculator,
    HistoricalUtilityTracker,
    MemoryValueEstimator,
    FeedbackRecord,
    MessageValueScore,
    MemoryValueComponent,
)
from pilotcode.services.context_manager import ContextMessage, MessagePriority


class TestInformationDensityCalculator:
    """Tests for information density calculation."""
    
    def test_empty_content(self):
        calc = InformationDensityCalculator()
        assert calc.calculate("") == 0.0
    
    def test_high_density_technical_content(self):
        calc = InformationDensityCalculator()
        content = """
        def create_user(email: str, name: str) -> User:
            user = User(email=email, name=name)
            db.session.add(user)
            db.session.commit()
            return user
        """
        score = calc.calculate(content)
        assert score > 0.3  # Should have reasonable density
    
    def test_low_density_fluff_content(self):
        calc = InformationDensityCalculator()
        content = "This is a very repetitive sentence. " * 10
        score = calc.calculate(content)
        assert score < 0.5  # Should be low density
    
    def test_file_reference_density(self):
        calc = InformationDensityCalculator()
        content = "Check src/models/user.py and tests/test_user.py for details"
        score = calc.calculate(content)
        assert score > 0.2  # Should detect file references
    
    def test_structural_density(self):
        calc = InformationDensityCalculator()
        content = """
        - First item
        - Second item
        - Third item
        
        ```python
        code block
        ```
        """
        score = calc.calculate(content)
        assert score > 0.2  # Should detect structure


class TestTaskRelevanceCalculator:
    """Tests for task relevance calculation."""
    
    def test_no_task_context(self):
        calc = TaskRelevanceCalculator()
        msg = ContextMessage(role="user", content="Hello", priority=MessagePriority.USER)
        score = calc.calculate(msg, "")
        assert score == 0.5  # Neutral when no task context
    
    def test_keyword_overlap(self):
        calc = TaskRelevanceCalculator()
        msg = ContextMessage(
            role="user",
            content="I need to implement a user authentication system",
            priority=MessagePriority.USER
        )
        task = "Implement user login and authentication features"
        score = calc.calculate(msg, task)
        assert score > 0.3  # Should detect keyword overlap
    
    def test_file_context_relevance(self):
        calc = TaskRelevanceCalculator()
        msg = ContextMessage(
            role="assistant",
            content="Looking at src/auth.py to understand the authentication flow",
            priority=MessagePriority.ASSISTANT
        )
        score = calc.calculate(msg, "Fix authentication", ["src/auth.py"])
        assert score > 0.3  # Should detect file relevance
    
    def test_role_priority(self):
        calc = TaskRelevanceCalculator()
        
        system_msg = ContextMessage(role="system", content="System prompt")
        user_msg = ContextMessage(role="user", content="User request")
        tool_msg = ContextMessage(role="tool", content="Tool result")
        
        task = "Some task"
        
        system_score = calc.calculate(system_msg, task)
        user_score = calc.calculate(user_msg, task)
        tool_score = calc.calculate(tool_msg, task)
        
        assert system_score >= tool_score  # System >= tool
        assert user_score >= tool_score    # User >= tool


class TestHistoricalUtilityTracker:
    """Tests for historical utility tracking."""
    
    def test_initial_utility(self):
        tracker = HistoricalUtilityTracker()
        assert tracker.get_utility("msg_1") == 0.5  # Default neutral
    
    def test_record_feedback(self):
        tracker = HistoricalUtilityTracker()
        
        record = FeedbackRecord(
            message_id="msg_1",
            task_id="task_1",
            success=True,
            contribution_score=1.0,
        )
        tracker.record_feedback(record)
        
        assert tracker.get_utility("msg_1") > 0.5  # Should increase
    
    def test_multiple_feedback_averaging(self):
        tracker = HistoricalUtilityTracker()
        
        for i in range(5):
            tracker.record_feedback(FeedbackRecord(
                message_id="msg_1",
                task_id=f"task_{i}",
                success=True,
                contribution_score=1.0,
            ))
        
        utility = tracker.get_utility("msg_1")
        assert utility > 0.7  # Should converge to high value
    
    def test_negative_feedback(self):
        tracker = HistoricalUtilityTracker()
        
        tracker.record_feedback(FeedbackRecord(
            message_id="msg_1",
            task_id="task_1",
            success=False,
            contribution_score=0.5,
        ))
        
        assert tracker.get_utility("msg_1") <= 0.5  # Should decrease or stay same


class TestMemoryValueEstimator:
    """Tests for the main memory value estimator."""
    
    def test_estimate_value_basic(self):
        estimator = MemoryValueEstimator()
        
        msg = ContextMessage(
            role="user",
            content="Implement user authentication with JWT tokens",
            priority=MessagePriority.USER
        )
        
        score = estimator.estimate_value(
            msg,
            task_context="Implement JWT authentication",
            current_files=["src/auth.py"],
        )
        
        assert isinstance(score, MessageValueScore)
        assert 0 <= score.total_score <= 1
        assert score.info_density >= 0
        assert score.task_relevance >= 0
    
    def test_batch_estimate(self):
        estimator = MemoryValueEstimator()
        
        messages = [
            ContextMessage(role="user", content="Create login page"),
            ContextMessage(role="assistant", content="I'll help you create a login page"),
            ContextMessage(role="tool", content="File created successfully"),
        ]
        
        scores = estimator.batch_estimate(messages, "Create login page")
        
        assert len(scores) == 3
        assert all(isinstance(s, MessageValueScore) for s in scores)
    
    def test_get_top_k_messages(self):
        estimator = MemoryValueEstimator()
        
        messages = [
            ContextMessage(role="system", content="System prompt"),
            ContextMessage(role="user", content="Implement authentication"),
            ContextMessage(role="assistant", content="Here's the implementation..."),
            ContextMessage(role="tool", content="OK"),
        ]
        
        top_k = estimator.get_top_k_messages(messages, "Implement auth", k=2)
        
        assert len(top_k) == 2
        assert all(isinstance(m, ContextMessage) for m, _ in top_k)
        assert all(isinstance(s, MessageValueScore) for _, s in top_k)
    
    def test_record_outcome(self):
        estimator = MemoryValueEstimator()
        
        # First estimate to initialize
        msg = ContextMessage(role="user", content="Test", id="msg_1")
        estimator.estimate_value(msg, "Test task")
        
        # Record outcome
        estimator.record_outcome("msg_1", "task_1", success=True, contribution=1.0)
        
        # Utility should be updated
        utility = estimator.utility_tracker.get_utility("msg_1")
        assert utility != 0.5  # Should have changed from default
    
    def test_value_components_sum(self):
        estimator = MemoryValueEstimator()
        
        msg = ContextMessage(role="user", content="Implement login with JWT")
        score = estimator.estimate_value(msg, "Implement JWT login")
        
        # Check that weights sum to expected values
        weighted_sum = (
            MemoryValueComponent.INFO_DENSITY * score.info_density +
            MemoryValueComponent.TASK_RELEVANCE * score.task_relevance +
            MemoryValueComponent.HISTORICAL_UTILITY * score.historical_utility
        )
        
        # Total should be approximately weighted sum plus recency boost
        assert abs(score.total_score - weighted_sum) < 0.15  # Allow for recency boost


class TestGlobalEstimator:
    """Tests for global estimator functions."""
    
    def test_get_memory_value_estimator_singleton(self):
        from pilotcode.services.memory_value import (
            get_memory_value_estimator,
            reset_memory_value_estimator,
        )
        
        reset_memory_value_estimator()
        
        est1 = get_memory_value_estimator()
        est2 = get_memory_value_estimator()
        
        assert est1 is est2
        
        reset_memory_value_estimator()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
