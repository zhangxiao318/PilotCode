"""Shared fixtures for model capability assessment tests.

Provides three-layer evaluation fixtures:
- bare_llm_client: Layer 1 -- direct model_client, no tools, no QueryEngine
- model_capability_client: Layer 2 -- QueryEngine with full tool execution loop
"""

import pytest
from pathlib import Path

# --run-llm-e2e and --e2e-timeout are registered in tests/e2e/conftest.py


@pytest.fixture(scope="session")
def e2e_timeout(request) -> float:
    return request.config.getoption("--e2e-timeout")


# ---------------------------------------------------------------------------
# Layer 1: Bare LLM (direct model client, no tools)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def bare_llm_client(request):
    """Create a direct ModelClient for bare-LLM capability testing (Layer 1)."""
    if not request.config.getoption("--run-llm-e2e"):
        pytest.skip("--run-llm-e2e not enabled")

    from pilotcode.utils.model_client import get_model_client

    return get_model_client()


# ---------------------------------------------------------------------------
# Layer 2: QueryEngine with tools (but no automatic execution -- tests use
# engine_helper.run_with_tools() for full loop)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def model_capability_client(request):
    """Create a standalone QueryEngine for capability testing (Layer 2).

    Tests should use engine_helper.run_with_tools() to execute the full
    submit_message -> tool execution -> add_tool_result loop.
    """
    if not request.config.getoption("--run-llm-e2e"):
        pytest.skip("--run-llm-e2e not enabled")

    from pilotcode.query_engine import QueryEngine, QueryEngineConfig
    from pilotcode.tools.registry import get_all_tools
    from pilotcode.state.app_state import get_default_app_state
    from pilotcode.state.store import Store
    from pilotcode.utils.config import get_global_config

    store = Store(get_default_app_state())
    tools = get_all_tools()
    global_cfg = get_global_config()

    query_engine = QueryEngine(
        QueryEngineConfig(
            cwd=str(Path.cwd()),
            tools=tools,
            get_app_state=store.get_state,
            set_app_state=lambda f: store.set_state(f),
            on_notify=lambda et, pl: None,
            auto_review=global_cfg.auto_review,
            max_review_iterations=global_cfg.max_review_iterations,
        )
    )

    return query_engine
