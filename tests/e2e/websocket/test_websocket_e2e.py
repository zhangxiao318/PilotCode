"""LLM-backed WebSocket end-to-end tests for PilotCode.

These tests validate session-level multi-turn conversation capabilities
by connecting to a live PilotCode Web server and exercising real LLM
inference + tool use.

Run:
    # Start the web server first
    python -m pilotcode --web --web-port 18080 --cwd .

    # Run E2E tests
    pytest tests/e2e/websocket/ --run-llm-e2e -v

    # Run only simple tasks
    pytest tests/e2e/websocket/ --run-llm-e2e -v -k simple

    # Run with custom timeout
    pytest tests/e2e/websocket/ --run-llm-e2e --e2e-timeout 180 -v

Skip (default):
    pytest tests/e2e/websocket/ -v
    # All tests show as skipped
"""

from __future__ import annotations

import asyncio
import json
import pytest
import sys
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .client import PilotCodeWebSocketClient, QueryResult

# ============================================================================
# Test case loader
# ============================================================================


@dataclass
class E2eStep:
    """A single step in a test case."""

    send: str = ""
    expect: dict = field(default_factory=dict)
    action: str = ""  # "create", "disconnect_and_reconnect", etc.
    session: str = ""


@dataclass
class E2eCase:
    """A complete test case with multiple steps."""

    id: str
    name: str
    description: str
    steps: list[E2eStep]
    session_mode: str = ""  # "", "multi", "reconnect"
    platforms: list[str] = field(default_factory=lambda: ["all"])
    setup: str = ""  # "", "init_git_repo", etc.


def load_test_cases(cases_dir: Path, suite_name: str) -> list[E2eCase]:
    """Load test cases from a JSON file."""
    file_path = cases_dir / f"{suite_name}.json"
    if not file_path.exists():
        return []

    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    cases = []
    for case_data in data.get("cases", []):
        steps = []
        for step_data in case_data.get("steps", []):
            steps.append(
                E2eStep(
                    send=step_data.get("send", ""),
                    expect=step_data.get("expect", {}),
                    action=step_data.get("action", ""),
                    session=step_data.get("session", ""),
                )
            )
        cases.append(
            E2eCase(
                id=case_data["id"],
                name=case_data["name"],
                description=case_data["description"],
                steps=steps,
                session_mode=case_data.get("session_mode", ""),
                platforms=case_data.get("platforms", ["all"]),
                setup=case_data.get("setup", ""),
            )
        )
    return cases


# ============================================================================
# Verification helpers
# ============================================================================


def verify_result(result: QueryResult, expect: dict, step_index: int) -> list[str]:
    """Verify a query result against expectations.

    Returns a list of error messages (empty if all pass).
    Hard assertions: success, tool_calls, not_tool_calls, not_contains, length.
    Soft warnings: contains (logged but does not fail the test).
    """
    import warnings

    errors = []
    text = result.response

    # Success check
    if not result.success:
        errors.append(f"Step {step_index}: Query failed: {result.error}")
        return errors

    # Content contains — SOFT check: warn but do not fail
    for keyword in expect.get("contains", []):
        if keyword.lower() not in text.lower():
            warnings.warn(
                f"[Step {step_index}] Response missing expected content: '{keyword}'. "
                f"Actual response starts with: {text[:80]!r}",
                UserWarning,
                stacklevel=2,
            )

    # Content excludes — HARD check
    for keyword in expect.get("not_contains", []):
        if keyword.lower() in text.lower():
            errors.append(f"Step {step_index}: Response should NOT contain '{keyword}'")

    # Tool calls required — HARD check
    for tool in expect.get("tool_calls", []):
        if tool not in result.tool_calls:
            errors.append(
                f"Step {step_index}: Expected tool '{tool}' to be called, got: {result.tool_calls}"
            )

    # Tool calls excluded — HARD check
    for tool in expect.get("not_tool_calls", []):
        if tool in result.tool_calls:
            errors.append(f"Step {step_index}: Tool '{tool}' should NOT have been called")

    # Response length — HARD check
    min_len = expect.get("response_min_length", 0)
    if min_len > 0 and len(text) < min_len:
        errors.append(f"Step {step_index}: Response too short ({len(text)} < {min_len} chars)")

    max_len = expect.get("response_max_length", 0)
    if max_len > 0 and len(text) > max_len:
        errors.append(f"Step {step_index}: Response too long ({len(text)} > {max_len} chars)")

    return errors


# ============================================================================
# Test executor
# ============================================================================


def _should_run_on_platform(case: E2eCase) -> bool:
    """Check if case should run on current platform."""
    if "all" in case.platforms:
        return True
    return sys.platform in case.platforms


def _init_git_repo(repo_path: Path) -> None:
    """Initialize a temporary git repo for testing."""
    import shutil

    if repo_path.exists():
        shutil.rmtree(repo_path)
    repo_path.mkdir(parents=True, exist_ok=True)
    (repo_path / "README.md").write_text("# Temp Repo\n")
    subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "e2e@test.com"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "E2E Tester"], cwd=repo_path, capture_output=True, check=True
    )
    subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"], cwd=repo_path, capture_output=True, check=True
    )


def _substitute_tmp(text: str, tmp_dir: Path) -> str:
    """Replace {{TMP}} placeholder with actual temp directory path."""
    return text.replace("{{TMP}}", str(tmp_dir))


async def run_test_case(
    client: PilotCodeWebSocketClient,
    case: E2eCase,
    timeout: float,
    tmp_dir: Path | None = None,
) -> list[str]:
    """Execute a test case and return any errors."""
    # Platform filter
    if not _should_run_on_platform(case):
        return [f"Skipped: platform {sys.platform} not in {case.platforms}"]

    errors = []
    sessions: dict[str, str] = {}  # local session name -> server session_id

    # Run setup if needed
    if case.setup == "init_git_repo" and tmp_dir:
        repo = tmp_dir / "git_test_repo"
        _init_git_repo(repo)

    for i, step in enumerate(case.steps):
        try:
            # Handle special actions
            if step.action == "create":
                sid = await client.create_session()
                sessions[step.session] = sid
                continue

            if step.action == "disconnect_and_reconnect":
                current_sid = client.session_id
                await client.close()
                await asyncio.sleep(0.5)
                await client.connect()
                # Re-attach to the same session
                attach_sid = (
                    current_sid if step.session == "_use_current" else sessions.get(step.session)
                )
                if attach_sid:
                    await client.attach_session(attach_sid)
                continue

            # Determine which session to use
            if step.session:
                if step.session in sessions:
                    client.session_id = sessions[step.session]
                # If session not in local map, assume it's a direct session_id

            # Normal query step
            if not step.send:
                continue

            # Substitute temp directory placeholder
            send_text = step.send
            if tmp_dir:
                send_text = _substitute_tmp(send_text, tmp_dir)

            result = await client.query(send_text, timeout=timeout)
            step_errors = verify_result(result, step.expect, i + 1)
            errors.extend(step_errors)

        except Exception as e:
            errors.append(f"Step {i + 1}: Exception: {type(e).__name__}: {e}")

    return errors


# ============================================================================
# Pytest tests
# ============================================================================


@pytest.mark.llm_e2e
class TestWebSocketSimpleTasks:
    """Simple task E2E tests."""

    @pytest.fixture(scope="class")
    def simple_cases(self, cases_dir) -> list[E2eCase]:
        return load_test_cases(cases_dir, "simple_tasks")

    @pytest.mark.parametrize(
        "case",
        [
            pytest.param(c, id=c.id)
            for c in load_test_cases(Path(__file__).parent / "cases", "simple_tasks")
        ],
    )
    @pytest.mark.asyncio
    async def test_simple_task(self, ws_client_with_session, case, e2e_timeout, e2e_temp_dir):
        """Run a simple task test case."""
        errors = await run_test_case(
            ws_client_with_session, case, e2e_timeout, tmp_dir=e2e_temp_dir
        )
        assert not errors, "\n".join(errors)


@pytest.mark.llm_e2e
class TestWebSocketComplexTasks:
    """Complex task E2E tests."""

    @pytest.fixture(scope="class")
    def complex_cases(self, cases_dir) -> list[E2eCase]:
        return load_test_cases(cases_dir, "complex_tasks")

    @pytest.mark.parametrize(
        "case",
        [
            pytest.param(c, id=c.id)
            for c in load_test_cases(Path(__file__).parent / "cases", "complex_tasks")
        ],
    )
    @pytest.mark.asyncio
    async def test_complex_task(self, ws_client_with_session, case, e2e_timeout, e2e_temp_dir):
        """Run a complex task test case."""
        errors = await run_test_case(
            ws_client_with_session, case, e2e_timeout, tmp_dir=e2e_temp_dir
        )
        assert not errors, "\n".join(errors)


@pytest.mark.llm_e2e
class TestWebSocketSessionManagement:
    """Session lifecycle and isolation tests."""

    @pytest.mark.asyncio
    async def test_session_create_and_attach(self, ws_client, e2e_timeout):
        """Test creating a session and re-attaching to it."""
        # Create session
        sid1 = await ws_client.create_session()
        assert sid1.startswith("sess_")

        # Query to establish context
        result = await ws_client.query(
            "记住：我们的测试会话ID是 " + sid1,
            timeout=e2e_timeout,
        )
        assert result.success

        # Create a second session
        sid2 = await ws_client.create_session()
        assert sid2 != sid1

        result2 = await ws_client.query(
            "记住：这是第二个会话",
            timeout=e2e_timeout,
        )
        assert result2.success

        # Switch back to first session
        info = await ws_client.attach_session(sid1)
        assert info.session_id == sid1

        result3 = await ws_client.query(
            "我们当前的会话ID是什么？",
            timeout=e2e_timeout,
        )
        assert result3.success
        assert sid1 in result3.response

    @pytest.mark.asyncio
    async def test_session_list_and_save(self, ws_client, e2e_timeout):
        """Test listing and saving sessions."""
        # Create a session
        sid = await ws_client.create_session()

        # List sessions
        sessions = await ws_client.list_sessions()
        session_ids = [s["session_id"] for s in sessions]
        assert sid in session_ids

        # Save session
        saved = await ws_client.save_session(name="test_save_session")
        assert saved

    @pytest.mark.asyncio
    async def test_session_isolation(self, ws_client, e2e_timeout):
        """Verify two sessions do not share context."""
        # Session A
        sid_a = await ws_client.create_session()
        r1 = await ws_client.query("记住：会话A的秘密是 apple", timeout=e2e_timeout)
        assert r1.success

        # Session B
        sid_b = await ws_client.create_session()
        r2 = await ws_client.query("记住：会话B的秘密是 banana", timeout=e2e_timeout)
        assert r2.success

        # Back to A
        await ws_client.attach_session(sid_a)
        r3 = await ws_client.query(
            "我们的秘密是什么？只回答秘密，不要多余的话。", timeout=e2e_timeout
        )
        assert r3.success
        assert "apple" in r3.response.lower()
        assert "banana" not in r3.response.lower()

        # Back to B
        await ws_client.attach_session(sid_b)
        r4 = await ws_client.query(
            "我们的秘密是什么？只回答秘密，不要多余的话。", timeout=e2e_timeout
        )
        assert r4.success
        assert "banana" in r4.response.lower()
        assert "apple" not in r4.response.lower()


@pytest.mark.llm_e2e
class TestWebSocketContextRetention:
    """Tests specifically targeting context retention across turns."""

    @pytest.mark.asyncio
    async def test_three_turn_file_analysis(self, ws_client_with_session, e2e_timeout):
        """Three-turn analysis: find -> read -> summarize without re-reading."""
        client = ws_client_with_session

        # Turn 1: Find the file
        r1 = await client.query(
            "用 Glob 查找 src/pilotcode/tools/base.py",
            timeout=e2e_timeout,
        )
        assert r1.success
        assert "Glob" in r1.tool_calls or "glob" in r1.response.lower()

        # Turn 2: Read it
        r2 = await client.query(
            "读取这个文件的前50行",
            timeout=e2e_timeout,
        )
        assert r2.success
        assert "FileRead" in r2.tool_calls

        # Turn 3: Ask about it (should NOT re-read)
        r3 = await client.query(
            "基于你读到的内容，Tool类有哪些核心字段？不要重新读取文件。",
            timeout=e2e_timeout,
        )
        assert r3.success
        assert "FileRead" not in r3.tool_calls
        assert len(r3.response) > 50

    @pytest.mark.asyncio
    async def test_context_after_compaction(self, ws_client_with_session, e2e_timeout):
        """Verify early-turn context survives after multiple subsequent turns."""
        client = ws_client_with_session

        # Establish a fact in turn 1
        r1 = await client.query(
            "读取 README.md 的第一行。记住这一行内容。",
            timeout=e2e_timeout,
        )
        assert r1.success
        # Turns 2-4: Consume context with other queries
        for _ in range(3):
            r = await client.query(
                "读取 src/pilotcode/query_engine.py 的前20行，告诉我它导入了哪些模块。",
                timeout=e2e_timeout,
            )
            assert r.success

        # Turn 5: Ask about turn 1
        r5 = await client.query(
            "最开始我让你读的是哪个文件？它的第一行内容是什么？不要重新读取。",
            timeout=e2e_timeout,
        )
        assert r5.success
        assert "FileRead" not in r5.tool_calls
        assert "README" in r5.response or "readme" in r5.response.lower()


@pytest.mark.llm_e2e
class TestToolBehavior:
    """E2E tests for individual tool behaviors across platforms."""

    @pytest.mark.parametrize(
        "case",
        [
            pytest.param(c, id=c.id)
            for c in load_test_cases(Path(__file__).parent / "cases", "tool_behavior")
        ],
    )
    @pytest.mark.asyncio
    async def test_tool(self, ws_client_with_session, case, e2e_timeout, e2e_temp_dir):
        """Run a tool behavior test case."""
        errors = await run_test_case(
            ws_client_with_session, case, e2e_timeout, tmp_dir=e2e_temp_dir
        )
        # Platform-skipped cases report as a single skip message
        if errors and errors[0].startswith("Skipped:"):
            pytest.skip(errors[0])
        assert not errors, "\n".join(errors)
