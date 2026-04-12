# ClaudeCode-Style Task Orchestration

This module provides ClaudeCode-style task decomposition and multi-agent orchestration.

## Features

### 1. Task Decomposition (`decomposer.py`)

- **Heuristic Analysis**: Rule-based task complexity detection
- **LLM-Based Analysis**: Intelligent decomposition for complex tasks
- **Multiple Strategies**: Sequential, Parallel, Hierarchical, Iterative
- **Auto-Decomposition**: Predefined patterns for common tasks

```python
from pilotcode.orchestration import TaskDecomposer

decomposer = TaskDecomposer()
result = decomposer.auto_decompose("Implement a feature with tests")

print(f"Strategy: {result.strategy.name}")
for subtask in result.subtasks:
    print(f"  - [{subtask.role}] {subtask.description}")
```

### 2. Task Execution (`executor.py`)

- **Sequential Execution**: Steps execute one after another
- **Parallel Execution**: Concurrent execution with limits
- **Hierarchical Execution**: Supervisor-worker pattern
- **Dependency-Aware**: Respects task dependencies

```python
from pilotcode.orchestration import TaskExecutor

executor = TaskExecutor(agent_factory)

# Sequential
results = await executor.execute_sequential(subtasks)

# Parallel
results = await executor.execute_parallel(subtasks, max_concurrency=5)

# Hierarchical
results = await executor.execute_hierarchical(task, workers)
```

### 3. Agent Coordinator (`coordinator.py`)

Main entry point for orchestration:

```python
from pilotcode.orchestration import AgentCoordinator

coordinator = AgentCoordinator(agent_factory)
result = await coordinator.execute(
    task="Implement user authentication",
    auto_decompose=True
)

print(result.summary)
```

## Usage Examples

### Basic Task Decomposition

```python
# Simple task - no decomposition
result = decomposer.analyze("Read README.md")
# Strategy: NONE

# Complex task - automatic decomposition
result = decomposer.analyze("Implement and test a new API endpoint")
# Strategy: SEQUENTIAL
# Subtasks: Plan → Implement → Test
```

### Multi-Agent Workflow

```python
# Parallel code review
result = await coordinator.execute(
    task="Review the pull request",
    strategy="parallel"
)

# Sequential implementation
result = await coordinator.execute(
    task="Implement a feature with tests",
    strategy="sequential"
)

# Hierarchical refactoring
result = await coordinator.execute(
    task="Refactor the database layer",
    strategy="hierarchical"
)
```

## Decomposition Patterns

### 1. Implementation Pattern

```
Task: "Implement X with tests"
→ Plan → Implement → Test
```

### 2. Refactoring Pattern

```
Task: "Refactor X"
→ Explore → Plan → Refactor → Verify
```

### 3. Bug Fix Pattern

```
Task: "Fix bug in X"
→ Diagnose → Fix → Test
```

### 4. Code Review Pattern

```
Task: "Review X"
→ [Structure Review] + [Quality Review] + [Security Review] (parallel)
```

## Agent Roles

- `coder`: Write and edit code
- `debugger`: Find and fix bugs
- `tester`: Write tests
- `reviewer`: Review code
- `planner`: Create plans
- `explorer`: Understand codebases
- `explainer`: Explain concepts

## Testing

Run tests:

```bash
pytest tests/unit/orchestration/ -v
```

Run examples:

```bash
python examples/orchestration/basic_decomposition.py
```
