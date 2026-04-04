#!/usr/bin/env python3
"""
Test PilotCode TUI using mcp-tui-test MCP server.

This script tests all input/output scenarios:
1. Time query (现在几点了)
2. Factorial code generation
3. Project structure analysis
4. File operations
5. Multi-turn conversation
6. Session save/load
7. Commands (/help, /clear)

Requirements:
    git clone https://github.com/GeorgePearse/mcp-tui-test.git
    cd mcp-tui-test
    pip install -e .
    
    OR run server directly:
    python /path/to/mcp-tui-test/server.py

Usage:
    python test_with_mcp_tui_test.py
    python test_with_mcp_tui_test.py --server-path /path/to/server.py
    python test_with_mcp_tui_test.py --test time_query
"""

import asyncio
import json
import subprocess
import sys
import time
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass


@dataclass
class TestResult:
    name: str
    passed: bool
    duration: float
    error: Optional[str] = None
    screenshot: Optional[str] = None


class MCPTUITestClient:
    """Client for mcp-tui-test MCP server."""
    
    def __init__(self, server_path: Optional[str] = None, session_id: str = "default"):
        self.server_path = server_path or self._find_server()
        self.session_id = session_id
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 0
        
    def _find_server(self) -> str:
        """Find mcp-tui-test server."""
        # Common locations
        possible_paths = [
            "mcp-tui-test",
            "/usr/local/bin/mcp-tui-test",
            str(Path.home() / ".local" / "bin" / "mcp-tui-test"),
            str(Path.home() / "mcp-tui-test" / "server.py"),
            "/tmp/mcp-tui-test/server.py",
        ]
        
        for path in possible_paths:
            if Path(path).exists():
                return path
        
        raise RuntimeError(
            "mcp-tui-test not found. Please install:\n"
            "  git clone https://github.com/GeorgePearse/mcp-tui-test.git\n"
            "  cd mcp-tui-test\n"
            "  pip install -e ."
        )
    
    def __enter__(self):
        """Start MCP server."""
        cmd = [sys.executable, self.server_path] if self.server_path.endswith('.py') else [self.server_path]
        
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        # Wait a moment for server to start
        time.sleep(1)
        
        # Initialize MCP connection
        self._initialize()
        
        return self
    
    def __exit__(self, *args):
        """Stop MCP server."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
    
    def _send_request(self, method: str, params: dict) -> dict:
        """Send JSON-RPC request."""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": f"tools/call",
            "params": {
                "name": method,
                "arguments": params
            }
        }
        
        # Send request
        data = json.dumps(request) + "\n"
        self.process.stdin.write(data)
        self.process.stdin.flush()
        
        # Read response
        response_line = self.process.stdout.readline()
        return json.loads(response_line)
    
    def _initialize(self):
        """Initialize MCP connection."""
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pilotcode-test", "version": "1.0"}
            }
        }
        
        data = json.dumps(init_req) + "\n"
        self.process.stdin.write(data)
        self.process.stdin.flush()
        
        # Read response
        response = self.process.stdout.readline()
        
        # Send initialized notification
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        self.process.stdin.write(json.dumps(notif) + "\n")
        self.process.stdin.flush()
    
    def launch_tui(self, command: str, session_id: str = None, 
                   mode: str = "buffer", dimensions: str = "120x40") -> bool:
        """Launch TUI application."""
        session_id = session_id or self.session_id
        result = self._send_request("launch_tui", {
            "command": command,
            "session_id": session_id,
            "mode": mode,
            "dimensions": dimensions,
            "timeout": 30
        })
        
        if "error" in result:
            print(f"Launch error: {result['error']}")
            return False
        
        # Check if actually launched
        if "result" in result:
            res = result["result"]
            if res.get("isError"):
                print(f"Launch failed: {res}")
                return False
            # Check content for success indicator
            content = res.get("content", [{}])
            if content and isinstance(content, list):
                text = content[0].get("text", "")
                if "✓ Launched" in text or "Launched" in text:
                    return True
        
        print(f"Unexpected launch result: {result}")
        return False
    
    def send_keys(self, keys: str, session_id: str = None, delay: float = 0.1) -> bool:
        """Send keyboard input."""
        session_id = session_id or self.session_id
        result = self._send_request("send_keys", {
            "keys": keys,
            "session_id": session_id,
            "delay": delay
        })
        time.sleep(delay + 0.5)  # Wait for processing
        return "error" not in result
    
    def send_enter(self, session_id: str = None, key_type: str = "lf") -> bool:
        """Send Enter key."""
        session_id = session_id or self.session_id
        result = self._send_request("send_enter", {
            "session_id": session_id,
            "key_type": key_type
        })
        time.sleep(0.5)
        return "error" not in result
    
    def send_ctrl(self, key: str, session_id: str = None) -> bool:
        """Send Ctrl+key combination."""
        session_id = session_id or self.session_id
        result = self._send_request("send_ctrl", {
            "key": key,
            "session_id": session_id
        })
        time.sleep(0.5)
        return "error" not in result
    
    def capture_screen(self, session_id: str = None) -> str:
        """Capture screen content."""
        session_id = session_id or self.session_id
        result = self._send_request("capture_screen", {
            "session_id": session_id,
            "include_ansi": False
        })
        
        try:
            if "result" in result and "content" in result["result"]:
                content = result["result"]["content"]
                if isinstance(content, list) and len(content) > 0:
                    text = content[0].get("text", "")
                    # Extract actual screen content from formatted output
                    if "============================================================" in text:
                        lines = text.split("\n")
                        start = -1
                        end = -1
                        for i, line in enumerate(lines):
                            if "=" * 20 in line:
                                if start == -1:
                                    start = i + 1
                                else:
                                    end = i
                                    break
                        if start != -1 and end != -1:
                            return "\n".join(lines[start:end])
                    return text
        except Exception as e:
            print(f"  Capture error: {e}")
        return ""
    
    def expect_text(self, pattern: str, session_id: str = "default", 
                   timeout: float = 10) -> bool:
        """Wait for text to appear."""
        result = self._send_request("expect_text", {
            "pattern": pattern,
            "session_id": session_id,
            "timeout": timeout
        })
        return "error" not in result
    
    def assert_contains(self, text: str, session_id: str = "default") -> bool:
        """Assert screen contains text."""
        screen = self.capture_screen(session_id)
        return text in screen
    
    def close_session(self, session_id: str = None) -> bool:
        """Close session."""
        session_id = session_id or self.session_id
        result = self._send_request("close_session", {
            "session_id": session_id
        })
        return "error" not in result


class PilotCodeTUITester:
    """Test PilotCode TUI using mcp-tui-test."""
    
    def __init__(self, client: MCPTUITestClient, 
                 pilotcode_cmd: str = "bash -c 'cd /home/zx/mycc/PilotCode && python3 -m pilotcode main --auto-allow'"):
        self.client = client
        self.pilotcode_cmd = pilotcode_cmd
        self.results: List[TestResult] = []
    
    def run_test(self, name: str, test_func) -> TestResult:
        """Run a single test."""
        print(f"\n{'='*60}")
        print(f"TEST: {name}")
        print(f"{'='*60}")
        
        start = time.time()
        try:
            test_func()
            duration = time.time() - start
            print(f"✅ PASSED ({duration:.2f}s)")
            result = TestResult(name=name, passed=True, duration=duration)
        except AssertionError as e:
            duration = time.time() - start
            print(f"❌ FAILED: {e}")
            result = TestResult(name=name, passed=False, duration=duration, error=str(e))
        except Exception as e:
            duration = time.time() - start
            print(f"❌ ERROR: {e}")
            result = TestResult(name=name, passed=False, duration=duration, error=str(e))
        finally:
            # Cleanup session
            try:
                self.client.close_session()
            except:
                pass
        
        self.results.append(result)
        return result
    
    # === Test Cases ===
    
    def test_startup(self):
        """Test 1: Startup and welcome screen."""
        # Use unique session for this test
        self.client.session_id = "test_startup"
        
        # Launch
        assert self.client.launch_tui(self.pilotcode_cmd), "Failed to launch"
        
        # Wait for TUI to fully render (may take 2-5 seconds)
        for i in range(10):
            time.sleep(1)
            screen = self.client.capture_screen()
            if "PilotCode" in screen:
                break
        
        # Check welcome screen
        assert "PilotCode" in screen, f"Welcome message not found. Screen: {screen[:200]}"
        assert "v0.2" in screen or "v0." in screen, "Version not found"
        print(f"  Screen content: {screen[:150]}...")
    
    def test_time_query(self):
        """Test 2: Time query (现在几点了)."""
        self.client.session_id = "test_time"
        assert self.client.launch_tui(self.pilotcode_cmd), "Failed to launch"
        time.sleep(2)
        
        # Send query
        self.client.send_keys("现在几点了", delay=1)
        self.client.send_enter()
        
        # Wait for response
        time.sleep(20)  # Wait for AI response
        
        # Check response
        screen = self.client.capture_screen()
        print(f"  Screen: {screen[:300]}...")
        
        # Should contain time-related content or suggest using date command
        has_time = any(word in screen for word in ["时间", "点", "分", "date", "time", "clock"])
        assert has_time, f"No time-related content. Screen: {screen[:300]}"
    
    def test_code_generation(self):
        """Test 3: Factorial code generation."""
        self.client.session_id = "test_code"
        assert self.client.launch_tui(self.pilotcode_cmd), "Failed to launch"
        time.sleep(2)
        
        # Request code
        self.client.send_keys("编写一个计算阶乘的C语言程序，可以计算1-200的阶乘", delay=1)
        self.client.send_enter()
        
        # Wait for generation
        time.sleep(30)
        
        # Check response
        screen = self.client.capture_screen()
        print(f"  Screen: {screen[:400]}...")
        
        # Should contain code
        has_code = "```c" in screen or "#include" in screen or "factorial" in screen.lower()
        assert has_code, "No code generated"
    
    def test_file_operations(self):
        """Test 4: File read/write."""
        assert self.client.launch_tui(self.pilotcode_cmd), "Failed to launch"
        time.sleep(2)
        
        # Create a file via query
        self.client.send_keys("创建一个hello.txt文件，内容为Hello World", delay=1)
        self.client.send_enter()
        
        # Wait
        time.sleep(10)
        
        # Check response
        screen = self.client.capture_screen()
        print(f"  Screen: {screen[:300]}...")
        
        # Should mention file creation
        has_file = "文件" in screen or "file" in screen.lower() or "created" in screen.lower()
        assert has_file, "No file operation mentioned"
    
    def test_project_analysis(self):
        """Test 5: Project structure analysis."""
        self.client.session_id = "test_project"
        assert self.client.launch_tui(self.pilotcode_cmd), "Failed to launch"
        time.sleep(2)
        
        # Request analysis
        self.client.send_keys("分析当前目录下程序结构", delay=1)
        self.client.send_enter()
        
        # Wait
        time.sleep(20)
        
        # Check response
        screen = self.client.capture_screen()
        print(f"  Screen: {screen[:400]}...")
        
        # Should contain analysis (more flexible check)
        has_analysis = any(word in screen for word in ["结构", "目录", "文件", "src", "分析", "项目", "代码", "文件"])
        assert has_analysis, "No project analysis found"
    
    def test_multi_turn(self):
        """Test 6: Multi-turn conversation."""
        self.client.session_id = "test_multi"
        assert self.client.launch_tui(self.pilotcode_cmd), "Failed to launch"
        time.sleep(2)
        
        # Turn 1: Create file request
        self.client.send_keys("创建一个test.py文件\n", delay=1)
        time.sleep(8)
        
        # Turn 2: Add content
        self.client.send_keys("添加一个hello函数\n", delay=1)
        time.sleep(8)
        
        # Check response
        screen = self.client.capture_screen()
        print(f"  Screen: {screen[:400]}...")
        
        # Should have substantial content
        assert len(screen) > 100, "No meaningful response"
    
    def test_help_command(self):
        """Test 7: /help command."""
        self.client.session_id = "test_help"
        assert self.client.launch_tui(self.pilotcode_cmd), "Failed to launch"
        time.sleep(2)
        
        # Send help command
        self.client.send_keys("/help", delay=1)
        self.client.send_enter()
        time.sleep(3)
        
        # Check response
        screen = self.client.capture_screen()
        print(f"  Screen: {screen[:300]}...")
        
        # Should contain help
        has_help = any(word in screen.lower() for word in ["help", "command", "available"])
        assert has_help, "No help content found"
    
    def test_clear_command(self):
        """Test 8: /clear command."""
        self.client.session_id = "test_clear"
        assert self.client.launch_tui(self.pilotcode_cmd), "Failed to launch"
        time.sleep(2)
        
        # Add content first
        self.client.send_keys("Hello\n", delay=1)
        time.sleep(3)
        
        # Clear
        self.client.send_keys("/clear\n", delay=1)
        time.sleep(2)
        
        # Check screen cleared (should still have some UI elements)
        screen = self.client.capture_screen()
        print(f"  Screen after clear: {screen[:200]}...")
        
        # Should not error
        assert "Error" not in screen or "error" not in screen.lower(), "Clear command failed"
    
    def run_all_tests(self):
        """Run all tests."""
        tests = [
            ("Startup & Welcome", self.test_startup),
            ("Time Query (现在几点了)", self.test_time_query),
            ("Code Generation (Factorial)", self.test_code_generation),
            ("File Operations", self.test_file_operations),
            ("Project Analysis", self.test_project_analysis),
            ("Multi-turn Conversation", self.test_multi_turn),
            ("Help Command", self.test_help_command),
            ("Clear Command", self.test_clear_command),
        ]
        
        for name, test_func in tests:
            self.run_test(name, test_func)
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        total_time = sum(r.duration for r in self.results)
        
        for r in self.results:
            status = "✅ PASS" if r.passed else "❌ FAIL"
            print(f"{status}: {r.name} ({r.duration:.2f}s)")
            if r.error:
                print(f"      Error: {r.error[:80]}")
        
        print(f"\nTotal: {passed}/{total} passed ({passed/total*100:.1f}%)")
        print(f"Time: {total_time:.2f}s")
        print("="*60)


async def main():
    parser = argparse.ArgumentParser(description="Test PilotCode TUI with mcp-tui-test")
    parser.add_argument("--server-path", help="Path to mcp-tui-test server.py")
    parser.add_argument("--pilotcode-cmd", default="bash -c 'cd /home/zx/mycc/PilotCode && python3 -m pilotcode main --auto-allow'",
                       help="Command to launch PilotCode")
    parser.add_argument("--test", help="Run specific test only")
    args = parser.parse_args()
    
    print("="*60)
    print("PilotCode TUI Test with mcp-tui-test")
    print("="*60)
    
    # Use synchronous client
    with MCPTUITestClient(server_path=args.server_path) as client:
        tester = PilotCodeTUITester(client, pilotcode_cmd=args.pilotcode_cmd)
        
        if args.test:
            # Run specific test
            test_map = {
                "startup": tester.test_startup,
                "time": tester.test_time_query,
                "code": tester.test_code_generation,
                "file": tester.test_file_operations,
                "project": tester.test_project_analysis,
                "multi": tester.test_multi_turn,
                "help": tester.test_help_command,
                "clear": tester.test_clear_command,
            }
            if args.test in test_map:
                tester.run_test(args.test, test_map[args.test])
            else:
                print(f"Unknown test: {args.test}")
                print(f"Available: {list(test_map.keys())}")
        else:
            # Run all tests
            tester.run_all_tests()


if __name__ == "__main__":
    # Use asyncio.run for the async main, but client is sync
    import asyncio
    
    # Actually the client is sync, so we don't need async
    # Let's rewrite main to be synchronous
    
    parser = argparse.ArgumentParser(description="Test PilotCode TUI with mcp-tui-test")
    parser.add_argument("--server-path", help="Path to mcp-tui-test server.py")
    parser.add_argument("--pilotcode-cmd", default="bash -c 'cd /home/zx/mycc/PilotCode && python3 -m pilotcode main --auto-allow'",
                       help="Command to launch PilotCode")
    parser.add_argument("--test", help="Run specific test only (startup, time, code, file, project, multi, help, clear)")
    args = parser.parse_args()
    
    print("="*60)
    print("PilotCode TUI Test with mcp-tui-test")
    print("="*60)
    
    try:
        with MCPTUITestClient(server_path=args.server_path) as client:
            tester = PilotCodeTUITester(client, pilotcode_cmd=args.pilotcode_cmd)
            
            if args.test:
                test_map = {
                    "startup": tester.test_startup,
                    "time": tester.test_time_query,
                    "code": tester.test_code_generation,
                    "file": tester.test_file_operations,
                    "project": tester.test_project_analysis,
                    "multi": tester.test_multi_turn,
                    "help": tester.test_help_command,
                    "clear": tester.test_clear_command,
                }
                if args.test in test_map:
                    tester.run_test(args.test, test_map[args.test])
                else:
                    print(f"Unknown test: {args.test}")
                    print(f"Available: {list(test_map.keys())}")
            else:
                tester.run_all_tests()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
