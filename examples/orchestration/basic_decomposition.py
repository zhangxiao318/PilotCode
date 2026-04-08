"""Example: Basic task decomposition and execution.

Demonstrates ClaudeCode-style task decomposition and execution.
"""

import asyncio
from pilotcode.orchestration import (
    TaskDecomposer,
    DecompositionStrategy,
    TaskExecutor,
    AgentCoordinator,
)


async def main():
    """Run decomposition examples."""
    
    # Example 1: Simple task that doesn't need decomposition
    print("=" * 60)
    print("Example 1: Simple task")
    print("=" * 60)
    
    decomposer = TaskDecomposer()
    result = decomposer.analyze("Read the README.md file")
    
    print(f"Task: Read the README.md file")
    print(f"Strategy: {result.strategy.name}")
    print(f"Confidence: {result.confidence}")
    print(f"Reasoning: {result.reasoning}")
    print()
    
    # Example 2: Complex implementation task
    print("=" * 60)
    print("Example 2: Implementation with tests")
    print("=" * 60)
    
    result = decomposer.auto_decompose(
        "Implement a user authentication system with login, signup, and password reset, including comprehensive tests"
    )
    
    print(f"Task: Implement authentication system")
    print(f"Strategy: {result.strategy.name}")
    print(f"Subtasks ({len(result.subtasks)}):")
    for i, subtask in enumerate(result.subtasks, 1):
        print(f"  {i}. [{subtask.role}] {subtask.description}")
        print(f"     Dependencies: {subtask.dependencies}")
    print()
    
    # Example 3: Refactoring task
    print("=" * 60)
    print("Example 3: Refactoring")
    print("=" * 60)
    
    result = decomposer.auto_decompose(
        "Refactor the database layer to use async/await pattern"
    )
    
    print(f"Task: Refactor database layer")
    print(f"Strategy: {result.strategy.name}")
    print(f"Subtasks ({len(result.subtasks)}):")
    for i, subtask in enumerate(result.subtasks, 1):
        print(f"  {i}. [{subtask.role}] {subtask.description}")
    print()
    
    # Example 4: Bug fix
    print("=" * 60)
    print("Example 4: Bug fix")
    print("=" * 60)
    
    result = decomposer.auto_decompose(
        "Fix the memory leak in the data processing pipeline"
    )
    
    print(f"Task: Fix memory leak")
    print(f"Strategy: {result.strategy.name}")
    print(f"Subtasks ({len(result.subtasks)}):")
    for i, subtask in enumerate(result.subtasks, 1):
        print(f"  {i}. [{subtask.role}] {subtask.description}")
    print()
    
    print("=" * 60)
    print("Examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
