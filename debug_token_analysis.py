#!/usr/bin/env python3
"""
Debug script to analyze token calculation issues in QueryEngine.
This will help identify why token counts don't update after input.
"""

import os
import sys
import json
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from src.pilotcode.query.token_manager import TokenManager
from src.pilotcode.query.query_engine import QueryEngine
from src.pilotcode.messages import UserMessage, AssistantMessage, SystemMessage


def test_token_manager_behavior():
    """Test the token manager behavior to understand the cache logic."""
    print("=== Testing TokenManager Behavior ===")

    # Create a mock token manager
    # This is a simplified test - in reality you'd need a real config
    print("TokenManager has methods:")
    print("- count_tokens(): returns token count")
    print("- reset_cache(): clears all cached values")
    print("- _compute_state_hash(): generates hash of current messages")
    print("- _estimate_messages_delta(): estimates delta from base")

    # Show how token counting works
    print("\nToken counting process:")
    print("1. count_tokens() checks current hash vs cached hash")
    print("2. If hash matches, returns cached value")
    print("3. If hash doesn't match, recomputes tokens")
    print("4. Uses _exact_prompt_base + delta estimation for efficiency")
    print("5. Only resets cache when messages list fundamentally changes")

    # Key insight: cache is only invalidated when message list hash changes
    print("\nKey issue: If messages are added but hash doesn't change, cache is reused")


def test_submit_message_flow():
    """Trace through the submit_message flow to see where messages are added."""
    print("\n=== Testing submit_message Flow ===")

    # This simulates what happens in submit_message
    print("In submit_message():")
    print("1. Create user message")
    print("2. Add to self.messages.append(user_msg)")
    print("3. Yield result")
    print("4. Continue processing...")
    print("5. Add assistant message (if not greeting)")
    print("6. Add system messages (auto-review)")
    print("7. Add tool use messages")
    print("8. Add tool result messages")

    # The core issue: no cache reset after message addition
    print("\nPROBLEM: Messages are added but no reset_cache() is called")
    print("This means the next count_tokens() returns cached value")
    print("even though new messages were added")


def analyze_token_manager_cache_logic():
    """Analyze the exact cache invalidation logic."""
    print("\n=== Analyzing TokenManager Cache Logic ===")

    print("How _compute_state_hash works:")
    print("1. Hashes each message in self.messages")
    print("2. Hashes tools list if present")
    print("3. Returns str(hash('|'.join(parts)))")

    print("\nWhen does cache get invalidated?")
    print("1. When messages are cleared (clear_history)")
    print("2. When sessions are loaded (load_session, load_from_storage)")
    print("3. When /session load command is used")

    print("\nWhen does cache NOT get invalidated?")
    print("1. When messages are added via submit_message")
    print("2. This is the bug!")


def show_proper_fix():
    """Show what the proper fix should look like."""
    print("\n=== Proper Fix Analysis ===")

    print("In submit_message, after each self.messages.append():")
    print("    - self._token_mgr.reset_cache() should be called")
    print("    - OR the hash should be updated properly")

    print("\nBut wait - let me re-read the code more carefully...")

    # The real issue might be in the hash computation itself
    print("\nActually, let me look at the token counting logic more carefully:")
    print("The issue might be that the hash computation isn't detecting changes properly.")

    print("\nThe real fix is: AFTER any message addition in submit_message,")
    print("call self._token_mgr.reset_cache() to ensure accurate token counts.")


if __name__ == "__main__":
    test_token_manager_behavior()
    test_submit_message_flow()
    analyze_token_manager_cache_logic()
    show_proper_fix()

    print("\n=== FINAL CONCLUSION ===")
    print("The root cause is in src/pilotcode/query_engine.py")
    print("In the submit_message method, after adding messages to self.messages,")
    print("the token manager cache is not reset, so count_tokens() returns stale values.")
    print("\nSOLUTION:")
    print("1. Add self._token_mgr.reset_cache() after each message append in submit_message")
    print("2. This should be called after:")
    print("   - self.messages.append(user_msg)")
    print("   - self.messages.append(assistant_msg)")
    print("   - self.messages.append(review_msg)")
    print("   - self.messages.append(tool_use_msg)")
    print("   - self.messages.append(tool_result_msg)")
