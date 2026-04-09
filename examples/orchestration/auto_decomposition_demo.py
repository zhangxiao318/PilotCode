"""Demo: Automatic task decomposition in action.

Shows how SmartCoordinator automatically decides when to decompose tasks.
"""

import asyncio
from pilotcode.orchestration import TaskDecomposer, DecompositionStrategy
from pilotcode.orchestration.smart_coordinator import SmartCoordinator
from pilotcode.orchestration.auto_config import configure_auto_decomposition


class MockAgent:
    """Mock agent for demo."""
    def __init__(self, role, prompt):
        self.role = role
        self.prompt = prompt


def mock_agent_factory(role, prompt):
    """Mock agent factory."""
    return MockAgent(role, prompt)


def demo_heuristic_analysis():
    """Demonstrate heuristic analysis for auto-decomposition."""
    print("=" * 70)
    print("DEMO: Heuristic Analysis for Auto-Decomposition")
    print("=" * 70)
    print()
    
    decomposer = TaskDecomposer()
    
    test_cases = [
        # (task, expected to decompose)
        ("Read README.md", False),
        ("Show me the file structure", False),
        ("Find all TODO comments", False),
        ("Implement user authentication with login, signup, and password reset", True),
        ("Refactor the database layer to use async/await", True),
        ("Fix the memory leak in data processing", True),
        ("Review this pull request for code quality", True),
        ("Check each file independently for errors", True),
    ]
    
    print("Task Analysis Results:")
    print("-" * 70)
    
    for task, expected_decompose in test_cases:
        result = decomposer.analyze(task)
        
        will_decompose = result.strategy != DecompositionStrategy.NONE
        status = "✓" if will_decompose == expected_decompose else "✗"
        
        print(f"{status} Task: {task[:50]}...")
        print(f"   Strategy: {result.strategy.name}")
        print(f"   Confidence: {result.confidence:.2f}")
        print(f"   Will Decompose: {will_decompose} (Expected: {expected_decompose})")
        print()


def demo_auto_patterns():
    """Demonstrate auto-decomposition patterns."""
    print("=" * 70)
    print("DEMO: Auto-Decomposition Patterns")
    print("=" * 70)
    print()
    
    decomposer = TaskDecomposer()
    
    patterns = [
        ("Implementation", "Implement a REST API with CRUD operations and tests"),
        ("Refactoring", "Refactor the monolithic service into microservices"),
        ("Bug Fix", "Fix the race condition in the concurrent data handler"),
        ("Code Review", "Review the authentication module changes"),
    ]
    
    for pattern_name, task in patterns:
        print(f"\n{pattern_name} Pattern:")
        print(f"Task: {task}")
        print()
        
        result = decomposer.auto_decompose(task)
        
        print(f"  Strategy: {result.strategy.name}")
        print(f"  Subtasks ({len(result.subtasks)}):")
        
        for i, subtask in enumerate(result.subtasks, 1):
            deps = f" (depends: {subtask.dependencies})" if subtask.dependencies else ""
            print(f"    {i}. [{subtask.role}] {subtask.description}{deps}")
        print()


def demo_smart_coordinator():
    """Demonstrate SmartCoordinator behavior."""
    print("=" * 70)
    print("DEMO: SmartCoordinator Auto-Decomposition")
    print("=" * 70)
    print()
    
    coordinator = SmartCoordinator(mock_agent_factory)
    
    # Configure for demo
    configure_auto_decomposition(enabled=True, require_confirmation=False)
    
    test_tasks = [
        "Read the configuration file",
        "Implement a user management system with authentication and authorization",
        "List all Python files",
        "Refactor the database connection pooling",
    ]
    
    print("SmartCoordinator will automatically decide when to decompose:\n")
    
    for task in test_tasks:
        # Analyze only (don't actually execute)
        analysis = coordinator.decomposer.analyze(task)
        will_decompose = analysis.strategy != DecompositionStrategy.NONE
        
        print(f"Task: {task}")
        print(f"  → Will decompose: {will_decompose}")
        print(f"  → Strategy: {analysis.strategy.name}")
        print(f"  → Confidence: {analysis.confidence:.2f}")
        
        if will_decompose:
            print(f"  → Subtasks: {len(analysis.subtasks)}")
        print()


def demo_configuration():
    """Demonstrate configuration options."""
    print("=" * 70)
    print("DEMO: Configuration Options")
    print("=" * 70)
    print()
    
    from pilotcode.orchestration.auto_config import get_auto_config
    
    config = get_auto_config()
    
    print("Current Configuration:")
    print(f"  enabled: {config.enabled}")
    print(f"  min_confidence: {config.min_confidence}")
    print(f"  simple_task_threshold: {config.simple_task_threshold}")
    print(f"  require_confirmation: {config.require_confirmation}")
    print()
    
    print("Configuration Examples:")
    print()
    print("# Enable auto-decomposition with high confidence threshold")
    print("configure_auto_decomposition(")
    print("    enabled=True,")
    print("    min_confidence=0.8,")
    print("    require_confirmation=False")
    print(")")
    print()
    print("# Disable auto-decomposition globally")
    print("configure_auto_decomposition(enabled=False)")
    print()
    print("# Or use convenience functions:")
    print("enable_auto_decomposition()")
    print("disable_auto_decomposition()")
    print()


async def main():
    """Run all demos."""
    demo_heuristic_analysis()
    print("\n")
    
    demo_auto_patterns()
    print("\n")
    
    demo_smart_coordinator()
    print("\n")
    
    demo_configuration()
    
    print("=" * 70)
    print("Demo completed!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
