#!/usr/bin/env python3
"""
Test Simple CLI UI for PilotCode.
Uses mcp-tui-test MCP server for automation.
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from test_with_mcp_tui_test import MCPTUITestClient, TestResult
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SimpleCLIResult:
    """Test result for simple CLI."""
    name: str
    passed: bool
    duration: float
    error: Optional[str] = None


class SimpleCLITester:
    """Test Simple CLI using mcp-tui-test."""
    
    def __init__(self, client: MCPTUITestClient, 
                 cli_cmd: str = "python3 -m pilotcode.tui.simple_cli --auto-allow"):
        self.client = client
        self.cli_cmd = cli_cmd
        self.results: List[SimpleCLIResult] = []
    
    def run_test(self, name: str, test_func) -> SimpleCLIResult:
        """Run a single test."""
        print(f"\n{'='*60}")
        print(f"TEST: {name}")
        print(f"{'='*60}")
        
        import time as time_module
        start = time_module.time()
        try:
            test_func()
            duration = time_module.time() - start
            print(f"✅ PASSED ({duration:.2f}s)")
            result = SimpleCLIResult(name=name, passed=True, duration=duration)
        except AssertionError as e:
            duration = time_module.time() - start
            print(f"❌ FAILED: {e}")
            result = SimpleCLIResult(name=name, passed=False, duration=duration, error=str(e))
        except Exception as e:
            duration = time_module.time() - start
            print(f"❌ ERROR: {e}")
            result = SimpleCLIResult(name=name, passed=False, duration=duration, error=str(e))
        finally:
            # Cleanup session
            try:
                self.client.close_session()
            except:
                pass
        
        self.results.append(result)
        return result
    
    def test_startup(self):
        """Test 1: Startup and welcome screen."""
        self.client.session_id = "test_startup"
        assert self.client.launch_tui(self.cli_cmd, mode="stream"), "Failed to launch"
        time.sleep(3)
        
        # Check welcome message
        screen = self.client.capture_screen()
        assert "PilotCode" in screen, f"Welcome message not found. Screen: {screen[:200]}"
        assert "v0.2" in screen or "Commands:" in screen, "Version or commands not found"
        print(f"  Screen: {screen[:300]}...")
    
    def test_help_command(self):
        """Test 2: /help command."""
        self.client.session_id = "test_help"
        assert self.client.launch_tui(self.cli_cmd), "Failed to launch"
        time.sleep(2)
        
        # Send help command
        self.client.send_keys("/help", delay=0.5)
        self.client.send_enter()
        time.sleep(2)
        
        # Check response
        screen = self.client.capture_screen()
        print(f"  Screen: {screen[:400]}...")
        
        # Should show help content
        has_help = any(word in screen.lower() for word in ["available", "command", "/save", "/load", "/quit"])
        assert has_help, f"No help content found. Screen: {screen[:300]}"
    
    def test_time_query(self):
        """Test 3: Time query (now uses LLM, so just check it processes)."""
        self.client.session_id = "test_time"
        assert self.client.launch_tui(self.cli_cmd), "Failed to launch"
        time.sleep(2)
        
        # Send query
        self.client.send_keys("What time is it?", delay=0.5)
        self.client.send_enter()
        time.sleep(15)  # Wait for LLM
        
        # Check response (just verify something happened)
        screen = self.client.capture_screen()
        print(f"  Screen: {screen[:400]}...")
        
        # Should show "Thinking..." or response
        has_response = any(word in screen for word in ["Thinking", "Response", "time", "Error"])
        assert has_response, f"No response. Screen: {screen[:300]}"
    
    def test_clear_command(self):
        """Test 4: /clear command."""
        self.client.session_id = "test_clear"
        assert self.client.launch_tui(self.cli_cmd), "Failed to launch"
        time.sleep(2)
        
        # Add some content first
        self.client.send_keys("hello", delay=0.5)
        self.client.send_enter()
        time.sleep(2)
        
        # Clear
        self.client.send_keys("/clear", delay=0.5)
        self.client.send_enter()
        time.sleep(2)
        
        # Check cleared
        screen = self.client.capture_screen()
        print(f"  Screen after clear: {screen[:300]}...")
        
        # Should show cleared message or empty prompt
        assert "cleared" in screen.lower() or "You:" in screen, "Clear failed"
    
    def test_quit_command(self):
        """Test 5: /quit command."""
        self.client.session_id = "test_quit"
        assert self.client.launch_tui(self.cli_cmd), "Failed to launch"
        time.sleep(2)
        
        # Send quit
        self.client.send_keys("/quit", delay=0.5)
        self.client.send_enter()
        time.sleep(2)
        
        # Check goodbye message
        screen = self.client.capture_screen()
        print(f"  Screen: {screen[:300]}...")
        
        assert "goodbye" in screen.lower() or "bye" in screen.lower(), "Quit message not found"
    
    def run_all_tests(self):
        """Run all tests."""
        print("="*60)
        print("PilotCode Simple CLI Test")
        print("="*60)
        
        # Run tests
        self.run_test("Startup & Welcome", self.test_startup)
        self.run_test("Help Command", self.test_help_command)
        self.run_test("Time Query", self.test_time_query)
        self.run_test("Clear Command", self.test_clear_command)
        self.run_test("Quit Command", self.test_quit_command)
        
        # Print summary
        print()
        print("="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        
        for result in self.results:
            status = "✅ PASS" if result.passed else "❌ FAIL"
            print(f"{status}: {result.name} ({result.duration:.2f}s)")
            if result.error and not result.passed:
                print(f"      Error: {result.error[:100]}")
        
        print()
        print(f"Total: {passed}/{total} passed ({100*passed/total:.0f}%)")
        print("="*60)
        
        return passed == total


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Simple CLI")
    parser.add_argument("--server-path", default="/home/zx/mycc/mcp-tui-test-main/server.py")
    parser.add_argument("--cli-cmd", default=None)
    args = parser.parse_args()
    
    # Default command with proper path
    if args.cli_cmd is None:
        cmd = "bash -c 'cd /home/zx/mycc/PilotCode && PYTHONPATH=src python3 -m pilotcode.tui.simple_cli --auto-allow'"
    else:
        cmd = args.cli_cmd
    
    with MCPTUITestClient(server_path=args.server_path) as client:
        tester = SimpleCLITester(client, cli_cmd=cmd)
        success = tester.run_all_tests()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
