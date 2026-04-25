"""Layer 2: Task Planning Capability.

Tests whether the LLM can decompose complex coding tasks into correct
multi-step sequences and execute them with appropriate tools.

Attribution rules:
- Wrong sequence (edit before read) -> llm_function_calling
- Missing steps (no test after edit) -> llm_capability / llm_function_calling
- Redundant steps (re-read same file multiple times) -> llm_function_calling
- Correct plan but tool execution fails -> pilotcode_tool
"""

from __future__ import annotations

import asyncio
import pytest
import tempfile
from pathlib import Path

from ..engine_helper import run_with_tools, ToolRunResult


@pytest.mark.llm_e2e
class TestMultiStepCodingTask:
    """Complex tasks requiring discover -> read -> modify -> verify."""

    async def test_find_and_read_then_answer(self, model_capability_client, e2e_timeout):
        """Find a file, read it, then answer a question without re-reading."""
        qe = model_capability_client
        result: ToolRunResult = await asyncio.wait_for(
            run_with_tools(
                qe,
                "Find the file that defines QueryEngineConfig, read it, then tell me what fields it has.",
                timeout=e2e_timeout,
                max_turns=12,
            ),
            timeout=e2e_timeout + 30,
        )

        tool_names = [tc.name for tc in result.tool_calls]

        # Should discover first
        has_discovery = any(t in tool_names for t in ("Glob", "Grep", "CodeSearch", "LSP"))
        assert has_discovery, (
            f"Should discover file first, got tools: {tool_names}\n"
            f"Final response: {result.final_response!r}"
        )

        # Should read the file
        assert "FileRead" in tool_names, f"Should read the discovered file, got tools: {tool_names}"

        # Should provide a non-empty answer
        assert (
            len(result.final_response) > 20
        ), f"Should provide an answer, got: {result.final_response!r}"

    async def test_add_function_and_run(self, model_capability_client, e2e_timeout, tmp_path):
        """Create a Python file with a function, then run it with Bash."""
        qe = model_capability_client
        # Create a temporary working directory for this test
        test_dir = tmp_path / "planning_test"
        test_dir.mkdir()
        qe.config.cwd = str(test_dir)
        if qe.config.set_app_state:
            qe.config.set_app_state(lambda s: setattr(s, "cwd", str(test_dir)) or s)

        result: ToolRunResult = await asyncio.wait_for(
            run_with_tools(
                qe,
                (
                    "Create a file called math_utils.py containing a function "
                    "'add(a, b)' that returns a + b. Then run a Python command to test it."
                ),
                timeout=e2e_timeout,
                max_turns=12,
            ),
            timeout=e2e_timeout + 30,
        )

        tool_names = [tc.name for tc in result.tool_calls]

        # Should write a file
        assert (
            "FileWrite" in tool_names or "FileEdit" in tool_names
        ), f"Should write or edit a file, got tools: {tool_names}"

        # Should run a test
        assert "Bash" in tool_names, (
            f"Should run a bash command to test the code, got tools: {tool_names}\n"
            f"Final response: {result.final_response!r}"
        )

        # Verify file was actually created
        created_file = test_dir / "math_utils.py"
        assert created_file.exists(), f"File was not created at {created_file}"

    async def test_generate_count_script_and_execute(
        self, model_capability_client, e2e_timeout, tmp_path
    ):
        """LLM generates a Python script to count files, executes it, and verifies output.

        Validates the full write -> execute -> verify loop for script generation tasks.
        """
        qe = model_capability_client
        test_dir = tmp_path / "count_script_test"
        test_dir.mkdir()

        # Pre-create files with known content for deterministic verification
        (test_dir / "a.txt").write_text("line1\nline2\nline3\n")
        (test_dir / "b.txt").write_text("line4\nline5\n")
        (test_dir / "c.py").write_text("print('hello')\n")

        qe.config.cwd = str(test_dir)
        if qe.config.set_app_state:
            qe.config.set_app_state(lambda s: setattr(s, "cwd", str(test_dir)) or s)

        result: ToolRunResult = await asyncio.wait_for(
            run_with_tools(
                qe,
                (
                    f"Write a Python script '{test_dir}/count_files.py' that counts "
                    f"the number of .txt files and total lines in {test_dir}, "
                    "then prints 'files=X, lines=Y' where X and Y are the actual counts. "
                    "Then run the script with Bash."
                ),
                timeout=e2e_timeout,
                max_turns=12,
            ),
            timeout=e2e_timeout + 30,
        )

        tool_names = [tc.name for tc in result.tool_calls]

        # Should create the script (FileWrite or Bash redirect)
        assert "FileWrite" in tool_names or "Bash" in tool_names, (
            f"Should write script via FileWrite or Bash, got: {tool_names}\n"
            f"Final response: {result.final_response!r}"
        )

        # Should execute the script
        assert "Bash" in tool_names, (
            f"Should run Bash to execute script, got: {tool_names}\n"
            f"Final response: {result.final_response!r}"
        )

        # Verify correctness: 2 txt files, 5 lines total
        assert (
            "files=2" in result.final_response
        ), f"Expected 'files=2' in response, got: {result.final_response!r}"
        assert (
            "lines=5" in result.final_response
        ), f"Expected 'lines=5' in response, got: {result.final_response!r}"

    async def test_generate_recursive_script_with_excludes(
        self, model_capability_client, e2e_timeout, tmp_path
    ):
        """LLM generates a recursive script with exclude patterns (e.g. __pycache__, .git).

        Simulates real-world directory scanning where certain directories must be skipped.
        """
        qe = model_capability_client
        test_dir = tmp_path / "recursive_script_test"
        test_dir.mkdir()

        # Create nested structure with mixed file types
        for p in ["src/sub", "__pycache__", ".git", ".venv"]:
            (test_dir / p).mkdir(parents=True, exist_ok=True)

        (test_dir / "src" / "a.py").write_text("x = 1\n")
        (test_dir / "src" / "b.py").write_text("y = 2\ny = 3\n")
        (test_dir / "src" / "sub" / "c.py").write_text("z = 4\n")
        (test_dir / "src" / "readme.txt").write_text("docs\n")
        # Excluded directories (should not count)
        (test_dir / "__pycache__" / "cache.pyc").write_text("cached\n")
        (test_dir / ".git" / "config").write_text("gitconfig\n")
        (test_dir / ".venv" / "lib.py").write_text("lib\n")

        qe.config.cwd = str(test_dir)
        if qe.config.set_app_state:
            qe.config.set_app_state(lambda s: setattr(s, "cwd", str(test_dir)) or s)

        result: ToolRunResult = await asyncio.wait_for(
            run_with_tools(
                qe,
                (
                    f"Write a Python script that recursively counts all .py files under {test_dir}, "
                    "excluding '__pycache__', '.git', and '.venv' directories. "
                    "Print the result as 'py_files=N'. Then run it with Bash."
                ),
                timeout=e2e_timeout,
                max_turns=12,
            ),
            timeout=e2e_timeout + 30,
        )

        tool_names = [tc.name for tc in result.tool_calls]
        assert "Bash" in tool_names, f"Should run Bash to execute script, got: {tool_names}"

        # Expected: 3 .py files in test data (src/a.py, src/b.py, src/sub/c.py)
        # Plus the script itself (count_py.py) = 4 if the model writes it in the same dir.
        # Excluded: __pycache__/cache.pyc, .git/config, .venv/lib.py
        # Accept either 3 or 4 — the script itself is a valid .py file under the root.
        assert (
            "py_files=3" in result.final_response or "py_files=4" in result.final_response
        ), f"Expected 'py_files=3' or 'py_files=4' in response, got: {result.final_response!r}"


@pytest.mark.llm_e2e
class TestTaskDecomposition:
    """LLM should break down multi-part requests into logical steps."""

    async def test_count_and_report(self, model_capability_client, e2e_timeout):
        """Ask for multiple pieces of information in one query."""
        qe = model_capability_client
        result: ToolRunResult = await asyncio.wait_for(
            run_with_tools(
                qe,
                (
                    "How many Python files are in src/pilotcode/tools? "
                    "Also, what is the first line of src/pilotcode/query_engine.py?"
                ),
                timeout=e2e_timeout,
                max_turns=12,
            ),
            timeout=e2e_timeout + 30,
        )

        tool_names = [tc.name for tc in result.tool_calls]

        # Should use Glob or Bash for counting
        assert "Glob" in tool_names or "Bash" in tool_names, (
            f"Should use Glob/Bash to count files, got: {tool_names}\n"
            f"Final response: {result.final_response!r}"
        )

        # Should use FileRead for the first line
        assert (
            "FileRead" in tool_names
        ), f"Should use FileRead to read query_engine.py, got: {tool_names}"

        # Should answer both parts
        assert (
            len(result.final_response) > 30
        ), f"Should answer both questions, got: {result.final_response!r}"
