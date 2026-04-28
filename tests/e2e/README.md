# E2E Tests

PilotCode end-to-end tests cover the full chain: LLM inference, tool execution, WebSocket communication, and session management.

For full documentation, see:
- [E2E Testing Guide](../../docs/guides/e2e-testing.md) — Three-layer diagnostic framework, test structure, and how to add new tests.

## Quick Run

```bash
# Skip LLM tests (fast regression)
pytest tests/e2e/ -v

# Run with LLM (requires backend API)
pytest tests/e2e/ --run-llm-e2e -v

# Layer 1 only — bare LLM capability, zero framework dependency
pytest tests/e2e/model_capability/test_bare_llm/ --run-llm-e2e -v

# Layer 2 only — LLM + tool execution
pytest tests/e2e/model_capability/test_tool_capability/ --run-llm-e2e -v

# Layer 3 only — full WebSocket E2E (requires server on :8081)
pytest tests/e2e/websocket/ --run-llm-e2e -v
```

## Three-Layer Diagnostics

| Layer | Scope | Identifies |
|-------|-------|-----------|
| 1 | Bare LLM | LLM base capability weakness |
| 2 | LLM + Tools | Function calling or tool implementation issues |
| 3 | Full E2E | Framework issues (LoopGuard, timeout, context compression) |

See the [full guide](../../docs/guides/e2e-testing.md) for details.
