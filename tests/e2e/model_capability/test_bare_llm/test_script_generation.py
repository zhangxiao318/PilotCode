"""Layer 1: Standalone Script Generation Capability.

Tests whether the bare LLM can generate complete, executable Python scripts
(not just isolated functions) that handle real-world concerns like:
- Proper imports and module usage
- Command-line entry points (if __name__ == "__main__")
- Error handling for edge cases (missing directories, permissions)
- File I/O and path operations
- Structured output formatting

Unlike test_code_generation.py (HumanEval-style function snippets),
these tests evaluate "script engineering" competence.

Failure attribution: llm_capability.
"""

from __future__ import annotations

import asyncio
import pytest
import subprocess
import tempfile
from pathlib import Path

from pilotcode.utils.model_client import Message

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _generate_script(model_client, prompt: str, timeout: float) -> str:
    """Ask the model to generate a complete Python script."""
    messages = [
        Message(
            role="user",
            content=(
                f"{prompt}\n\n"
                "Write a complete, self-contained Python script. "
                "Include necessary imports and a main execution block. "
                "Output only the code, no markdown fences, no explanations."
            ),
        ),
    ]
    chunks: list[str] = []
    async for chunk in model_client.chat_completion(messages, tools=None, stream=True):
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        content = delta.get("content")
        if content:
            chunks.append(content)
    return "".join(chunks)


def _extract_script(code_text: str) -> str:
    """Extract executable Python code from model response.

    Handles:
    - Markdown fences (```python ... ```)
    - <think>...</think> or standalone </think> reasoning blocks
    - Leading/trailing explanatory text
    - Indented code inside think blocks that becomes invalid when fences stripped

    Strategy: remove noise, then use Python's compile() to find the largest
    valid code block bounded by code-like start lines.
    """
    text = code_text

    # 1. Strip reasoning blocks.
    #    Some reasoning models emit </think> without a matching <think>.
    #    Strategy: if </think> exists, take only what follows it (the actual
    #    response).  If both tags exist, also strip full <think>...</think>.
    if "</think>" in text:
        text = text.split("</think>", 1)[-1]
    while "<think>" in text and "</think>" in text:
        start = text.find("<think>")
        end = text.find("</think>", start) + len("</think>")
        text = text[:start] + text[end:]

    # 2. Strip markdown fences
    lines = text.splitlines()
    result: list[str] = []
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            result.append(line)
    text = "\n".join(result).strip()

    # 3. Fallback: try direct fence removal
    if not text:
        text = code_text.strip()
        if text.startswith("```"):
            text = "\n".join(text.splitlines()[1:])
        if text.endswith("```"):
            text = "\n".join(text.splitlines()[:-1])
        text = text.strip()

    # 4. Use compile() to find the largest valid Python block.
    #    Try every line that looks like a code start, expand downward
    #    until compilation fails — that gives us the longest valid block.
    lines = text.splitlines()
    CODE_START_MARKERS = ("import ", "from ", "def ", "class ", "print(", "if __name__")
    candidates: list[tuple[int, str]] = []

    for start_idx in range(len(lines)):
        stripped = lines[start_idx].strip()
        if not stripped.startswith(CODE_START_MARKERS):
            continue
        for end_idx in range(len(lines), start_idx, -1):
            block = "\n".join(lines[start_idx:end_idx])
            try:
                compile(block, "<extracted>", "exec")
                candidates.append((end_idx - start_idx, block))
                break  # longest valid block from this start
            except SyntaxError:
                continue

    if candidates:
        # Pick the longest valid block
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1].strip()

    # Ultimate fallback: heuristic trimming from first code-like line
    code_lines: list[str] = []
    found_code = False
    for line in lines:
        stripped = line.strip()
        if not found_code:
            if stripped.startswith(CODE_START_MARKERS):
                found_code = True
            elif stripped == "":
                continue
            else:
                continue
        code_lines.append(line)

    if code_lines:
        return "\n".join(code_lines).strip()

    return text.strip()


def _run_script(script_code: str, cwd: Path | None = None) -> tuple[bool, str, str, int]:
    """Execute script in a temporary file and return (success, stdout, stderr, rc)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script_code)
        f.flush()
        script_path = f.name

    try:
        proc = subprocess.run(
            ["python3", script_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=cwd,
        )
        return proc.returncode == 0, proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        return False, "", "Script execution timed out after 30s", -1
    except Exception as e:
        return False, "", f"Execution error: {type(e).__name__}: {e}", -1
    finally:
        Path(script_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.llm_e2e
class TestStandaloneScriptGeneration:
    """LLM generates complete executable scripts and we verify by running them."""

    async def test_generate_standalone_script(self, bare_llm_client, e2e_timeout, tmp_path):
        """LLM generates a complete script to count files with a specific extension.

        Validates:
        - Proper imports (os, pathlib, etc.)
        - File enumeration logic
        - Structured output formatting
        """
        # Setup: create known files in temp directory
        (tmp_path / "a.txt").write_text("hello\n")
        (tmp_path / "b.txt").write_text("world\n")
        (tmp_path / "c.py").write_text("print(1)\n")

        prompt = (
            f"Write a Python script that counts the number of .txt files "
            f"in '{tmp_path}' and prints the result in the exact format: "
            "'txt_count=N' where N is the number."
        )

        raw_response = await asyncio.wait_for(
            _generate_script(bare_llm_client, prompt, e2e_timeout),
            timeout=e2e_timeout,
        )

        script_code = _extract_script(raw_response)
        assert script_code.strip(), (
            "Could not extract script from response. " f"Raw: {raw_response[:300]!r}"
        )

        success, stdout, stderr, rc = _run_script(script_code, cwd=tmp_path)
        assert success, (
            f"Script failed (rc={rc}).\nScript:\n{script_code}\n"
            f"stderr: {stderr}\nstdout: {stdout}"
        )

        assert "txt_count=2" in stdout, (
            f"Expected 'txt_count=2' in output, got stdout={stdout!r}, " f"stderr={stderr!r}"
        )

    async def test_generate_robust_script_with_error_handling(
        self, bare_llm_client, e2e_timeout, tmp_path
    ):
        """LLM generates a script that handles a non-existent directory gracefully.

        Validates:
        - Error handling (try/except or path.exists() check)
        - Graceful degradation instead of crashing
        - User-friendly error messages
        """
        nonexistent = tmp_path / "does_not_exist"

        prompt = (
            f"Write a Python script that counts .py files in '{nonexistent}'. "
            "If the directory does not exist, print exactly 'ERROR: directory not found' "
            "and exit with code 0. If it exists, print 'py_count=N'."
        )

        raw_response = await asyncio.wait_for(
            _generate_script(bare_llm_client, prompt, e2e_timeout),
            timeout=e2e_timeout,
        )

        script_code = _extract_script(raw_response)
        assert script_code.strip(), (
            "Could not extract script from response. " f"Raw: {raw_response[:300]!r}"
        )

        success, stdout, stderr, rc = _run_script(script_code, cwd=tmp_path)
        assert success, (
            f"Script failed (rc={rc}).\nScript:\n{script_code}\n"
            f"stderr: {stderr}\nstdout: {stdout}"
        )

        assert "ERROR: directory not found" in stdout, (
            f"Expected graceful error handling, got stdout={stdout!r}, " f"stderr={stderr!r}"
        )
