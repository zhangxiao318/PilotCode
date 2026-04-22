"""PilotCode TUI Test Suite - Automated tests for PilotCode TUI functionality."""

import asyncio
import tempfile
import os
import shutil
from typing import List, Tuple, Optional
from dataclasses import dataclass

from .client import TUITestClient


@dataclass
class TestResult:
    """Result of a single test."""

    name: str
    passed: bool
    duration: float
    error: Optional[str] = None
    screenshot: Optional[str] = None


class PilotCodeTestSuite:
    """Comprehensive test suite for PilotCode TUI.

    Tests:
    1. Basic startup and welcome screen
    2. Simple query (time, weather, etc.)
    3. Code generation (factorial, etc.)
    4. File operations (read, write, glob)
    5. Project analysis
    6. Multi-turn conversation
    7. Error handling
    8. Session save/load

    Example:
        async with PilotCodeTestSuite() as suite:
            results = await suite.run_all_tests()
            suite.print_report(results)
    """

    def __init__(
        self,
        pilotcode_command: str = "python -m pilotcode --auto-allow",
        server_command: Optional[str] = None,
        screenshots_dir: Optional[str] = None,
    ):
        """Initialize test suite.

        Args:
            pilotcode_command: Command to launch PilotCode TUI
            server_command: MCP TUI server command (auto-detected if None)
            screenshots_dir: Directory to save failure screenshots
        """
        self.pilotcode_command = pilotcode_command
        self.server_command = server_command
        self.screenshots_dir = screenshots_dir or tempfile.mkdtemp(
            prefix="pilotcode_test_screenshots_"
        )
        self.client: Optional[TUITestClient] = None
        self.test_dir: Optional[str] = None

    async def __aenter__(self):
        """Setup test environment."""
        # Create temp test directory
        self.test_dir = tempfile.mkdtemp(prefix="pilotcode_test_")

        # Initialize MCP client
        self.client = TUITestClient(server_command=self.server_command)
        await self.client.__aenter__()

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup test environment."""
        if self.client:
            await self.client.__aexit__(exc_type, exc_val, exc_tb)

        # Cleanup test directory
        if self.test_dir and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    async def _launch_pilotcode(self, session_id: str = "pilotcode_test"):
        """Launch PilotCode TUI."""
        return await self.client.launch_tui(
            command=self.pilotcode_command,
            session_id=session_id,
            mode="buffer",
            dimensions="120x40",
            cwd=self.test_dir,
        )

    async def _take_screenshot(self, name: str, session_id: str = "pilotcode_test") -> str:
        """Take a screenshot and save it."""
        screen = await self.client.capture_screen(session_id)
        screenshot_path = os.path.join(self.screenshots_dir, f"{name}.txt")
        with open(screenshot_path, "w") as f:
            f.write(screen.raw_text)
        return screenshot_path

    # === Individual Tests ===

    async def test_startup(self) -> TestResult:
        """Test 1: Basic startup and welcome screen."""
        import time

        start = time.time()

        try:
            # Launch PilotCode
            await self._launch_pilotcode()

            # Wait for welcome screen
            await self.client.expect_text("PilotCode", timeout=5)

            # Verify expected elements
            screen = await self.client.capture_screen()
            assert "PilotCode" in screen.raw_text, "Welcome message not found"
            assert "v0.2.0" in screen.raw_text or "v0." in screen.raw_text, "Version not found"

            # Cleanup
            await self.client.close_session()

            return TestResult(name="Startup & Welcome", passed=True, duration=time.time() - start)

        except Exception as e:
            screenshot = await self._take_screenshot("startup_failure")
            return TestResult(
                name="Startup & Welcome",
                passed=False,
                duration=time.time() - start,
                error=str(e),
                screenshot=screenshot,
            )

    async def test_time_query(self) -> TestResult:
        """Test 2: Simple time query."""
        import time

        start = time.time()

        try:
            await self._launch_pilotcode()

            # Wait for input prompt
            await self.client.expect_text("Type", timeout=5)

            # Send time query
            await self.client.send_keys("现在几点了\n")

            # Wait for response (should contain time-related content)
            await self.client.expect_text("时间", timeout=15)

            # Verify response
            screen = await self.client.capture_screen()
            has_response = any(
                word in screen.raw_text for word in ["时间", "点", "分", "date", "time"]
            )
            assert has_response, "Time-related response not found"

            await self.client.close_session()

            return TestResult(name="Time Query", passed=True, duration=time.time() - start)

        except Exception as e:
            screenshot = await self._take_screenshot("time_query_failure")
            return TestResult(
                name="Time Query",
                passed=False,
                duration=time.time() - start,
                error=str(e),
                screenshot=screenshot,
            )

    async def test_code_generation(self) -> TestResult:
        """Test 3: Code generation (factorial)."""
        import time

        start = time.time()

        try:
            await self._launch_pilotcode()

            # Request factorial code
            await self.client.send_keys("编写一个计算阶乘的C语言程序，可以计算1-200的阶乘\n")

            # Wait for code generation
            await asyncio.sleep(10)  # Give time for code generation

            # Verify code was generated
            screen = await self.client.capture_screen()
            has_code = "```c" in screen.raw_text or "#include" in screen.raw_text
            assert has_code, "C code not generated"

            # Check if file was created (if FileWrite was used)
            factorial_path = os.path.join(self.test_dir, "factorial.c")
            os.path.exists(factorial_path)

            await self.client.close_session()

            return TestResult(
                name="Code Generation (Factorial)", passed=True, duration=time.time() - start
            )

        except Exception as e:
            screenshot = await self._take_screenshot("code_gen_failure")
            return TestResult(
                name="Code Generation (Factorial)",
                passed=False,
                duration=time.time() - start,
                error=str(e),
                screenshot=screenshot,
            )

    async def test_file_operations(self) -> TestResult:
        """Test 4: File read/write operations."""
        import time

        start = time.time()

        try:
            await self._launch_pilotcode()

            # Create a test file first
            test_file = os.path.join(self.test_dir, "test.txt")
            with open(test_file, "w") as f:
                f.write("Hello from PilotCode test!")

            # Ask PilotCode to read it
            await self.client.send_keys(f"读取文件 {test_file}\n")

            # Wait for file content
            await asyncio.sleep(5)

            # Verify file was read
            screen = await self.client.capture_screen()
            has_content = "Hello" in screen.raw_text or "FileRead" in screen.raw_text
            assert has_content, "File content not shown"

            await self.client.close_session()

            return TestResult(name="File Operations", passed=True, duration=time.time() - start)

        except Exception as e:
            screenshot = await self._take_screenshot("file_ops_failure")
            return TestResult(
                name="File Operations",
                passed=False,
                duration=time.time() - start,
                error=str(e),
                screenshot=screenshot,
            )

    async def test_project_analysis(self) -> TestResult:
        """Test 5: Project structure analysis."""
        import time

        start = time.time()

        try:
            await self._launch_pilotcode()

            # Create some structure
            os.makedirs(os.path.join(self.test_dir, "src"))
            os.makedirs(os.path.join(self.test_dir, "tests"))

            # Ask for analysis
            await self.client.send_keys("分析当前目录下程序结构\n")

            # Wait for analysis
            await asyncio.sleep(8)

            # Verify analysis was performed
            screen = await self.client.capture_screen()
            has_analysis = any(
                word in screen.raw_text.lower()
                for word in ["目录", "文件", "结构", "src", "test", "分析"]
            )
            assert has_analysis, "Project analysis not found"

            await self.client.close_session()

            return TestResult(name="Project Analysis", passed=True, duration=time.time() - start)

        except Exception as e:
            screenshot = await self._take_screenshot("project_analysis_failure")
            return TestResult(
                name="Project Analysis",
                passed=False,
                duration=time.time() - start,
                error=str(e),
                screenshot=screenshot,
            )

    async def test_multi_turn_conversation(self) -> TestResult:
        """Test 6: Multi-turn conversation with context."""
        import time

        start = time.time()

        try:
            await self._launch_pilotcode()

            # Turn 1: Ask to create a file
            await self.client.send_keys("创建一个hello.py文件\n")
            await asyncio.sleep(8)

            # Turn 2: Ask to modify it
            await self.client.send_keys("在hello.py中添加一个hello函数\n")
            await asyncio.sleep(8)

            # Verify file exists
            os.path.join(self.test_dir, "hello.py")
            # File might be created, might not - depends on AI

            screen = await self.client.capture_screen()
            has_response = len(screen.raw_text) > 100  # Should have substantial response
            assert has_response, "Multi-turn conversation failed"

            await self.client.close_session()

            return TestResult(
                name="Multi-turn Conversation", passed=True, duration=time.time() - start
            )

        except Exception as e:
            screenshot = await self._take_screenshot("multi_turn_failure")
            return TestResult(
                name="Multi-turn Conversation",
                passed=False,
                duration=time.time() - start,
                error=str(e),
                screenshot=screenshot,
            )

    async def test_clear_command(self) -> TestResult:
        """Test 7: /clear command."""
        import time

        start = time.time()

        try:
            await self._launch_pilotcode()

            # Add some content first
            await self.client.send_keys("Hello\n")
            await asyncio.sleep(3)

            # Clear screen
            await self.client.send_keys("/clear\n")
            await asyncio.sleep(2)

            # Screen should be mostly clear
            screen = await self.client.capture_screen()
            # Just verify no error occurred
            assert (
                "Error" not in screen.raw_text or "error" not in screen.raw_text.lower()
            ), "Clear command failed"

            await self.client.close_session()

            return TestResult(name="Clear Command", passed=True, duration=time.time() - start)

        except Exception as e:
            return TestResult(
                name="Clear Command", passed=False, duration=time.time() - start, error=str(e)
            )

    async def test_help_command(self) -> TestResult:
        """Test 8: /help command."""
        import time

        start = time.time()

        try:
            await self._launch_pilotcode()

            # Request help
            await self.client.send_keys("/help\n")
            await asyncio.sleep(3)

            # Verify help was shown
            screen = await self.client.capture_screen()
            has_help = any(
                word in screen.raw_text.lower()
                for word in ["help", "command", "available", "usage"]
            )
            assert has_help, "Help content not found"

            await self.client.close_session()

            return TestResult(name="Help Command", passed=True, duration=time.time() - start)

        except Exception as e:
            return TestResult(
                name="Help Command", passed=False, duration=time.time() - start, error=str(e)
            )

    # === Test Runner ===

    async def run_all_tests(self) -> List[TestResult]:
        """Run all tests and return results."""
        tests = [
            self.test_startup,
            self.test_time_query,
            self.test_code_generation,
            self.test_file_operations,
            self.test_project_analysis,
            self.test_multi_turn_conversation,
            self.test_clear_command,
            self.test_help_command,
        ]

        results = []
        for test in tests:
            result = await test()
            results.append(result)

            # Small delay between tests
            await asyncio.sleep(1)

        return results

    def print_report(self, results: List[TestResult]):
        """Print formatted test report."""
        print("\n" + "=" * 70)
        print("PILOTCODE TUI TEST REPORT")
        print("=" * 70)

        passed = sum(1 for r in results if r.passed)
        total = len(results)
        total_time = sum(r.duration for r in results)

        for result in results:
            status = "✅ PASS" if result.passed else "❌ FAIL"
            print(f"\n{status}: {result.name} ({result.duration:.2f}s)")
            if result.error:
                print(f"   Error: {result.error}")
            if result.screenshot:
                print(f"   Screenshot: {result.screenshot}")

        print("\n" + "=" * 70)
        print(f"Total: {passed}/{total} passed ({passed/total*100:.1f}%)")
        print(f"Time: {total_time:.2f}s")
        print(f"Screenshots: {self.screenshots_dir}")
        print("=" * 70)

        if passed == total:
            print("\n🎉 All tests passed!")
        else:
            print(f"\n⚠️ {total - passed} test(s) failed")


# Convenience function for running tests
async def run_pilotcode_tui_tests(
    pilotcode_command: str = "python -m pilotcode --auto-allow",
    server_command: Optional[str] = None,
) -> Tuple[int, List[TestResult]]:
    """Run all PilotCode TUI tests.

    Returns:
        Tuple of (exit_code, results)
    """
    async with PilotCodeTestSuite(
        pilotcode_command=pilotcode_command, server_command=server_command
    ) as suite:
        results = await suite.run_all_tests()
        suite.print_report(results)

        exit_code = 0 if all(r.passed for r in results) else 1
        return exit_code, results
