#!/usr/bin/env python3
"""
Regression tests for Simple CLI using the standard test cases.
Uses subprocess to test the actual CLI with input/output.
"""

import subprocess
import time
import sys
import os
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class TestCase:
    """Test case with input and expected output checks."""
    name: str
    inputs: List[str]
    expected_in_output: List[str]
    expected_not_in_output: List[str] = None
    timeout: int = 60
    description: str = ""


@dataclass
class TestResult:
    name: str
    passed: bool
    duration: float
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None


class CLIRegressionTester:
    """Test Simple CLI using input/output test cases."""
    
    def __init__(self, cli_cmd: List[str] = None):
        self.cli_cmd = cli_cmd or ["./run.sh"]
        self.cwd = "/home/zx/mycc/PilotCode"
        self.env = dict(os.environ)
        self.results: List[TestResult] = []
        
        # Define standard test cases
        self.test_cases = [
            TestCase(
                name="Startup & Help",
                description="Test welcome message and /help command",
                inputs=["/help", "/quit"],
                expected_in_output=[
                    "PilotCode",
                    "v0.2",
                    "Available Commands",
                    "/save",
                    "/load",
                    "/quit",
                    "Goodbye"
                ],
                timeout=10
            ),
            TestCase(
                name="Clear Command",
                description="Test /clear command clears conversation",
                inputs=["hello", "/clear", "/quit"],
                expected_in_output=[
                    "Goodbye"
                ],
                timeout=10
            ),
            TestCase(
                name="Save/Load Session",
                description="Test session persistence",
                inputs=["test message", "/save /tmp/test_session.json", "/quit"],
                expected_in_output=[
                    "saved",
                    "Goodbye"
                ],
                timeout=15
            ),
            TestCase(
                name="Time Query (现在几点了)",
                description="Test basic AI response for time query",
                inputs=["现在几点了", "/quit"],
                expected_in_output=[
                    "Response:",  # Should have response marker
                ],
                expected_not_in_output=[
                    "Error processing query"
                ],
                timeout=60
            ),
            TestCase(
                name="Factorial Code Generation",
                description="Test code generation for factorial C program",
                inputs=["编写一个计算阶乘的C语言程序，可以计算1-200的阶乘", "/quit"],
                expected_in_output=[
                    "Response:",
                    # Code may be in file or in response
                    ("factorial", "阶乘", "```c", "#include", "FileWrite")
                ],
                expected_not_in_output=[
                    "Error processing query"
                ],
                timeout=90
            ),
            TestCase(
                name="Project Analysis",
                description="Test project structure analysis",
                inputs=["分析当前目录下程序结构", "/quit"],
                expected_in_output=[
                    "Response:"  # Should have analysis response
                ],
                expected_not_in_output=[
                    "Error processing query"
                ],
                timeout=60
            ),
        ]
    
    def run_cli(self, inputs: List[str], timeout: int = 30) -> Tuple[str, str, int]:
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
        
        try:
            stdout, stderr = proc.communicate(input=stdin_text, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            return stdout, stderr + "\n[TIMEOUT]", -1
        
        return stdout, stderr, proc.returncode
    
    def run_test_case(self, test_case: TestCase) -> TestResult:
        """Run a single test case."""
        print(f"\n{'='*70}")
        print(f"TEST: {test_case.name}")
        print(f"{'='*70}")
        print(f"Description: {test_case.description}")
        print(f"Inputs: {test_case.inputs}")
        
        start = time.time()
        
        try:
            stdout, stderr, rc = self.run_cli(test_case.inputs, test_case.timeout)
            duration = time.time() - start
            
            # Check expected content in output
            # Support tuples for OR logic (any of the options)
            missing = []
            for expected in test_case.expected_in_output:
                if isinstance(expected, tuple):
                    # OR logic: at least one of the options must be present
                    if not any(opt in stdout for opt in expected):
                        missing.append(f"any of {expected}")
                elif expected not in stdout:
                    missing.append(expected)
            
            # Check unexpected content not in output
            unexpected = []
            if test_case.expected_not_in_output:
                for not_expected in test_case.expected_not_in_output:
                    if not_expected in stdout:
                        unexpected.append(not_expected)
            
            # Determine pass/fail
            if missing or unexpected:
                errors = []
                if missing:
                    errors.append(f"Missing expected: {missing}")
                if unexpected:
                    errors.append(f"Unexpected found: {unexpected}")
                error_msg = "; ".join(errors)
                print(f"❌ FAILED: {error_msg}")
                print(f"\nStdout preview:\n{stdout[:500]}...")
                return TestResult(
                    name=test_case.name,
                    passed=False,
                    duration=duration,
                    stdout=stdout,
                    stderr=stderr,
                    error=error_msg
                )
            
            print(f"✅ PASSED ({duration:.2f}s)")
            print(f"  Return code: {rc}")
            print(f"  Output length: {len(stdout)} chars")
            return TestResult(
                name=test_case.name,
                passed=True,
                duration=duration,
                stdout=stdout,
                stderr=stderr
            )
            
        except Exception as e:
            duration = time.time() - start
            print(f"❌ ERROR: {e}")
            return TestResult(
                name=test_case.name,
                passed=False,
                duration=duration,
                error=str(e)
            )
    
    def run_all_tests(self):
        """Run all test cases."""
        print("="*70)
        print("PILOTCODE CLI REGRESSION TEST SUITE")
        print("="*70)
        print(f"CLI Command: {' '.join(self.cli_cmd)}")
        print(f"Working Dir: {self.cwd}")
        print(f"Total Tests: {len(self.test_cases)}")
        
        # Run each test case
        for test_case in self.test_cases:
            result = self.run_test_case(test_case)
            self.results.append(result)
        
        # Print summary
        self.print_summary()
        
        return all(r.passed for r in self.results)
    
    def print_summary(self):
        """Print test summary."""
        print()
        print("="*70)
        print("TEST SUMMARY")
        print("="*70)
        
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        
        for result in self.results:
            status = "✅ PASS" if result.passed else "❌ FAIL"
            print(f"{status}: {result.name} ({result.duration:.2f}s)")
            if result.error and not result.passed:
                print(f"      Error: {result.error[:100]}")
        
        print()
        print(f"Total: {passed}/{total} passed ({100*passed/total:.0f}%)")
        print("="*70)
        
        if passed == total:
            print("\n🎉 All regression tests passed!")
        else:
            print(f"\n⚠️  {total - passed} test(s) failed")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='PilotCode CLI Regression Tests')
    parser.add_argument('--cli-cmd', default=None,
                       help='CLI command to test (default: ./run.sh)')
    parser.add_argument('--test', default=None,
                       help='Run specific test only')
    
    args = parser.parse_args()
    
    # Create tester
    cli_cmd = args.cli_cmd.split() if args.cli_cmd else None
    tester = CLIRegressionTester(cli_cmd=cli_cmd)
    
    # Run specific test or all
    if args.test:
        test_case = next((tc for tc in tester.test_cases if args.test.lower() in tc.name.lower()), None)
        if test_case:
            print("="*70)
            print("PILOTCODE CLI REGRESSION TEST")
            print("="*70)
            result = tester.run_test_case(test_case)
            tester.results = [result]
            tester.print_summary()
            return 0 if result.passed else 1
        else:
            print(f"Test not found: {args.test}")
            print(f"Available: {[tc.name for tc in tester.test_cases]}")
            return 1
    else:
        success = tester.run_all_tests()
        return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
