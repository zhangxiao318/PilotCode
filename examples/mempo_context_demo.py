"""Demo of MemPO-style context management in PilotCode.

This example demonstrates the four key improvements:
1. Memory value estimation
2. Task-aware compression
3. Compression feedback learning
4. Hierarchical memory architecture
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pilotcode.services.adaptive_context_manager import (
    AdaptiveContextManager,
    AdaptiveContextConfig,
    get_adaptive_context_manager,
    reset_adaptive_context_manager,
)
from pilotcode.services.memory_value import get_memory_value_estimator
from pilotcode.services.task_aware_compression import (
    TaskAwareCompressor,
    TaskContext,
    CompressionMode,
)
from pilotcode.services.compression_feedback import (
    get_compression_feedback_loop,
    TaskOutcome,
)
from pilotcode.services.hierarchical_memory import get_hierarchical_memory


def demo_memory_value_estimation():
    """Demo 1: Memory Value Estimation"""
    print("\n" + "="*60)
    print("Demo 1: Memory Value Estimation")
    print("="*60)
    
    estimator = get_memory_value_estimator()
    
    # Simulate messages with different value
    messages = [
        ("system", "You are a helpful coding assistant"),
        ("user", "Help me fix this bug"),
        ("assistant", "Looking at the error in src/auth.py..."),
        ("tool", "File content: def login(): ..."),
        ("user", "Thanks"),
        ("assistant", "You're welcome!"),
    ]
    
    task_context = "Fix authentication bug in login system"
    current_files = ["src/auth.py", "src/models.py"]
    
    print(f"\nTask: {task_context}")
    print(f"Files: {current_files}\n")
    
    from pilotcode.services.context_manager import ContextMessage
    
    for role, content in messages:
        msg = ContextMessage(role=role, content=content)
        score = estimator.estimate_value(msg, task_context, current_files)
        
        print(f"[{role:12}] Score: {score.total_score:.2f} | "
              f"Info: {score.info_density:.2f} | "
              f"Relevance: {score.task_relevance:.2f} | "
              f"Utility: {score.historical_utility:.2f}")
        print(f"             Content: {content[:50]}...")
    
    print("\n💡 Key insight: Technical messages about auth.py get higher scores!")


def demo_task_aware_compression():
    """Demo 2: Task-Aware Compression"""
    print("\n" + "="*60)
    print("Demo 2: Task-Aware Compression")
    print("="*60)
    
    compressor = TaskAwareCompressor()
    
    # Simulate a conversation
    from pilotcode.services.context_manager import ContextMessage
    
    messages = []
    conversation = [
        ("user", "I need to implement user authentication"),
        ("assistant", "I'll help you create an authentication system. What technology would you like to use?"),
        ("user", "Use JWT tokens with refresh token rotation"),
        ("assistant", "Good choice. Let's create the JWT auth module..."),
        ("tool", "File created: src/auth/jwt_handler.py"),
        ("assistant", "Now let's implement the token refresh mechanism..."),
        ("user", "Also add password hashing with bcrypt"),
        ("assistant", "I'll add bcrypt password hashing to the auth module..."),
        ("tool", "Modified: src/auth/jwt_handler.py"),
        ("assistant", "The implementation is complete. Here's a summary..."),
    ]
    
    for role, content in conversation:
        # Simulate longer messages
        content = content * 20  # Make them longer
        messages.append(ContextMessage(role=role, content=content))
    
    task_context = TaskContext(
        description="Implement JWT authentication with bcrypt",
        current_files=["src/auth/jwt_handler.py"],
        task_type="feature",
        complexity="medium",
    )
    
    print(f"\nOriginal: {len(messages)} messages")
    
    # Compress with low target to force compression
    result = compressor.compress_with_task_context(
        messages, task_context, target_tokens=2000
    )
    
    print(f"Compressed: {result.retained_messages} messages retained")
    print(f"Value retention: {result.value_retention_rate:.1%}")
    print(f"Token reduction: {result.to_dict()['token_reduction']:.1%}")
    print(f"Compression mode: {result.compression_mode.value}")
    
    print("\n📊 Decisions made:")
    for decision in result.decisions[:5]:
        status = "✓" if decision.retained else "✗"
        print(f"  {status} {decision.compression_action:12} (score: {decision.value_score:.2f}) - {decision.reason}")
    
    print("\n💡 Key insight: High-value messages about JWT/auth are retained!")


def demo_compression_feedback():
    """Demo 3: Compression Feedback Loop"""
    print("\n" + "="*60)
    print("Demo 3: Compression Feedback Loop")
    print("="*60)
    
    feedback = get_compression_feedback_loop()
    
    # Simulate multiple compression events with outcomes
    scenarios = [
        ("Fix login bug", CompressionMode.LIGHT, TaskOutcome.SUCCESS),
        ("Add new feature", CompressionMode.MODERATE, TaskOutcome.SUCCESS),
        ("Refactor codebase", CompressionMode.AGGRESSIVE, TaskOutcome.FAILURE),
        ("Debug error", CompressionMode.LIGHT, TaskOutcome.SUCCESS),
        ("Implement API", CompressionMode.MODERATE, TaskOutcome.SUCCESS),
    ]
    
    from pilotcode.services.task_aware_compression import TaskAwareCompressionResult
    
    for desc, mode, outcome in scenarios:
        result = TaskAwareCompressionResult(
            original_messages=20,
            retained_messages=12 if mode == CompressionMode.MODERATE else 16,
            summarized_messages=4,
            removed_messages=4 if mode == CompressionMode.MODERATE else 0,
            original_tokens=8000,
            compressed_tokens=4800 if mode == CompressionMode.MODERATE else 6400,
            value_retention_rate=0.75 if outcome == TaskOutcome.SUCCESS else 0.45,
            compression_mode=mode,
        )
        
        event_id = feedback.record_compression(result, desc)
        feedback.record_outcome(event_id, outcome)
        
        status = "✓" if outcome == TaskOutcome.SUCCESS else "✗"
        print(f"{status} {desc:20} | Mode: {mode.value:12} | Outcome: {outcome.value}")
    
    # Get recommendations
    print("\n📈 Learned patterns:")
    report = feedback.get_compression_report()
    
    print(f"Mode effectiveness:")
    for mode, score in report["mode_effectiveness"].items():
        print(f"  - {mode}: {score:.2f}")
    
    recommended = feedback.get_recommended_mode("Implement new feature")
    print(f"\n🎯 Recommended mode for 'Implement new feature': {recommended.value}")


def demo_hierarchical_memory():
    """Demo 4: Hierarchical Memory Architecture"""
    print("\n" + "="*60)
    print("Demo 4: Hierarchical Memory Architecture")
    print("="*60)
    
    memory = get_hierarchical_memory()
    
    # Simulate previous episodes
    print("\n💾 Storing past episodes...")
    
    from pilotcode.services.context_manager import ContextMessage
    
    # Episode 1: Authentication
    memory.start_episode()
    messages1 = [
        ContextMessage(role="user", content="Implement JWT authentication"),
        ContextMessage(role="assistant", content="Created auth module with JWT"),
        ContextMessage(role="tool", content="Created src/auth.py"),
    ]
    for m in messages1:
        memory.add_to_working(m)
    snapshot1 = memory.end_episode()
    print(f"  Stored: {snapshot1.primary_request[:40]}...")
    
    # Episode 2: Database
    memory.start_episode()
    messages2 = [
        ContextMessage(role="user", content="Setup PostgreSQL database"),
        ContextMessage(role="assistant", content="Configured database models"),
        ContextMessage(role="tool", content="Created models.py"),
    ]
    for m in messages2:
        memory.add_to_working(m)
    snapshot2 = memory.end_episode()
    print(f"  Stored: {snapshot2.primary_request[:40]}...")
    
    # Episode 3: Testing
    memory.start_episode()
    messages3 = [
        ContextMessage(role="user", content="Write unit tests"),
        ContextMessage(role="assistant", content="Created test suite"),
        ContextMessage(role="tool", content="Created test_auth.py"),
    ]
    for m in messages3:
        memory.add_to_working(m)
    snapshot3 = memory.end_episode()
    print(f"  Stored: {snapshot3.primary_request[:40]}...")
    
    # Query for relevant episodes
    print("\n🔍 Querying for 'authentication JWT':")
    context = memory.retrieve_context("authentication JWT", include_episodes=2)
    
    for episode in context["episodic_memories"]:
        print(f"  Found: {episode.primary_request[:50]}...")
        print(f"    - Files: {episode.files_modified}")
        print(f"    - Concepts: {episode.key_technical_concepts[:3]}")
    
    # Format for prompt
    print("\n📝 Formatted for prompt:")
    formatted = memory.format_context_for_prompt(context, max_tokens=500)
    print(formatted)
    
    print("\n💡 Key insight: Relevant past episodes are retrieved automatically!")


def demo_adaptive_context_manager():
    """Demo 5: Full Adaptive Context Manager"""
    print("\n" + "="*60)
    print("Demo 5: Full Adaptive Context Manager")
    print("="*60)
    
    reset_adaptive_context_manager()
    
    config = AdaptiveContextConfig(
        simple_task_tokens=2000,
        medium_task_tokens=4000,
        complex_task_tokens=6000,
    )
    
    manager = get_adaptive_context_manager(config)
    
    # Set task context
    print("\n🎯 Setting task context...")
    manager.set_task_context(
        description="Implement user authentication with JWT and bcrypt",
        task_type="feature",
        current_files=["src/auth.py"],
        task_id="auth_task_1",
    )
    
    print(f"Task complexity: {manager.current_task_complexity.value}")
    print(f"Token budget: {manager.budget.max_tokens}")
    
    # Add messages
    print("\n💬 Adding messages to context...")
    messages = [
        ("user", "I need to implement login"),
        ("assistant", "I'll create an authentication system"),
        ("user", "Use JWT tokens"),
        ("assistant", "Setting up JWT..."),
        ("tool", "Created src/auth.py with JWT implementation"),
        ("user", "Add password hashing too"),
        ("assistant", "Adding bcrypt password hashing..."),
        ("tool", "Updated src/auth.py with password hashing"),
    ]
    
    for role, content in messages:
        # Make messages longer to trigger compression
        content = content * 50
        manager.add_message(role, content)
        print(f"  Added [{role}]: {content[:40]}...")
    
    # Show message values
    print("\n📊 Message value scores:")
    scored_messages = manager.get_messages_with_scores()
    for msg in scored_messages[-5:]:
        if "value_score" in msg:
            vs = msg["value_score"]
            print(f"  [{msg['role']:12}] Total: {vs['total']:.2f} | "
                  f"Density: {vs['info_density']:.2f} | "
                  f"Relevance: {vs['task_relevance']:.2f}")
    
    # Force compression
    print("\n🗜️  Forcing compression...")
    result = manager.force_compact(CompressionMode.MODERATE)
    
    print(f"Original: {result.original_messages} messages, {result.original_tokens} tokens")
    print(f"Compressed: {result.retained_messages} messages, {result.compressed_tokens} tokens")
    print(f"Value retention: {result.value_retention_rate:.1%}")
    
    # Record outcome
    print("\n✅ Recording task outcome (success)...")
    manager.record_task_outcome(success=True)
    
    # Show stats
    stats = manager.get_adaptive_stats()
    print("\n📈 Adaptive stats:")
    print(f"  Total compressions: {stats['adaptive_stats']['total_compressions']}")
    print(f"  Tokens saved: {stats['adaptive_stats']['total_tokens_saved']}")
    print(f"  Avg value retention: {stats['adaptive_stats']['avg_value_retention']:.1%}")
    print(f"  Task success rate: {stats['adaptive_stats']['task_success_rate']:.1%}")
    
    print("\n💡 Key insight: The system learns from outcomes to improve compression!")


def main():
    """Run all demos."""
    print("\n" + "="*60)
    print("🧠 MemPO-Style Context Management Demo for PilotCode")
    print("="*60)
    print("\nThis demo showcases intelligent context management inspired by MemPO:")
    print("https://arxiv.org/abs/2603.00680")
    
    try:
        demo_memory_value_estimation()
    except Exception as e:
        print(f"Demo 1 error: {e}")
    
    try:
        demo_task_aware_compression()
    except Exception as e:
        print(f"Demo 2 error: {e}")
    
    try:
        demo_compression_feedback()
    except Exception as e:
        print(f"Demo 3 error: {e}")
    
    try:
        demo_hierarchical_memory()
    except Exception as e:
        print(f"Demo 4 error: {e}")
    
    try:
        demo_adaptive_context_manager()
    except Exception as e:
        print(f"Demo 5 error: {e}")
    
    print("\n" + "="*60)
    print("✅ Demo complete!")
    print("="*60)


if __name__ == "__main__":
    main()
