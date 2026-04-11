"""Real-world usage example of task orchestration.

Shows how to use the orchestration system in actual development workflows.
"""

import asyncio
from datetime import datetime
from typing import Any, Optional


# Mock implementations for demonstration
class MockModelClient:
    """Mock model client for demo."""

    async def chat_completion(self, messages, stream=False):
        """Simulate model response."""
        await asyncio.sleep(0.01)
        return {"content": f"[Response to: {messages[-1]['content'][:30]}...]", "tool_calls": None}


class MockAgent:
    """Mock agent that simulates execution."""

    def __init__(self, role: str, prompt: str):
        self.role = role
        self.prompt = prompt
        self.tools_used = []
        self.started_at = None
        self.completed_at = None

    async def execute(self) -> str:
        """Execute the agent's task."""
        self.started_at = datetime.now()

        # Simulate work based on role
        await asyncio.sleep(0.05)

        # Simulate some tool usage
        if self.role == "coder":
            self.tools_used = ["Read", "Write", "Bash"]
        elif self.role == "debugger":
            self.tools_used = ["Read", "Grep", "Bash"]
        elif self.role == "tester":
            self.tools_used = ["Read", "Bash"]
        else:
            self.tools_used = ["Read"]

        self.completed_at = datetime.now()

        return f"[{self.role.upper()}] Completed: {self.prompt[:40]}..."


def agent_factory(role: str, prompt: str) -> MockAgent:
    """Factory for creating mock agents."""
    return MockAgent(role, prompt)


async def example_1_feature_implementation():
    """Example 1: Feature Implementation Workflow."""
    print("\n" + "=" * 70)
    print("  Example 1: Feature Implementation Workflow")
    print("=" * 70)

    from pilotcode.orchestration import AgentCoordinator

    coordinator = AgentCoordinator(agent_factory)

    # Complex feature request
    task = """Implement a user profile management feature with:
    - Profile editing (name, email, avatar)
    - Password change functionality
    - Activity history view
    - Privacy settings
    - Unit tests for all components"""

    print(f"\n📝 Task: {task[:80]}...")
    print("\n🔄 Starting automatic decomposition and execution...\n")

    # Execute with progress tracking
    progress_log = []

    def on_progress(event, data):
        progress_log.append((datetime.now(), event, data))
        if event == "task_starting":
            print(f"  ▶️  Starting: {data.get('task_id', 'unknown')}")
        elif event == "task_completed":
            print(f"  ✅ Completed: {data.get('task_id', 'unknown')}")

    coordinator.on_progress(on_progress)

    # Execute
    result = await coordinator.execute(task=task, auto_decompose=True)

    # Print results
    print(f"\n📊 Execution Summary:")
    print(f"  Status: {result.status}")
    print(f"  Duration: {result.duration_seconds:.2f}s")
    print(f"  Decomposed: {result.metadata.get('decomposed', False)}")

    if result.metadata.get("subtask_count"):
        print(f"  Subtasks: {result.metadata['subtask_count']}")
        print(f"  Successful: {result.metadata.get('success_count', 0)}")

    print(f"\n📄 Summary:\n{result.summary[:300]}...")


async def example_2_bug_fix_workflow():
    """Example 2: Bug Fix Workflow."""
    print("\n" + "=" * 70)
    print("  Example 2: Bug Fix Workflow")
    print("=" * 70)

    from pilotcode.orchestration import TaskDecomposer

    decomposer = TaskDecomposer()

    bug_report = """Critical bug: Users can't login after password reset.
    Steps to reproduce:
    1. Request password reset
    2. Click reset link
    3. Set new password
    4. Try to login → Fails with 'Invalid credentials'
    
    Need to fix urgently with regression test."""

    print(f"\n🐛 Bug Report: {bug_report[:100]}...")

    # Analyze and decompose
    result = decomposer.auto_decompose(bug_report)

    print(f"\n🔍 Decomposition:")
    print(f"  Strategy: {result.strategy.name}")
    print(f"  Confidence: {result.confidence:.0%}")

    print(f"\n📝 Fix Plan:")
    for i, subtask in enumerate(result.subtasks, 1):
        print(f"  {i}. [{subtask.role.upper()}] {subtask.description}")
        print(f"     └─ {subtask.prompt[:60]}...")

    # Simulate execution
    print(f"\n⏱️  Execution:")
    for subtask in result.subtasks:
        agent = agent_factory(subtask.role, subtask.prompt)
        output = await agent.execute()
        print(f"  ✓ {output}")


async def example_3_code_review_automation():
    """Example 3: Automated Code Review."""
    print("\n" + "=" * 70)
    print("  Example 3: Automated Code Review")
    print("=" * 70)

    from pilotcode.orchestration.smart_coordinator import SmartCoordinator

    coordinator = SmartCoordinator(agent_factory)

    pr_description = """Review pull request #123:
    - New payment gateway integration
    - Updated transaction handling
    - Modified error logging
    - Database schema changes"""

    print(f"\n📋 PR: {pr_description}")

    # Smart coordinator decides if decomposition is needed
    result, preview = await coordinator.run_with_preview(pr_description)

    print(f"\n🔍 Analysis Preview:")
    print(f"  Will Decompose: {preview['will_decompose']}")
    print(f"  Strategy: {preview['strategy']}")

    if preview["will_decompose"]:
        print(f"\n📝 Review Plan ({len(preview['subtasks'])} reviewers):")
        for i, st in enumerate(preview["subtasks"], 1):
            print(f"  {i}. {st['role']}: {st['description']}")

        print(f"\n⏱️  Estimated Duration: {preview['estimated_duration']}s")


async def example_4_refactoring_project():
    """Example 4: Large-Scale Refactoring."""
    print("\n" + "=" * 70)
    print("  Example 4: Large-Scale Refactoring Project")
    print("=" * 70)

    from pilotcode.orchestration import TaskDecomposer, DecompositionStrategy

    decomposer = TaskDecomposer()

    refactoring_task = """Migrate legacy codebase from Python 2 to Python 3:
    - Update print statements
    - Fix unicode/string handling
    - Update exception syntax
    - Modernize imports
    - Update dependencies
    - Run full test suite
    - Deploy to staging for verification"""

    print(f"\n🔄 Task: {refactoring_task[:80]}...")

    result = decomposer.auto_decompose(refactoring_task)

    print(f"\n📊 Migration Strategy: {result.strategy.name}")
    print(f"  Confidence: {result.confidence:.0%}")

    print(f"\n📝 Migration Steps ({len(result.subtasks)} phases):")

    for i, subtask in enumerate(result.subtasks, 1):
        status = "⏸️ " if subtask.dependencies else "▶️ "
        deps = f" (after: {', '.join(subtask.dependencies)})" if subtask.dependencies else ""
        print(f"\n  Phase {i}: {status}{subtask.description}{deps}")
        print(f"    Role: {subtask.role}")
        print(f"    Complexity: {'⭐' * subtask.estimated_complexity}")
        print(f"    Est. Duration: {subtask.estimated_duration_seconds}s")


async def example_5_performance_optimization():
    """Example 5: Performance Optimization."""
    print("\n" + "=" * 70)
    print("  Example 5: Performance Optimization")
    print("=" * 70)

    from pilotcode.orchestration import AgentCoordinator

    coordinator = AgentCoordinator(agent_factory)

    optimization_task = """Optimize database query performance:
    - Identify slow queries from logs
    - Add missing indexes
    - Optimize N+1 queries
    - Implement caching layer
    - Benchmark before/after performance"""

    print(f"\n⚡ Task: {optimization_task[:80]}...")

    # Execute with forced parallel strategy
    result = await coordinator.execute(
        task=optimization_task, strategy="parallel", auto_decompose=True  # Force parallel execution
    )

    print(f"\n📊 Results:")
    print(f"  Strategy Used: {result.metadata.get('strategy', 'unknown')}")
    print(f"  Duration: {result.duration_seconds:.2f}s")

    if result.metadata.get("decomposed"):
        print(f"  Subtasks: {result.metadata['subtask_count']}")
        print(f"  Parallel Efficiency: ~{result.metadata['subtask_count'] * 0.7:.1f}x faster")


async def example_6_configuring_automation():
    """Example 6: Configuring Auto-Decomposition."""
    print("\n" + "=" * 70)
    print("  Example 6: Configuring Auto-Decomposition")
    print("=" * 70)

    from pilotcode.orchestration.auto_config import (
        configure_auto_decomposition,
        get_auto_config,
        enable_auto_decomposition,
        disable_auto_decomposition,
    )

    print("\n⚙️  Current Configuration:")
    config = get_auto_config()
    print(f"  Enabled: {config.enabled}")
    print(f"  Min Confidence: {config.min_confidence}")
    print(f"  Require Confirmation: {config.require_confirmation}")

    print("\n📝 Configuration Options:")

    # Example 1: Conservative mode
    print("\n  1. Conservative Mode (only decompose high-confidence tasks):")
    print("     configure_auto_decomposition(")
    print("         enabled=True,")
    print("         min_confidence=0.9,")
    print("         require_confirmation=True")
    print("     )")

    # Example 2: Aggressive mode
    print("\n  2. Aggressive Mode (decompose most tasks):")
    print("     configure_auto_decomposition(")
    print("         enabled=True,")
    print("         min_confidence=0.5,")
    print("         require_confirmation=False")
    print("     )")

    # Example 3: Disable
    print("\n  3. Disable Auto-Decomposition:")
    print("     disable_auto_decomposition()")
    print("     # or: configure_auto_decomposition(enabled=False)")

    # Example 4: Re-enable
    print("\n  4. Re-enable Auto-Decomposition:")
    print("     enable_auto_decomposition()")


async def main():
    """Run all real-world examples."""
    print("\n" + "🚀" * 35)
    print("  Real-World Task Orchestration Examples")
    print("🚀" * 35)

    await example_1_feature_implementation()
    await example_2_bug_fix_workflow()
    await example_3_code_review_automation()
    await example_4_refactoring_project()
    await example_5_performance_optimization()
    await example_6_configuring_automation()

    print("\n" + "=" * 70)
    print("  Examples Complete!")
    print("=" * 70)
    print("\n💡 For actual usage:")
    print("  from pilotcode.orchestration import AgentCoordinator")
    print("  coordinator = AgentCoordinator(agent_factory)")
    print("  result = await coordinator.execute(task, auto_decompose=True)")
    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
