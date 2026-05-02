"""Real-world usage example of task orchestration.

Shows how to use the orchestration system in actual development workflows.
Uses MissionAdapter (the production entry point) instead of the removed
AgentCoordinator stub.
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

    from pilotcode.orchestration import MissionAdapter, TaskDecomposer

    # In production, use MissionAdapter for full P-EVR orchestration:
    #   adapter = MissionAdapter()
    #   result = await adapter.run(user_request=task)

    decomposer = TaskDecomposer()

    # Complex feature request
    task = """Implement a user profile management feature with:
    - Profile editing (name, email, avatar)
    - Password change functionality
    - Activity history view
    - Privacy settings
    - Unit tests for all components"""

    print(f"\n📝 Task: {task[:80]}...")

    # Use TaskDecomposer to preview the decomposition plan
    result = decomposer.auto_decompose(task)

    print(f"\n📊 Decomposition Preview:")
    print(f"  Strategy: {result.strategy.name}")
    print(f"  Confidence: {result.confidence:.0%}")
    print(f"  Subtask count: {len(result.subtasks)}")
    for i, st in enumerate(result.subtasks, 1):
        print(f"  {i}. [{st.role}] {st.description}")

    print(f"\n💡 To execute: use MissionAdapter().run(user_request=task)")


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

    from pilotcode.orchestration import MissionAdapter, TaskDecomposer, DecompositionStrategy

    adapter = MissionAdapter()
    decomposer = TaskDecomposer()

    pr_description = """Review pull request #123:
    - New payment gateway integration
    - Updated transaction handling
    - Modified error logging
    - Database schema changes"""

    print(f"\n📋 PR: {pr_description}")

    # MissionAdapter auto-detects if full P-EVR planning is needed
    will_plan = MissionAdapter._should_explore_and_plan(pr_description)
    analysis = decomposer.analyze(pr_description)

    print(f"\n🔍 Analysis Preview:")
    print(f"  Will Plan (P-EVR): {will_plan}")
    print(f"  Strategy: {analysis.strategy.name}")

    if analysis.strategy != DecompositionStrategy.NONE:
        result = decomposer.auto_decompose(pr_description)
        print(f"\n📝 Review Plan ({len(result.subtasks)} reviewers):")
        for i, st in enumerate(result.subtasks, 1):
            print(f"  {i}. {st.role}: {st.description}")

        print(f"\n⏱️  Estimated Duration: {result.subtasks[0].estimated_duration_seconds}s")


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

    from pilotcode.orchestration import TaskDecomposer

    decomposer = TaskDecomposer()

    optimization_task = """Optimize database query performance:
    - Identify slow queries from logs
    - Add missing indexes
    - Optimize N+1 queries
    - Implement caching layer
    - Benchmark before/after performance"""

    print(f"\n⚡ Task: {optimization_task[:80]}...")

    # Decompose with parallel strategy
    result = decomposer.auto_decompose(optimization_task)

    print(f"\n📊 Results:")
    print(f"  Strategy: {result.strategy.name}")
    print(f"  Subtasks: {len(result.subtasks)}")
    
    for i, st in enumerate(result.subtasks, 1):
        deps = f" (depends on: {', '.join(st.dependencies)})" if st.dependencies else ""
        print(f"  {i}. [{st.role}] {st.description}{deps}")

    print(f"\n💡 To execute: use MissionAdapter().run(user_request=task)")


async def example_6_configuring_automation():
    """Example 6: Configuring Auto-Decomposition."""
    print("\n" + "=" * 70)
    print("  Example 6: Configuring Auto-Decomposition")
    print("=" * 70)

    from pilotcode.orchestration.auto_config import AutoDecompositionConfig

    print("\n⚙️  Configuration:")
    config = AutoDecompositionConfig()
    print(f"  Enabled: {config.enabled}")
    print(f"  Simple Task Threshold: {config.simple_task_threshold}")
    print(f"  Require Confirmation: {config.require_confirmation}")

    print("\n📝 Configuration Presets:")

    # Example 1: Conservative mode
    print("\n  1. Conservative Mode:")
    conservative = AutoDecompositionConfig(
        enabled=True,
        simple_task_threshold=5,
        require_confirmation=True,
    )
    print(f"     enabled={conservative.enabled}, threshold={conservative.simple_task_threshold}")

    # Example 2: Aggressive mode
    print("\n  2. Aggressive Mode:")
    aggressive = AutoDecompositionConfig(
        enabled=True,
        simple_task_threshold=1,
        require_confirmation=False,
    )
    print(f"     enabled={aggressive.enabled}, threshold={aggressive.simple_task_threshold}")

    # Example 3: Disabled
    print("\n  3. Disabled:")
    disabled = AutoDecompositionConfig(enabled=False)
    print(f"     enabled={disabled.enabled}")

    print("\n💡 Pass config instances to consumers via constructor injection.")


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
    print("  from pilotcode.orchestration import MissionAdapter")
    print("  adapter = MissionAdapter()")
    print("  result = await adapter.run(\"Your task description\")")
    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
