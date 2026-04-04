#!/usr/bin/env python3
"""Core functionality test for PilotCode - Non-TUI testing."""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from pilotcode.state.app_state import get_default_app_state
from pilotcode.state.store import Store, set_global_store
from pilotcode.tools.registry import get_all_tools
from pilotcode.query_engine import QueryEngine, QueryEngineConfig
from pilotcode.tools.base import ToolUseContext
from pilotcode.permissions import get_tool_executor


class CoreTester:
    """Test core functionality without TUI."""
    
    def __init__(self):
        self.store = Store(get_default_app_state())
        set_global_store(self.store)
        
        tools = get_all_tools()
        self.query_engine = QueryEngine(QueryEngineConfig(
            cwd=self.store.get_state().cwd,
            tools=tools,
            get_app_state=self.store.get_state,
            set_app_state=lambda f: self.store.set_state(f)
        ))
        
        self.tool_executor = get_tool_executor()
        self.message_history = []
        
    def log(self, role: str, content: str):
        """Log a message."""
        self.message_history.append({"role": role, "content": content})
        prefix = {
            "user": "[You]",
            "assistant": "[AI]",
            "system": "[System]",
            "tool_use": "[Tool]",
            "tool_result": "[Result]",
            "error": "[Error]"
        }.get(role, f"[{role}]")
        print(f"{prefix} {content}")
        
    async def test_query(self, prompt: str, max_iterations: int = 3):
        """Test a single query through the engine."""
        print(f"\n{'='*60}")
        print(f"Testing query: '{prompt}'")
        print(f"{'='*60}\n")
        
        self.log("user", prompt)
        
        iteration = 0
        current_prompt = prompt
        
        while iteration < max_iterations:
            iteration += 1
            print(f"\n--- Iteration {iteration} ---")
            
            pending_tools = []
            full_content = ""
            chunk_count = 0
            
            try:
                print("Calling submit_message...")
                async for result in self.query_engine.submit_message(current_prompt):
                    chunk_count += 1
                    msg = result.message
                    
                    if hasattr(msg, 'content') and msg.content:
                        if result.is_complete:
                            full_content = msg.content
                            self.log("assistant", full_content)
                        else:
                            # Streaming - accumulate
                            full_content += msg.content
                            
                    # Check for tool use
                    if hasattr(msg, 'name') and msg.name:  # ToolUseMessage
                        pending_tools.append(msg)
                        self.log("tool_use", f"{msg.name}({msg.input})")
                        
                print(f"Received {chunk_count} chunks")
                
            except Exception as e:
                self.log("error", f"Query failed: {e}")
                import traceback
                traceback.print_exc()
                return False
            
            if not pending_tools:
                print("No pending tools, query complete.")
                break
                
            # Execute tools
            for tool_msg in pending_tools:
                print(f"\nExecuting tool: {tool_msg.name}")
                
                ctx = ToolUseContext(
                    get_app_state=self.store.get_state,
                    set_app_state=lambda f: self.store.set_state(f)
                )
                
                try:
                    # Use execute_tool_by_name which handles tool lookup
                    result = await self.tool_executor.execute_tool_by_name(
                        tool_msg.name, 
                        tool_msg.input, 
                        ctx
                    )
                    success = result.success
                    content = result.message or str(result.result)
                    
                    # Truncate long output
                    display = content[:500] + "..." if len(content) > 500 else content
                    self.log("tool_result", f"{'✓' if success else '✗'} {display}")
                    
                except Exception as e:
                    self.log("error", f"Tool execution failed: {e}")
                    import traceback
                    traceback.print_exc()
                    
            # Continue for next iteration
            current_prompt = "Continue based on the tool results."
            
        print(f"\n{'='*60}")
        print("Query test completed")
        print(f"{'='*60}")
        return True


async def main():
    """Run core tests."""
    print("PilotCode Core Functionality Test")
    print("=" * 60)
    
    tester = CoreTester()
    
    # Test 1: Simple question
    print("\n[TEST 1] Simple question")
    await tester.test_query("What time is it now?", max_iterations=2)
    
    # Test 2: File operation
    print("\n[TEST 2] File listing")
    await tester.test_query("List all Python files in the current directory", max_iterations=3)
    
    # Test 3: Code request
    print("\n[TEST 3] Code generation request")
    await tester.test_query("Write a hello world Python script", max_iterations=2)
    
    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
