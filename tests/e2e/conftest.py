"""Shared pytest configuration for all E2E tests under tests/e2e/."""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-llm-e2e",
        action="store_true",
        default=False,
        help="Run LLM-backed E2E tests (requires LLM backend + optional web server)",
    )
    parser.addoption(
        "--e2e-timeout",
        action="store",
        type=float,
        default=120.0,
        help="Timeout per test step in seconds (default: 120)",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "llm_e2e: marks tests as LLM-backed E2E (deselect without --run-llm-e2e)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-llm-e2e"):
        for item in items:
            if "llm_e2e" in {m.name for m in item.own_markers}:
                item.add_marker(pytest.mark.slow)
        return

    skip_llm = pytest.mark.skip(
        reason="LLM E2E tests skipped by default. Use --run-llm-e2e to enable."
    )
    for item in items:
        if "llm_e2e" in {m.name for m in item.own_markers}:
            item.add_marker(skip_llm)
