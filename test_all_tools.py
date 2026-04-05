#!/usr/bin/env python3
"""Comprehensive test for all PilotCode tools.

This test file covers:
- Read-only tools
- Write tools (using temp directory)
- Network tools (WebSearch, WebFetch)
- Interactive tools (AskUser with simulated input)
- REPL tool (Python, Bash)
"""

import asyncio
import sys
import os
import io
import tempfile
import json
from datetime import datetime
from unittest.mock import patch

sys.path.insert(0, 'src')

from pilotcode.tools.registry import get_all_tools, get_tool_by_name
from pilotcode.tools.base import ToolUseContext
from pilotcode.state.app_state import get_default_app_state
from pilotcode.state.store import Store, set_global_store


class ToolTestResult:
    def __init__(self, name, success, output=None, error=None):
        self.name = name
        self.success = success
        self.output = output
        self.error = error


async def test_tool(tool, test_input, ctx, allow_callback):
    """Test a single tool."""
    try:
        parsed = tool.input_schema(**test_input)
        result = await tool.call(parsed, ctx, allow_callback, None, lambda x: None)
        
        if result.is_error:
            return ToolTestResult(tool.name, False, None, result.error)
        else:
            output = str(result.data)[:200] if result.data else "<success>"
            return ToolTestResult(tool.name, True, output, None)
    except Exception as e:
        return ToolTestResult(tool.name, False, None, f"{type(e).__name__}: {str(e)}")


async def test_readonly_tools(ctx, allow_callback):
    """Test read-only tools."""
    print("\n" + "-" * 70)
    print("Testing READ-ONLY Tools")
    print("-" * 70)
    
    test_cases = {
        'FileRead': {'file_path': '/home/zx/mycc/PilotCode/README.md'},
        'Glob': {'pattern': '*.py', 'path': '/home/zx/mycc/PilotCode/src/pilotcode'},
        'Grep': {'pattern': 'class', 'path': '/home/zx/mycc/PilotCode/src/pilotcode', 'output_format': 'brief'},
        'GitStatus': {},
        'GitDiff': {},
        'GitLog': {'max_count': 2},
        'GitBranch': {'action': 'list'},
        'Brief': {'content': 'This is a long text that needs to be summarized', 'max_words': 10},
        'Sleep': {'seconds': 0.05},
        'ToolSearch': {'query': 'file'},
        'Config': {'action': 'list'},
        'TodoWrite': {'todos': [{'id': '1', 'content': 'Test', 'status': 'pending', 'priority': 'medium'}]},
        'CronList': {},
        'ListWorktrees': {},
        'ExitWorktree': {},
        'TaskList': {},
        'Skill': {'action': 'list', 'skill_name': ''},
        'SyntheticOutput': {'content_type': 'text/plain', 'description': 'Test', 'content': 'Test'},
        'ReceiveMessage': {'agent_id': 'test_agent'},
    }
    
    results = []
    for name, input_data in sorted(test_cases.items()):
        tool = get_tool_by_name(name)
        if not tool:
            print(f"{name:20s} ... ✗ NOT FOUND")
            continue
            
        print(f"{name:20s} ...", end=" ")
        result = await test_tool(tool, input_data, ctx, allow_callback)
        
        if result.success:
            print(f"✓ OK")
        else:
            print(f"✗ FAIL")
            print(f"  Error: {result.error[:60]}")
        
        results.append(result)
    
    return results


async def test_write_tools(ctx, allow_callback):
    """Test write tools using temp directory."""
    print("\n" + "-" * 70)
    print("Testing WRITE Tools (in temp directory)")
    print("-" * 70)
    
    results = []
    
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"Using temp dir: {tmpdir}\n")
        
        # FileWrite
        print(f"{'FileWrite':20s} ...", end=" ")
        try:
            tool = get_tool_by_name('FileWrite')
            test_file = os.path.join(tmpdir, 'test.txt')
            result = await test_tool(tool, {'file_path': test_file, 'content': 'Hello World'}, ctx, allow_callback)
            
            if result.success and os.path.exists(test_file):
                print(f"✓ OK")
            else:
                print(f"✗ FAIL")
            results.append(result)
        except Exception as e:
            print(f"✗ ERROR: {e}")
            results.append(ToolTestResult('FileWrite', False, None, str(e)))
        
        # FileEdit
        print(f"{'FileEdit':20s} ...", end=" ")
        try:
            tool = get_tool_by_name('FileEdit')
            result = await test_tool(tool, {'file_path': test_file, 'old_string': 'Hello', 'new_string': 'Hi'}, ctx, allow_callback)
            
            if result.success:
                with open(test_file) as f:
                    content = f.read()
                if 'Hi World' in content:
                    print(f"✓ OK")
                else:
                    print(f"✗ FAIL (content not changed)")
            else:
                print(f"✗ FAIL")
            results.append(result)
        except Exception as e:
            print(f"✗ ERROR: {e}")
            results.append(ToolTestResult('FileEdit', False, None, str(e)))
        
        # EnterWorktree
        print(f"{'EnterWorktree':20s} ...", end=" ")
        try:
            tool = get_tool_by_name('EnterWorktree')
            result = await test_tool(tool, {'path': '/home/zx/mycc/PilotCode'}, ctx, allow_callback)
            print(f"✓ OK" if result.success else f"✗ FAIL")
            results.append(result)
        except Exception as e:
            print(f"✗ ERROR: {e}")
            results.append(ToolTestResult('EnterWorktree', False, None, str(e)))
        
        # Bash (safe command)
        print(f"{'Bash':20s} ...", end=" ")
        try:
            tool = get_tool_by_name('Bash')
            result = await test_tool(tool, {'command': 'echo "test"', 'description': 'Test echo'}, ctx, allow_callback)
            print(f"✓ OK" if result.success else f"✗ FAIL")
            results.append(result)
        except Exception as e:
            print(f"✗ ERROR: {e}")
            results.append(ToolTestResult('Bash', False, None, str(e)))
    
    return results


async def test_network_tools(ctx, allow_callback):
    """Test network-dependent tools."""
    print("\n" + "-" * 70)
    print("Testing NETWORK Tools")
    print("-" * 70)
    
    results = []
    
    # WebSearch
    print(f"{'WebSearch':20s} ...", end=" ")
    try:
        tool = get_tool_by_name('WebSearch')
        result = await test_tool(tool, {'query': 'Python programming', 'max_results': 2}, ctx, allow_callback)
        print(f"✓ OK" if result.success else f"✗ FAIL: {result.error[:50]}")
        results.append(result)
    except Exception as e:
        print(f"✗ ERROR: {e}")
        results.append(ToolTestResult('WebSearch', False, None, str(e)))
    
    # WebFetch
    print(f"{'WebFetch':20s} ...", end=" ")
    try:
        tool = get_tool_by_name('WebFetch')
        result = await test_tool(tool, {'url': 'https://httpbin.org/get', 'max_length': 1000}, ctx, allow_callback)
        print(f"✓ OK" if result.success else f"✗ FAIL: {result.error[:50]}")
        results.append(result)
    except Exception as e:
        print(f"✗ ERROR: {e}")
        results.append(ToolTestResult('WebFetch', False, None, str(e)))
    
    return results


async def test_repl_tools(ctx, allow_callback):
    """Test REPL tool."""
    print("\n" + "-" * 70)
    print("Testing REPL Tool")
    print("-" * 70)
    
    results = []
    tool = get_tool_by_name('REPL')
    
    # Python
    print(f"{'REPL Python':20s} ...", end=" ")
    try:
        result = await test_tool(tool, {'language': 'python', 'code': 'print(2+3)', 'timeout': 10}, ctx, allow_callback)
        if result.success and '5' in (result.output or ''):
            print(f"✓ OK")
        else:
            print(f"✗ FAIL: {result.error}")
        results.append(result)
    except Exception as e:
        print(f"✗ ERROR: {e}")
        results.append(ToolTestResult('REPL', False, None, str(e)))
    
    return results


async def test_interactive_tools(ctx, allow_callback):
    """Test interactive tools with simulated input."""
    print("\n" + "-" * 70)
    print("Testing INTERACTIVE Tools (simulated input)")
    print("-" * 70)
    
    results = []
    
    # AskUser with simulated input
    print(f"{'AskUser':20s} ...", end=" ")
    try:
        tool = get_tool_by_name('AskUser')
        parsed = tool.input_schema(question="Continue?", options=["yes", "no"])
        
        simulated_input = "yes\n"
        with patch('sys.stdin', io.StringIO(simulated_input)):
            result = await tool.call(parsed, ctx, allow_callback, None, lambda x: None)
        
        if not result.is_error and result.data.response == "yes":
            print(f"✓ OK")
            results.append(ToolTestResult('AskUser', True, None, None))
        else:
            print(f"✗ FAIL")
            results.append(ToolTestResult('AskUser', False, None, result.error if result.is_error else "Wrong response"))
    except Exception as e:
        print(f"✗ ERROR: {e}")
        results.append(ToolTestResult('AskUser', False, None, str(e)))
    
    return results


async def main():
    print("=" * 70)
    print("PILOTCODE COMPREHENSIVE TOOL TEST")
    print("=" * 70)
    
    # Setup
    store = Store(get_default_app_state())
    set_global_store(store)
    
    ctx = ToolUseContext(
        get_app_state=store.get_state,
        set_app_state=lambda f: store.set_state(f)
    )
    
    async def allow_callback(*args, **kwargs):
        return {"behavior": "allow"}
    
    # Run all test categories
    tested_results = []
    tested_results.extend(await test_readonly_tools(ctx, allow_callback))
    tested_results.extend(await test_write_tools(ctx, allow_callback))
    tested_results.extend(await test_network_tools(ctx, allow_callback))
    tested_results.extend(await test_repl_tools(ctx, allow_callback))
    tested_results.extend(await test_interactive_tools(ctx, allow_callback))
    
    # Define tools that require special environment (not tested above)
    special_env_tools = {
        'PowerShell': 'Windows only',
        'LSP': 'Requires LSP server',
        'ListMcpResources': 'Requires MCP server configuration',
        'ReadMcpResource': 'Requires MCP server configuration',
        'MCP': 'Requires MCP server configuration',
        'WebBrowser': 'Requires Playwright browser',
        'RemoteTrigger': 'Requires network endpoint configuration',
        'Agent': 'Requires sub-agent configuration',
        'TaskCreate': 'Requires background task execution environment',
        'TaskStop': 'Requires existing task',
        'TaskUpdate': 'Requires existing task',
        'TaskOutput': 'Requires existing task with output',
        'SendMessage': 'Requires target agent',
        'EnterPlanMode': 'Plan mode tool',
        'ExitPlanMode': 'Plan mode tool',
        'UpdatePlanStep': 'Plan mode tool',
        'CronCreate': 'Cron management tool',
        'CronDelete': 'Cron management tool',
        'CronUpdate': 'Cron management tool',
        'NotebookEdit': 'Notebook editing tool',
    }
    
    # Create skipped results
    skipped_results = []
    tested_names = {r.name for r in tested_results}
    
    for tool in get_all_tools():
        if tool.name not in tested_names:
            reason = special_env_tools.get(tool.name, 'Not tested in this run')
            skipped_results.append(ToolTestResult(
                tool.name, 
                None,  # None means skipped
                None, 
                reason
            ))
    
    # Combine all results
    all_results = tested_results + skipped_results
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for r in tested_results if r.success)
    failed = sum(1 for r in tested_results if not r.success)
    skipped = len(skipped_results)
    total_tested = len(tested_results)
    total_all = len(all_results)
    
    print(f"Tested: {total_tested}")
    print(f"  Passed: {passed} ({passed/total_tested*100:.1f}%)")
    print(f"  Failed: {failed} ({failed/total_tested*100:.1f}%)")
    print(f"Skipped (needs special env): {skipped}")
    print(f"Total tools: {total_all}")
    
    if failed > 0:
        print("\nFailed tools:")
        for r in tested_results:
            if not r.success:
                print(f"  ✗ {r.name}: {r.error[:60]}")
    
    if skipped > 0:
        print("\nSkipped tools (need special environment):")
        for r in skipped_results:
            print(f"  ⊘ {r.name}: {r.error}")
    
    # Save report
    report = {
        'timestamp': datetime.now().isoformat(),
        'summary': {
            'total': total_all,
            'tested': total_tested,
            'passed': passed,
            'failed': failed,
            'skipped': skipped
        },
        'tested': [
            {'tool': r.name, 'status': 'passed' if r.success else 'failed', 
             'error': r.error, 'output': r.output}
            for r in tested_results
        ],
        'skipped': [
            {'tool': r.name, 'status': 'skipped', 'reason': r.error}
            for r in skipped_results
        ]
    }
    
    report_file = '/tmp/pilotcode_all_tools_report.json'
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\nDetailed report: {report_file}")
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
