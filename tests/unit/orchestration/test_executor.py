"""Tests for the task executor."""

import pytest
import asyncio
from datetime import datetime

from pilotcode.orchestration.executor import (
    TaskExecutor,
    ExecutionResult,
    ExecutionStatus,
    ExecutionPlan,
)


class MockSubtask:
    """Mock subtask for testing."""
    
    def __init__(self, id, description, prompt, role="coder", dependencies=None):
        self.id = id
        self.description = description
        self.prompt = prompt
        self.role = role
        self.dependencies = dependencies or []


class MockAgent:
    """Mock agent for testing."""
    
    def __init__(self, role, prompt):
        self.role = role
        self.prompt = prompt
        self.tools_used = ["Read", "Write"]


class TestExecutionResult:
    """Test ExecutionResult dataclass."""
    
    def test_duration_calculation(self):
        """Test duration calculation."""
        started = datetime.now()
        completed = datetime.now()
        
        result = ExecutionResult(
            task_id="test1",
            status=ExecutionStatus.COMPLETED,
            started_at=started,
            completed_at=completed
        )
        
        assert result.duration_seconds >= 0
    
    def test_duration_without_completion(self):
        """Test duration without completion time."""
        result = ExecutionResult(
            task_id="test1",
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now()
        )
        
        assert result.duration_seconds == 0.0


class TestExecutionPlan:
    """Test ExecutionPlan dataclass."""
    
    def test_is_complete(self):
        """Test completion detection."""
        plan = ExecutionPlan(
            task_id="plan1",
            original_task="Test task",
            strategy="sequential",
            executions=[
                ExecutionResult(task_id="t1", status=ExecutionStatus.COMPLETED),
                ExecutionResult(task_id="t2", status=ExecutionStatus.COMPLETED),
            ]
        )
        
        assert plan.is_complete
        assert plan.success_rate == 1.0
    
    def test_is_not_complete(self):
        """Test incomplete plan detection."""
        plan = ExecutionPlan(
            task_id="plan1",
            original_task="Test task",
            strategy="sequential",
            executions=[
                ExecutionResult(task_id="t1", status=ExecutionStatus.COMPLETED),
                ExecutionResult(task_id="t2", status=ExecutionStatus.RUNNING),
            ]
        )
        
        assert not plan.is_complete
    
    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        plan = ExecutionPlan(
            task_id="plan1",
            original_task="Test task",
            strategy="sequential",
            executions=[
                ExecutionResult(task_id="t1", status=ExecutionStatus.COMPLETED),
                ExecutionResult(task_id="t2", status=ExecutionStatus.COMPLETED),
                ExecutionResult(task_id="t3", status=ExecutionStatus.FAILED),
            ]
        )
        
        assert plan.success_rate == 2/3
    
    def test_get_summary(self):
        """Test summary generation."""
        plan = ExecutionPlan(
            task_id="plan1",
            original_task="Test task",
            strategy="sequential",
            executions=[
                ExecutionResult(task_id="t1", status=ExecutionStatus.COMPLETED),
                ExecutionResult(task_id="t2", status=ExecutionStatus.FAILED),
            ]
        )
        
        summary = plan.get_summary()
        
        assert summary["task_id"] == "plan1"
        assert summary["total_subtasks"] == 2
        assert summary["completed"] == 1
        assert summary["failed"] == 1
        assert summary["success_rate"] == 0.5


class TestTaskExecutor:
    """Test TaskExecutor."""
    
    @pytest.fixture
    def executor(self):
        """Create test executor."""
        def mock_agent_factory(role, prompt):
            return MockAgent(role, prompt)
        
        return TaskExecutor(mock_agent_factory)
    
    @pytest.fixture
    def mock_subtasks(self):
        """Create mock subtasks."""
        return [
            MockSubtask("t1", "Task 1", "Do task 1"),
            MockSubtask("t2", "Task 2", "Do task 2"),
        ]
    
    @pytest.mark.asyncio
    async def test_execute_sequential(self, executor, mock_subtasks):
        """Test sequential execution."""
        progress_events = []
        
        def on_progress(event, data):
            progress_events.append((event, data))
        
        executor.on_progress(on_progress)
        
        # Mock the _run_agent method
        async def mock_run(agent, prompt, context):
            return f"Result for {prompt}"
        
        executor._run_agent = mock_run
        
        results = await executor.execute_sequential(mock_subtasks)
        
        assert len(results) == 2
        assert results[0].status == ExecutionStatus.COMPLETED
        assert results[1].status == ExecutionStatus.COMPLETED
        assert len(progress_events) == 4  # 2 starts + 2 completions
    
    @pytest.mark.asyncio
    async def test_execute_parallel(self, executor, mock_subtasks):
        """Test parallel execution."""
        async def mock_run(agent, prompt, context):
            return f"Result for {prompt}"
        
        executor._run_agent = mock_run
        
        results = await executor.execute_parallel(mock_subtasks)
        
        assert len(results) == 2
        assert all(r.status == ExecutionStatus.COMPLETED for r in results)
    
    @pytest.mark.asyncio
    async def test_execute_with_dependencies(self, executor):
        """Test dependency-aware execution."""
        subtasks = [
            MockSubtask("t1", "Task 1", "Do task 1", dependencies=[]),
            MockSubtask("t2", "Task 2", "Do task 2", dependencies=["t1"]),
            MockSubtask("t3", "Task 3", "Do task 3", dependencies=["t1"]),
        ]
        
        async def mock_run(agent, prompt, context):
            return f"Result"
        
        executor._run_agent = mock_run
        
        results = await executor.execute_with_dependencies(subtasks)
        
        assert len(results) == 3
        assert all(r.status == ExecutionStatus.COMPLETED for r in results)
    
    @pytest.mark.asyncio
    async def test_execute_hierarchical(self, executor):
        """Test hierarchical execution."""
        workers = [
            MockSubtask("w1", "Worker 1", "Do work 1"),
            MockSubtask("w2", "Worker 2", "Do work 2"),
        ]
        
        async def mock_run(agent, prompt, context):
            return f"Result"
        
        executor._run_agent = mock_run
        
        results = await executor.execute_hierarchical(
            "Main task",
            workers
        )
        
        # Should have worker results + synthesis
        assert len(results) >= 2
    
    def test_enhance_prompt_with_context(self, executor):
        """Test prompt enhancement."""
        prompt = "Do something"
        context = "Previous work done"
        
        enhanced = executor._enhance_prompt_with_context(prompt, context, [])
        
        assert "Previous work" in enhanced
        assert prompt in enhanced
    
    def test_build_synthesis_prompt(self, executor):
        """Test synthesis prompt building."""
        results = [
            ExecutionResult(
                task_id="w1",
                status=ExecutionStatus.COMPLETED,
                output="Output 1"
            ),
            ExecutionResult(
                task_id="w2",
                status=ExecutionStatus.COMPLETED,
                output="Output 2"
            ),
        ]
        
        prompt = executor._build_synthesis_prompt("Task", results)
        
        assert "Task" in prompt
        assert "Output 1" in prompt
        assert "Output 2" in prompt
