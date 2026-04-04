#!/usr/bin/env python3
"""Multi-turn conversation test with multiple tool calls.

Test scenario: Create a simple Python calculator project
- Turn 1: Create project structure
- Turn 2: Implement calculator module  
- Turn 3: Create test file
- Turn 4: Verify files exist
"""

import asyncio
import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from pilotcode.state.app_state import get_default_app_state
from pilotcode.state.store import Store, set_global_store
from pilotcode.tools.registry import get_all_tools
from pilotcode.query_engine import QueryEngine, QueryEngineConfig
from pilotcode.tools.base import ToolUseContext
from pilotcode.permissions import get_tool_executor
from pilotcode.permissions.permission_manager import (
    ToolPermission, PermissionLevel, get_permission_manager
)
from pilotcode.types.message import AssistantMessage, ToolUseMessage


class MultiTurnTester:
    """Test multi-turn conversation with tool chains."""
    
    def __init__(self, auto_allow: bool = True):
        # Create temp directory for testing
        self.test_dir = tempfile.mkdtemp(prefix="pilotcode_test_")
        print(f"Test directory: {self.test_dir}")
        
        self.store = Store(get_default_app_state())
        set_global_store(self.store)
        
        tools = get_all_tools()
        self.query_engine = QueryEngine(QueryEngineConfig(
            cwd=self.test_dir,
            tools=tools,
            get_app_state=self.store.get_state,
            set_app_state=lambda f: self.store.set_state(f)
        ))
        
        self.tool_executor = get_tool_executor()
        
        if auto_allow:
            pm = get_permission_manager()
            for tool in tools:
                pm._permissions[tool.name] = ToolPermission(
                    tool_name=tool.name,
                    level=PermissionLevel.ALWAYS_ALLOW
                )
        
        self.turn_count = 0
        self.total_tool_calls = 0
    
    def cleanup(self):
        """Clean up test directory."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
            print(f"Cleaned up: {self.test_dir}")
    
    async def run_turn(self, prompt: str, max_iterations: int = 3) -> dict:
        """Run a single conversation turn."""
        self.turn_count += 1
        print(f"\n{'='*60}")
        print(f"TURN {self.turn_count}")
        print(f"Prompt: {prompt[:60]}...")
        print(f"{'='*60}")
        
        iteration = 0
        current_prompt = prompt
        all_responses = []
        tools_used = []
        
        while iteration < max_iterations:
            iteration += 1
            pending_tools = []
            full_content = ""
            
            try:
                async for result in self.query_engine.submit_message(current_prompt):
                    msg = result.message
                    
                    if isinstance(msg, AssistantMessage) and msg.content:
                        if result.is_complete:
                            full_content = msg.content
                            all_responses.append(full_content)
                        else:
                            full_content += msg.content
                    
                    if isinstance(msg, ToolUseMessage):
                        pending_tools.append(msg)
                        tools_used.append(msg.name)
            
            except Exception as e:
                print(f"  Error in submit_message: {e}")
                return {"success": False, "error": str(e)}
            
            if not pending_tools:
                # Print AI response if no tools
                if full_content:
                    print(f"  AI: {full_content[:100]}...")
                break
            
            # Execute tools
            print(f"  Iteration {iteration}: Executing {len(pending_tools)} tool(s)")
            for tool_msg in pending_tools:
                self.total_tool_calls += 1
                print(f"    Tool: {tool_msg.name}")
                
                ctx = ToolUseContext(
                    get_app_state=self.store.get_state,
                    set_app_state=lambda f: self.store.set_state(f)
                )
                
                try:
                    result = await self.tool_executor.execute_tool_by_name(
                        tool_msg.name,
                        tool_msg.input,
                        ctx
                    )
                    status = "✓" if result.success else "✗"
                    output = result.message or str(result.result)
                    print(f"    {status} {output[:60]}...")
                except Exception as e:
                    print(f"    ✗ Error: {e}")
            
            # Continue for next iteration if tools were executed
            current_prompt = "继续执行剩余的任务"
        
        return {
            "success": True,
            "tools_used": list(set(tools_used)),  # Unique tools
            "responses": all_responses,
            "iterations": iteration
        }
    
    async def test_multi_turn_project(self) -> bool:
        """Test multi-turn project creation."""
        print("\n" + "="*70)
        print("MULTI-TURN PROJECT CREATION TEST")
        print("="*70)
        print("Scenario: Create a Python calculator project with tests")
        
        try:
            # Turn 1: Create directory structure
            result1 = await self.run_turn(
                f"Create directory structure: create 'src' and 'tests' directories in {self.test_dir}"
            )
            if not result1["success"]:
                return False
            
            # Turn 2: Create calculator module
            result2 = await self.run_turn(
                "Create src/calculator.py with a Calculator class that has add, subtract methods"
            )
            if not result2["success"]:
                return False
            
            # Turn 3: Create test file
            result3 = await self.run_turn(
                "Create tests/test_calculator.py with unit tests for the Calculator class"
            )
            if not result3["success"]:
                return False
            
            # Turn 4: List all files
            result4 = await self.run_turn(
                f"List all files in {self.test_dir} to verify the project structure"
            )
            if not result4["success"]:
                return False
            
            # Verify files actually exist
            print("\n" + "="*60)
            print("VERIFYING FILES")
            print("="*60)
            
            expected_files = [
                "src/calculator.py",
                "tests/test_calculator.py"
            ]
            
            all_exist = True
            for f in expected_files:
                path = os.path.join(self.test_dir, f)
                exists = os.path.exists(path)
                status = "✅" if exists else "❌"
                size = os.path.getsize(path) if exists else 0
                print(f"  {status} {f} ({size} bytes)")
                all_exist = all_exist and exists
            
            # Print summary
            print("\n" + "="*60)
            print("TEST SUMMARY")
            print("="*60)
            print(f"  Total turns: {self.turn_count}")
            print(f"  Total tool calls: {self.total_tool_calls}")
            print(f"  All files created: {all_exist}")
            
            # Show content of created files
            if all_exist:
                print("\n  Created files content:")
                for f in expected_files:
                    path = os.path.join(self.test_dir, f)
                    with open(path) as file:
                        lines = file.readlines()[:5]  # First 5 lines
                        print(f"\n  {f}:")
                        for line in lines:
                            print(f"    {line.rstrip()}")
            
            return all_exist
            
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_simple_file_chain(self) -> bool:
        """Test simple file write then read chain."""
        print("\n" + "="*70)
        print("SIMPLE FILE CHAIN TEST")
        print("="*70)
        print("Scenario: Write file then read it back")
        
        try:
            # Create file with absolute path
            file_path = os.path.join(self.test_dir, "chain_test.txt")
            
            result1 = await self.run_turn(
                f"Create a file at {file_path} with content 'Multi-turn test successful'"
            )
            if not result1["success"]:
                return False
            
            # Check file exists
            if not os.path.exists(file_path):
                print(f"\n❌ File not created: {file_path}")
                return False
            
            with open(file_path) as f:
                content = f.read()
            
            if "Multi-turn test successful" in content:
                print(f"\n✅ File chain test passed")
                print(f"   Content: {content}")
                return True
            else:
                print(f"\n⚠️ Content mismatch: {content}")
                return False
                
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            return False
    
    async def run_all(self) -> int:
        """Run all multi-turn tests."""
        print("\n" + "="*70)
        print("MULTI-TURN CONVERSATION TEST SUITE")
        print("="*70)
        
        results = []
        
        # Test 1: Simple file chain
        results.append(("Simple File Chain", await self.test_simple_file_chain()))
        
        # Reset counters for next test
        self.turn_count = 0
        self.total_tool_calls = 0
        
        # Test 2: Multi-turn project creation
        results.append(("Project Creation", await self.test_multi_turn_project()))
        
        # Cleanup
        self.cleanup()
        
        # Summary
        print("\n" + "="*70)
        print("FINAL SUMMARY")
        print("="*70)
        
        passed = sum(1 for _, r in results if r)
        total = len(results)
        
        for name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"  {status}: {name}")
        
        print(f"\nTotal: {passed}/{total} passed")
        
        if passed == total:
            print("\n🎉 All multi-turn tests passed!")
            return 0
        else:
            print(f"\n⚠️ {total - passed} test(s) failed")
            return 1


async def main():
    """Main entry point."""
    import argparse
    parser = argparse.ArgumentParser(description='Multi-turn Conversation Tests')
    parser.add_argument('--no-auto-allow', action='store_true',
                       help='Disable auto-allow mode')
    args = parser.parse_args()
    
    tester = MultiTurnTester(auto_allow=not args.no_auto_allow)
    exit_code = await tester.run_all()
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
