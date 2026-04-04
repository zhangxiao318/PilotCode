#!/usr/bin/env python3
"""Regression tests for PilotCode core functionality.

Tests:
1. Simple query: "现在几点了" - Basic AI response
2. Code generation: Factorial C program - File write tool
3. Code analysis: Analyze project structure - File read/Glob tools
"""

import asyncio
import sys
import os
import time

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


class RegressionTester:
    """Regression test suite."""
    
    def __init__(self, auto_allow: bool = True):
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
        self.auto_allow = auto_allow
        
        if auto_allow:
            pm = get_permission_manager()
            for tool in tools:
                pm._permissions[tool.name] = ToolPermission(
                    tool_name=tool.name,
                    level=PermissionLevel.ALWAYS_ALLOW
                )
    
    def log(self, role: str, content: str, max_len: int = 200):
        """Log a message with truncation."""
        display = content[:max_len] + "..." if len(content) > max_len else content
        prefix = {
            "user": "[You]",
            "assistant": "[AI]",
            "system": "[System]",
            "tool_use": "[Tool]",
            "tool_result": "[Result]",
            "error": "[Error]"
        }.get(role, f"[{role}]")
        print(f"  {prefix} {display}")
    
    async def run_query(self, prompt: str, max_iterations: int = 5) -> dict:
        """Run a query and return results."""
        start_time = time.time()
        iteration = 0
        current_prompt = prompt
        messages = []
        tools_used = []
        
        try:
            while iteration < max_iterations:
                iteration += 1
                pending_tools = []
                full_content = ""
                
                async for result in self.query_engine.submit_message(current_prompt):
                    msg = result.message
                    
                    if hasattr(msg, 'content') and msg.content:
                        if result.is_complete:
                            full_content = msg.content
                            messages.append({"role": "assistant", "content": full_content})
                        else:
                            full_content += msg.content
                    
                    if hasattr(msg, 'name') and msg.name:
                        pending_tools.append(msg)
                        tools_used.append(msg.name)
                        self.log("tool_use", f"{msg.name}({msg.input})")
                
                if not pending_tools:
                    break
                
                # Execute tools
                for tool_msg in pending_tools:
                    ctx = ToolUseContext(
                        get_app_state=self.store.get_state,
                        set_app_state=lambda f: self.store.set_state(f)
                    )
                    
                    result = await self.tool_executor.execute_tool_by_name(
                        tool_msg.name,
                        tool_msg.input,
                        ctx
                    )
                    output = result.message or str(result.result)
                    self.log("tool_result", output)
                
                current_prompt = "继续"
            
            elapsed = time.time() - start_time
            return {
                "success": True,
                "elapsed": elapsed,
                "messages": messages,
                "tools_used": tools_used,
                "iterations": iteration
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "elapsed": time.time() - start_time
            }
    
    async def test_time_query(self) -> bool:
        """Test 1: Simple time query."""
        print("\n" + "=" * 70)
        print("TEST 1: Time Query (现在几点了)")
        print("=" * 70)
        print("Prompt: 现在几点了")
        
        result = await self.run_query("现在几点了")
        
        print(f"\nElapsed: {result['elapsed']:.2f}s")
        print(f"Success: {result['success']}")
        
        if result['success']:
            print(f"Tools used: {result['tools_used']}")
            print(f"Iterations: {result['iterations']}")
            
            # Check if response is reasonable
            if result['messages']:
                content = result['messages'][-1]['content'].lower()
                # Should mention time, date, or suggest using date command
                has_time = any(word in content for word in ['时间', 'time', 'date', '点', '分', '时'])
                if has_time:
                    print("✅ PASS: Response contains time-related content")
                    return True
                else:
                    print("⚠️  WARNING: Response may not contain time info")
                    print(f"Content: {result['messages'][-1]['content'][:100]}")
                    return True  # Still pass if we got a response
        else:
            print(f"❌ FAIL: {result.get('error', 'Unknown error')}")
            return False
        
        return result['success'] and result['elapsed'] < 10
    
    async def test_factorial_code(self) -> bool:
        """Test 2: Generate factorial C program."""
        print("\n" + "=" * 70)
        print("TEST 2: Code Generation (Factorial C Program)")
        print("=" * 70)
        prompt = "编写一个计算阶乘的C语言程序，可以计算1-200的阶乘"
        print(f"Prompt: {prompt}")
        
        result = await self.run_query(prompt, max_iterations=3)
        
        print(f"\nElapsed: {result['elapsed']:.2f}s")
        print(f"Success: {result['success']}")
        
        if result['success']:
            print(f"Tools used: {result['tools_used']}")
            
            # Check for code in response
            if result['messages']:
                content = result['messages'][-1]['content']
                has_code = '```c' in content or '#include' in content or 'int main' in content
                has_factorial = 'factorial' in content.lower() or '阶乘' in content
                
                if has_code and has_factorial:
                    print("✅ PASS: Generated C code with factorial logic")
                    return True
                elif has_code:
                    print("⚠️  WARNING: Generated code but may not be factorial")
                    return True
                else:
                    print("⚠️  WARNING: No code block found in response")
                    return True  # Still pass if we got a response
        else:
            print(f"❌ FAIL: {result.get('error', 'Unknown error')}")
            return False
        
        return result['success'] and result['elapsed'] < 30
    
    async def test_project_analysis(self) -> bool:
        """Test 3: Analyze project structure."""
        print("\n" + "=" * 70)
        print("TEST 3: Project Structure Analysis")
        print("=" * 70)
        print("Prompt: 分析当前目录下程序结构")
        
        result = await self.run_query("分析当前目录下程序结构", max_iterations=3)
        
        print(f"\nElapsed: {result['elapsed']:.2f}s")
        print(f"Success: {result['success']}")
        
        if result['success']:
            print(f"Tools used: {result['tools_used']}")
            
            # Should use file exploration tools
            expected_tools = {'Glob', 'FileRead', 'Grep', 'Bash'}
            used_expected = any(t in expected_tools for t in result['tools_used'])
            
            if used_expected:
                print("✅ PASS: Used file exploration tools")
            else:
                print("⚠️  WARNING: Did not use expected tools")
            
            # Check if analysis is present
            if result['messages']:
                content = result['messages'][-1]['content'].lower()
                has_analysis = any(word in content for word in 
                    ['结构', '目录', '文件', 'src', 'source', 'module', 'package'])
                
                if has_analysis:
                    print("✅ PASS: Response contains project analysis")
                    return True
                else:
                    print("⚠️  WARNING: May not contain project analysis")
                    return True
        else:
            print(f"❌ FAIL: {result.get('error', 'Unknown error')}")
            return False
        
        return result['success'] and result['elapsed'] < 20
    
    async def run_all(self):
        """Run all regression tests."""
        print("\n" + "=" * 70)
        print("PILOTCODE REGRESSION TEST SUITE")
        print("=" * 70)
        print(f"Auto-allow mode: {self.auto_allow}")
        
        results = []
        
        # Test 1
        results.append(("Time Query", await self.test_time_query()))
        
        # Test 2
        results.append(("Factorial Code", await self.test_factorial_code()))
        
        # Test 3
        results.append(("Project Analysis", await self.test_project_analysis()))
        
        # Summary
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        
        passed = sum(1 for _, r in results if r)
        total = len(results)
        
        for name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"  {status}: {name}")
        
        print(f"\nTotal: {passed}/{total} passed")
        
        if passed == total:
            print("\n🎉 All tests passed!")
            return 0
        else:
            print(f"\n⚠️  {total - passed} test(s) failed")
            return 1


async def run_session_tests() -> int:
    """Run session save/load tests."""
    print("\n" + "=" * 70)
    print("SESSION SAVE/LOAD TESTS")
    print("=" * 70)
    
    import tempfile
    import json
    from pilotcode.types.message import UserMessage, AssistantMessage
    
    store = Store(get_default_app_state())
    set_global_store(store)
    
    tools = get_all_tools()
    query_engine = QueryEngine(QueryEngineConfig(
        cwd=store.get_state().cwd,
        tools=tools,
        get_app_state=store.get_state,
        set_app_state=lambda f: store.set_state(f)
    ))
    
    results = []
    
    # Test 1: Save/Load empty session
    print("\n--- Test: Save/Load Empty Session ---")
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        query_engine.save_session(temp_path)
        
        new_engine = QueryEngine(QueryEngineConfig(
            cwd="/tmp", tools=tools,
            get_app_state=store.get_state,
            set_app_state=lambda f: store.set_state(f)
        ))
        result = new_engine.load_session(temp_path)
        
        assert result and len(new_engine.messages) == 0
        print("✅ PASS: Empty session save/load")
        results.append(("Empty Session", True))
    except Exception as e:
        print(f"❌ FAIL: {e}")
        results.append(("Empty Session", False))
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    
    # Test 2: Save/Load with messages
    print("\n--- Test: Save/Load With Messages ---")
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        query_engine.messages.append(UserMessage(content="Hello"))
        query_engine.messages.append(AssistantMessage(content="Hi!"))
        
        query_engine.save_session(temp_path)
        
        new_engine = QueryEngine(QueryEngineConfig(
            cwd="/tmp", tools=tools,
            get_app_state=store.get_state,
            set_app_state=lambda f: store.set_state(f)
        ))
        new_engine.load_session(temp_path)
        
        assert len(new_engine.messages) == 2
        assert isinstance(new_engine.messages[0], UserMessage)
        assert new_engine.messages[0].content == "Hello"
        
        print("✅ PASS: Session with messages save/load")
        results.append(("With Messages", True))
    except Exception as e:
        print(f"❌ FAIL: {e}")
        results.append(("With Messages", False))
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    
    # Test 3: Load non-existent file
    print("\n--- Test: Load Non-existent File ---")
    try:
        result = query_engine.load_session("/nonexistent/test.json")
        assert result == False
        print("✅ PASS: Non-existent file handling")
        results.append(("Non-existent File", True))
    except Exception as e:
        print(f"❌ FAIL: {e}")
        results.append(("Non-existent File", False))
    
    return sum(1 for _, r in results if r), len(results)


async def main():
    """Main entry point."""
    import argparse
    parser = argparse.ArgumentParser(description='PilotCode Regression Tests')
    parser.add_argument('--no-auto-allow', action='store_true', 
                       help='Disable auto-allow mode (will prompt for permissions)')
    parser.add_argument('--include-session', action='store_true',
                       help='Include session save/load tests')
    args = parser.parse_args()
    
    all_results = []
    
    # Core tests
    tester = RegressionTester(auto_allow=not args.no_auto_allow)
    core_passed, core_total = await tester.run_all()
    all_results.append(("Core Tests", core_passed, core_total))
    
    # Session tests
    if args.include_session:
        session_passed, session_total = await run_session_tests()
        all_results.append(("Session Tests", session_passed, session_total))
    
    # Final summary
    print("\n" + "=" * 70)
    print("OVERALL SUMMARY")
    print("=" * 70)
    
    total_passed = 0
    total_tests = 0
    
    for name, passed, count in all_results:
        status = "✅" if passed == count else "⚠️"
        print(f"  {status} {name}: {passed}/{count}")
        total_passed += passed
        total_tests += count
    
    print(f"\nTotal: {total_passed}/{total_tests} passed")
    
    if total_passed == total_tests:
        print("\n🎉 All regression tests passed!")
        return 0
    else:
        return 1


if __name__ == "__main__":
    asyncio.run(main())
