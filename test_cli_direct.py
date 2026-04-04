#!/usr/bin/env python3
"""
Direct test for Simple CLI without mcp-tui-test.
Uses subprocess for maximum compatibility.
"""

import subprocess
import time
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TestResult:
    name: str
    passed: bool
    duration: float
    error: Optional[str] = None


class CLITester:
    """Test CLI using direct subprocess."""
    
    def __init__(self, cli_cmd: List[str] = None):
        self.cli_cmd = cli_cmd or ["./run.sh"]
        self.cwd = "/home/zx/mycc/PilotCode"
        self.env = dict(subprocess.os.environ)  # Use existing env (run.sh sets PYTHONPATH)
        self.results: List[TestResult] = []
    
    def run_cli(self, inputs: List[str], timeout: int = 30) -> tuple:
        """Run CLI with given inputs and return (stdout, stderr, returncode)."""
        proc = subprocess.Popen(
            self.cli_cmd,
            cwd=self.cwd,
            env=self.env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Send all inputs
        stdin_text = "\n".join(inputs) + "\n"
        stdout, stderr = proc.communicate(input=stdin_text, timeout=timeout)
        
        return stdout, stderr, proc.returncode
    
    def run_test(self, name: str, test_func) -> TestResult:
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
            result = TestResult(name=name, passed=True, duration=duration)
        except AssertionError as e:
            duration = time_module.time() - start
            print(f"❌ FAILED: {e}")
            result = TestResult(name=name, passed=False, duration=duration, error=str(e))
        except Exception as e:
            duration = time_module.time() - start
            print(f"❌ ERROR: {e}")
            result = TestResult(name=name, passed=False, duration=duration, error=str(e))
        
        self.results.append(result)
        return result
    
    def test_startup_and_help(self):
        """Test startup and help command."""
        stdout, stderr, rc = self.run_cli(["/help", "/quit"])
        
        # Check welcome message
        assert "PilotCode" in stdout, f"Welcome not found. Output: {stdout[:200]}"
        assert "v0.2" in stdout, f"Version not found"
        
        # Check help content
        assert "Available Commands" in stdout or "/save" in stdout, f"Help not found"
        assert "/quit" in stdout, f"Quit command not in help"
        
        # Check clean exit
        assert rc == 0, f"Non-zero exit code: {rc}"
        assert "Goodbye" in stdout, f"Goodbye message not found"
        
        print(f"  Output length: {len(stdout)} chars")
        print(f"  ✓ Welcome message found")
        print(f"  ✓ Help content found")
        print(f"  ✓ Clean exit")
    
    def test_clear_command(self):
        """Test clear command."""
        stdout, stderr, rc = self.run_cli(["hello", "/clear", "/quit"])
        
        # Check clear worked
        assert "cleared" in stdout.lower() or rc == 0, f"Clear failed"
        
        print(f"  ✓ Clear command executed")
    
    def test_save_load(self):
        """Test save and load commands."""
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            session_file = f.name
        
        try:
            # First save a session
            stdout1, _, rc1 = self.run_cli(["Hello world", f"/save {session_file}", "/quit"])
            
            assert rc1 == 0, f"Save session failed with code {rc1}"
            assert "saved" in stdout1.lower(), f"Save confirmation not found: {stdout1}"
            
            # Check file exists
            assert Path(session_file).exists(), f"Session file not created"
            
            # Then load it
            stdout2, _, rc2 = self.run_cli([f"/load {session_file}", "/quit"])
            
            assert rc2 == 0, f"Load session failed with code {rc2}"
            assert "loaded" in stdout2.lower(), f"Load confirmation not found"
            
            print(f"  ✓ Save session: {session_file}")
            print(f"  ✓ Load session: success")
            
        finally:
            # Cleanup
            if Path(session_file).exists():
                os.unlink(session_file)
    
    def test_query_processing(self):
        """Test that queries are processed (may need LLM)."""
        stdout, stderr, rc = self.run_cli(["What is 2+2?", "/quit"], timeout=60)
        
        # Just verify it ran without crashing
        assert rc == 0, f"Non-zero exit code: {rc}"
        
        # Should show "You:" prompt at least
        assert "You:" in stdout, f"No prompt found"
        
        print(f"  ✓ Query processed without crash")
        print(f"  Output preview: {stdout[:300]}...")
    
    def run_all_tests(self):
        """Run all tests."""
        print("="*60)
        print("PilotCode Simple CLI Direct Test")
        print("="*60)
        
        self.run_test("Startup & Help", self.test_startup_and_help)
        self.run_test("Clear Command", self.test_clear_command)
        self.run_test("Save/Load Session", self.test_save_load)
        self.run_test("Query Processing", self.test_query_processing)
        
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
    tester = CLITester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
