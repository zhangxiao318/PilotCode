"""Pytest configuration for WebSocket LLM E2E tests.

These tests require:
1. A running PilotCode Web server (`python -m pilotcode --web`)
2. A configured LLM API key
3. The `--run-llm-e2e` flag to enable

Run with:
    python -m pilotcode --web --web-port 18080 &
    pytest tests/e2e/websocket/ --run-llm-e2e -v

Skip (default):
    pytest tests/e2e/websocket/ -v
    # All llm_e2e tests are skipped automatically
"""

import asyncio
import json
import os
import pytest
from pathlib import Path

# ---------------------------------------------------------------------------
# Custom CLI option
# ---------------------------------------------------------------------------


def pytest_addoption(parser):
    # --run-llm-e2e and --e2e-timeout are registered in tests/e2e/conftest.py
    parser.addoption(
        "--ws-url",
        action="store",
        default="ws://127.0.0.1:8081",
        help="WebSocket URL for the PilotCode web server (default: ws://127.0.0.1:8081, matching --web default)",
    )
    parser.addoption(
        "--ws-port",
        action="store",
        type=int,
        default=None,
        help="Override the WebSocket port (e.g. 18081). Shorthand for changing --ws-url port.",
    )
    parser.addoption(
        "--web-cwd",
        action="store",
        default=None,
        help="Working directory the web server should operate on (default: project root)",
    )


# ---------------------------------------------------------------------------
# Auto-skip marker
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Session fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def ws_url(pytestconfig) -> str:
    url = pytestconfig.getoption("--ws-url")
    port = pytestconfig.getoption("--ws-port")
    if port is not None:
        # Replace port in the URL, preserving scheme/host
        import urllib.parse

        parsed = urllib.parse.urlparse(url)
        # Rebuild netloc with new port
        host = parsed.hostname or "127.0.0.1"
        new_netloc = f"{host}:{port}"
        url = urllib.parse.urlunparse(parsed._replace(netloc=new_netloc))
    return url


@pytest.fixture(scope="session")
def e2e_timeout(pytestconfig) -> float:
    return pytestconfig.getoption("--e2e-timeout")


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).parent.parent.parent.parent


@pytest.fixture(scope="session")
def web_cwd(pytestconfig, project_root) -> Path:
    cwd = pytestconfig.getoption("--web-cwd")
    if cwd:
        return Path(cwd).resolve()
    return project_root


@pytest.fixture(scope="session")
def cases_dir() -> Path:
    return Path(__file__).parent / "cases"


# ---------------------------------------------------------------------------
# Temp directory for file I/O tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def e2e_temp_dir(project_root) -> Path:
    """Create a dedicated temp directory for E2E tool tests."""
    tmp = project_root / "tests" / "tmp" / "e2e_tool_behavior"
    tmp.mkdir(parents=True, exist_ok=True)
    yield tmp
    # Cleanup after all tests
    import shutil

    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# WebSocket client fixture (connection per test)
# ---------------------------------------------------------------------------


@pytest.fixture
async def ws_client(ws_url, e2e_timeout, request):
    """Create a connected WebSocket test client."""
    if not request.config.getoption("--run-llm-e2e"):
        pytest.skip("LLM E2E tests skipped by default. Use --run-llm-e2e to enable.")

    from .client import PilotCodeWebSocketClient

    client = PilotCodeWebSocketClient(ws_url, default_timeout=e2e_timeout)
    await client.connect()
    yield client
    await client.close()


@pytest.fixture
async def ws_client_with_session(ws_url, e2e_timeout, request):
    """Create a connected client with a fresh session."""
    if not request.config.getoption("--run-llm-e2e"):
        pytest.skip("LLM E2E tests skipped by default. Use --run-llm-e2e to enable.")

    from .client import PilotCodeWebSocketClient

    client = PilotCodeWebSocketClient(ws_url, default_timeout=e2e_timeout)
    await client.connect()
    session_id = await client.create_session()
    yield client
    await client.close()
