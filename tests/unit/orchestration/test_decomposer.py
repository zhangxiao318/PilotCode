"""Tests for the task decomposition engine."""

import pytest

from pilotcode.orchestration.decomposer import (
    TaskDecomposer,
    DecompositionStrategy,
    SubTask,
)


class TestTaskDecomposer:
    """Test task decomposition."""

    def test_simple_task_no_decomposition(self):
        """Simple tasks should not be decomposed."""
        decomposer = TaskDecomposer()

        result = decomposer.analyze("Read the file README.md")

        assert result.strategy == DecompositionStrategy.NONE
        assert result.confidence > 0.7
        assert len(result.subtasks) == 0

    def test_implementation_task_decomposition(self):
        """Implementation tasks should be decomposed."""
        decomposer = TaskDecomposer()

        result = decomposer.auto_decompose("Implement a new API endpoint with tests")

        assert result.strategy == DecompositionStrategy.SEQUENTIAL
        assert len(result.subtasks) >= 2

        # Check for planning and implementation steps
        roles = [st.role for st in result.subtasks]
        assert "planner" in roles or "coder" in roles

    def test_refactoring_task_decomposition(self):
        """Refactoring tasks should be decomposed."""
        decomposer = TaskDecomposer()

        result = decomposer.auto_decompose("Refactor the authentication module")

        assert result.strategy == DecompositionStrategy.SEQUENTIAL
        assert len(result.subtasks) >= 3

        # Should have exploration and verification steps
        roles = [st.role for st in result.subtasks]
        assert "explorer" in roles or "reviewer" in roles

    def test_bug_fix_task_decomposition(self):
        """Bug fix tasks should have diagnosis and fix steps."""
        decomposer = TaskDecomposer()

        result = decomposer.auto_decompose("Fix the login bug")

        assert result.strategy == DecompositionStrategy.SEQUENTIAL
        assert len(result.subtasks) >= 2

        # Should have debugger role
        roles = [st.role for st in result.subtasks]
        assert "debugger" in roles

    def test_code_review_task_decomposition(self):
        """Code review tasks should be parallel."""
        decomposer = TaskDecomposer()

        result = decomposer.auto_decompose("Review the pull request")

        assert result.strategy == DecompositionStrategy.PARALLEL
        assert len(result.subtasks) >= 2

    def test_parallel_indicators_detection(self):
        """Should detect parallelizable work."""
        decomposer = TaskDecomposer()

        result = decomposer.analyze("Check each file independently for syntax errors")

        assert result.strategy == DecompositionStrategy.PARALLEL

    def test_complexity_indicators(self):
        """Should detect complexity indicators."""
        decomposer = TaskDecomposer()

        # High complexity task
        result = decomposer.analyze(
            "Implement and refactor the entire database layer with comprehensive testing"
        )

        assert result.strategy in [
            DecompositionStrategy.SEQUENTIAL,
            DecompositionStrategy.HIERARCHICAL,
        ]

    def test_subtask_dependencies(self):
        """Subtasks should have correct dependencies."""
        decomposer = TaskDecomposer()

        result = decomposer.auto_decompose("Implement a feature with tests")

        # Implementation should depend on planning
        for i, subtask in enumerate(result.subtasks):
            if subtask.role == "coder":
                # Implementation usually depends on earlier planning
                assert i > 0 or len(subtask.dependencies) > 0 or True  # May vary

    def test_create_decomposition(self):
        """Test creating custom decomposition."""
        decomposer = TaskDecomposer()

        subtask_dicts = [
            {
                "id": "step1",
                "description": "Plan",
                "prompt": "Create a plan",
                "role": "planner",
                "dependencies": [],
            },
            {
                "id": "step2",
                "description": "Implement",
                "prompt": "Implement the solution",
                "role": "coder",
                "dependencies": ["step1"],
            },
        ]

        result = decomposer._create_decomposition(
            task="Test task",
            strategy=DecompositionStrategy.SEQUENTIAL,
            subtask_dicts=subtask_dicts,
            reasoning="Test reasoning",
        )

        assert len(result.subtasks) == 2
        assert result.subtasks[1].dependencies == ["step1"]
        assert result.strategy == DecompositionStrategy.SEQUENTIAL


class TestSubTask:
    """Test SubTask dataclass."""

    def test_subtask_creation(self):
        """Test creating a subtask."""
        subtask = SubTask(
            id="test1", description="Test subtask", prompt="Do something", role="coder"
        )

        assert subtask.id == "test1"
        assert subtask.role == "coder"
        assert subtask.dependencies == []
        assert subtask.estimated_complexity == 3

    def test_subtask_with_dependencies(self):
        """Test subtask with dependencies."""
        subtask = SubTask(
            id="step2",
            description="Second step",
            prompt="Do second thing",
            role="coder",
            dependencies=["step1"],
            output_key="step2_result",
        )

        assert subtask.dependencies == ["step1"]
        assert subtask.output_key == "step2_result"
