"""Demo: Complex Task Decomposition and Scheduling Execution

This demo shows how complex tasks are automatically decomposed and executed
with different scheduling strategies.
"""

import asyncio
from datetime import datetime
from pilotcode.orchestration import TaskDecomposer, DecompositionStrategy


def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def demo_complex_task_decomposition():
    """Demo 1: Complex task decomposition."""
    print_section("DEMO 1: Complex Task Decomposition")
    
    decomposer = TaskDecomposer()
    
    tasks = [
        {
            "name": "User Authentication System",
            "task": """Implement a complete user authentication system including:
            - User registration with email verification
            - Login with JWT token support
            - Password reset functionality
            - Role-based access control (RBAC)
            - Session management
            - Comprehensive test coverage"""
        },
        {
            "name": "Microservices Migration",
            "task": """Migrate our monolithic application to microservices:
            - Extract user service with its own database
            - Extract order service with event sourcing
            - Set up inter-service communication
            - Implement API gateway
            - Add service discovery
            - Ensure data consistency across services"""
        },
        {
            "name": "Security Audit",
            "task": """Perform comprehensive security audit:
            - Check for SQL injection vulnerabilities in all endpoints
            - Verify authentication and authorization mechanisms
            - Review data encryption at rest and in transit
            - Analyze third-party dependencies for known vulnerabilities
            - Test for XSS and CSRF vulnerabilities
            - Generate detailed security report with recommendations"""
        },
        {
            "name": "Database Performance Optimization",
            "task": """Optimize database performance:
            - Analyze slow queries and add appropriate indexes
            - Implement query result caching
            - Set up database connection pooling
            - Partition large tables
            - Optimize transaction boundaries
            - Add performance monitoring and alerting"""
        }
    ]
    
    for i, item in enumerate(tasks, 1):
        print(f"\n📋 Task {i}: {item['name']}")
        print(f"   Description: {item['task'][:80]}...")
        
        result = decomposer.auto_decompose(item['task'])
        
        print(f"\n   🔍 Analysis:")
        print(f"      Strategy: {result.strategy.name}")
        print(f"      Confidence: {result.confidence:.0%}")
        print(f"      Will Decompose: {result.strategy != DecompositionStrategy.NONE}")
        
        if result.subtasks:
            print(f"\n   📝 Decomposition ({len(result.subtasks)} subtasks):")
            for j, subtask in enumerate(result.subtasks, 1):
                deps = f" [→ {', '.join(subtask.dependencies)}]" if subtask.dependencies else ""
                print(f"      {j}. [{subtask.role:10}] {subtask.description}{deps}")
        else:
            print(f"\n   ⚡ Task will be executed as a single unit (no decomposition)")


def demo_scheduling_strategies():
    """Demo 2: Different scheduling strategies."""
    print_section("DEMO 2: Scheduling Strategies")
    
    decomposer = TaskDecomposer()
    
    # Sequential strategy example
    print("\n📊 Strategy: SEQUENTIAL (Task dependencies)")
    print("-" * 70)
    
    sequential_task = """Refactor the payment module:
    - Analyze current implementation
    - Design new architecture
    - Implement changes incrementally
    - Update tests
    - Deploy to staging"""
    
    result = decomposer.analyze(sequential_task)
    print(f"Task: {sequential_task[:60]}...")
    print(f"Strategy: {result.strategy.name}")
    print(f"\nExecution Flow:")
    for i, subtask in enumerate(result.subtasks, 1):
        deps = f" (after: {', '.join(subtask.dependencies)})" if subtask.dependencies else " (first)"
        print(f"  Step {i}: {subtask.description}{deps}")
    print("\n  ➡️  Tasks execute one after another, results pass forward")
    
    # Parallel strategy example
    print("\n\n📊 Strategy: PARALLEL (Independent tasks)")
    print("-" * 70)
    
    parallel_task = """Review the pull request:
    - Check code structure
    - Verify code quality
    - Review security implications"""
    
    result = decomposer.analyze(parallel_task)
    print(f"Task: {parallel_task[:60]}...")
    print(f"Strategy: {result.strategy.name}")
    print(f"\nExecution Flow:")
    for i, subtask in enumerate(result.subtasks, 1):
        print(f"  Task {i}: {subtask.description} [runs in parallel]")
    print("\n  ➡️  All tasks execute simultaneously, results collected at end")
    
    # Hierarchical strategy example
    print("\n\n📊 Strategy: HIERARCHICAL (Supervisor-Worker)")
    print("-" * 70)
    
    hierarchical_task = """Implement e-commerce platform:
    - Supervisor: Coordinate architecture design
    - Worker 1: Implement product catalog
    - Worker 2: Implement shopping cart
    - Worker 3: Implement checkout flow"""
    
    print(f"Task: {hierarchical_task[:60]}...")
    print(f"\nExecution Flow:")
    print("  1. Supervisor creates task breakdown")
    print("  2. Workers execute in parallel:")
    print("     - Worker 1: Product catalog → Result A")
    print("     - Worker 2: Shopping cart → Result B")
    print("     - Worker 3: Checkout flow → Result C")
    print("  3. Supervisor synthesizes: A + B + C → Final Result")
    print("\n  ➡️  Supervisor coordinates, workers execute, results synthesized")


def demo_execution_simulation():
    """Demo 3: Simulate execution of decomposed tasks."""
    print_section("DEMO 3: Execution Simulation")
    
    print("\n🎬 Simulating: 'Implement API with tests' (Sequential)")
    print("-" * 70)
    
    decomposer = TaskDecomposer()
    task = "Implement REST API with CRUD operations and tests"
    result = decomposer.auto_decompose(task)
    
    print(f"\nOriginal Task: {task}")
    print(f"Strategy: {result.strategy.name}")
    
    print("\n⏱️  Execution Timeline:")
    start_time = datetime.now()
    
    for i, subtask in enumerate(result.subtasks, 1):
        task_start = datetime.now()
        
        # Simulate work
        import time
        time.sleep(0.1)
        
        task_end = datetime.now()
        duration = (task_end - task_start).total_seconds()
        
        print(f"\n  [{task_start.strftime('%H:%M:%S.%f')[:-3]}] "
              f"→ Step {i}: {subtask.description}")
        print(f"  [{task_end.strftime('%H:%M:%S.%f')[:-3]}] "
              f"✓ Completed in {duration:.2f}s [{subtask.role}]")
        
        if i < len(result.subtasks):
            next_task = result.subtasks[i]
            if subtask.id in next_task.dependencies:
                print(f"                    ↓ (dependency for: {next_task.description})")
    
    total_duration = (datetime.now() - start_time).total_seconds()
    print(f"\n⏹️  Total execution time: {total_duration:.2f}s")
    print(f"   Subtasks completed: {len(result.subtasks)}")


def demo_comparison():
    """Demo 4: Compare with/without decomposition."""
    print_section("DEMO 4: With vs Without Decomposition")
    
    decomposer = TaskDecomposer()
    
    task = "Implement user authentication with tests"
    
    print(f"\nTask: {task}")
    
    # Without decomposition
    print("\n❌ Without Decomposition:")
    print("  • Single agent handles everything")
    print("  • May miss important aspects")
    print("  • Harder to track progress")
    print("  • Difficult to parallelize work")
    print("  • Less specialized expertise")
    
    # With decomposition
    result = decomposer.auto_decompose(task)
    
    print("\n✅ With Decomposition:")
    print(f"  • Split into {len(result.subtasks)} specialized subtasks")
    print("  • Each subtask has clear focus and role")
    print("  • Progress tracked per subtask")
    print(f"  • Strategy: {result.strategy.name} execution")
    print("  • Specialized agents per task type")
    print(f"  • Estimated total effort better understood")
    
    print("\n📊 Subtask Breakdown:")
    for i, subtask in enumerate(result.subtasks, 1):
        print(f"  {i}. {subtask.role:10} → {subtask.description}")


def demo_metrics():
    """Demo 5: Execution metrics."""
    print_section("DEMO 5: Execution Metrics")
    
    print("\n📈 Metrics Tracked During Execution:")
    print("-" * 70)
    
    metrics = {
        "Task Complexity Score": "Calculated based on keywords and structure",
        "Decomposition Confidence": "0.0 - 1.0 (higher = more confident)",
        "Estimated Duration": "Sum of all subtask estimates",
        "Actual Duration": "Measured execution time",
        "Success Rate": "Completed subtasks / Total subtasks",
        "Parallel Efficiency": "Time saved vs sequential execution",
        "Agent Utilization": "Time spent vs idle time per agent",
        "Tool Usage Count": "Number of tool calls per subtask"
    }
    
    for metric, description in metrics.items():
        print(f"  • {metric:25}: {description}")
    
    print("\n📊 Example Report:")
    print("""
    Workflow: Implement API Endpoint
    =================================
    Strategy: SEQUENTIAL
    Subtasks: 3 (Plan → Implement → Test)
    
    Execution Results:
    ├── Step 1 (planner):  ✓ Completed in 2.3s
    ├── Step 2 (coder):    ✓ Completed in 5.7s
    └── Step 3 (tester):   ✓ Completed in 3.1s
    
    Summary:
    ├── Total Duration: 11.1s
    ├── Success Rate: 100% (3/3)
    ├── Tools Used: 12 total
    └── Status: ✅ SUCCESS
    """)


async def main():
    """Run all demos."""
    print("\n" + "🚀" * 35)
    print("  Complex Task Decomposition & Scheduling Demo")
    print("🚀" * 35)
    
    demo_complex_task_decomposition()
    demo_scheduling_strategies()
    demo_execution_simulation()
    demo_comparison()
    demo_metrics()
    
    print_section("Demo Complete")
    print("\n💡 Key Takeaways:")
    print("  1. Complex tasks are automatically decomposed based on patterns")
    print("  2. Different strategies (Sequential/Parallel/Hierarchical) for different tasks")
    print("  3. Each subtask gets specialized agent with appropriate role")
    print("  4. Dependencies ensure correct execution order")
    print("  5. Full visibility into progress and results")
    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
