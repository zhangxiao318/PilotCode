# ClaudeDecode Test Framework

This directory contains an automated test framework for `PilotCode`. It uses **pytest** and includes a **Mock LLM client** so you can test full conversation + tool execution flows without hitting real APIs.

## Quick Start

```bash
# Run all tests
python run_tests.py

# Run with verbose output
python run_tests.py -v

# Run only fast tests (skip slow/network)
python run_tests.py --quick

# Run specific categories
python run_tests.py --tools
python run_tests.py --integration
python run_tests.py --commands
python run_tests.py --permissions

# Run with coverage
python run_tests.py --cov

# Run matching test names
python run_tests.py -k test_bash
```

## Test Structure

| File | Purpose |
|------|---------|
| `conftest.py` | Shared pytest fixtures (mock client, auto-allow permissions, temp dirs) |
| `mock_llm.py` | `MockModelClient` — simulates LLM responses and tool calls |
| `test_tools_comprehensive.py` | Unit tests for all tools (Bash, File*, Glob, Grep, Git, etc.) |
| `test_integration.py` | End-to-end conversation flows with mocked LLM |
| `test_commands.py` | Slash command parsing and execution tests |
| `test_permissions.py` | Permission manager and tool executor tests |

## Key Fixtures

### `mock_model_client`
Replaces the real HTTP LLM client with `MockModelClient`. All `QueryEngine` instances will automatically use it.

```python
async def test_hello(mock_model_client, query_engine_factory):
    mock_model_client.set_responses([
        MockLLMResponse.with_text("Hello!"),
    ])
    engine = query_engine_factory()
    ...
```

### `auto_allow_permissions`
Automatically grants all tool permissions, so tool execution never prompts.

### `query_engine_factory`
Creates fresh `QueryEngine` instances wired to the mock client.

## Mock LLM Patterns

### Simple text response
```python
mock_model_client.set_responses([
    MockLLMResponse.with_text("The answer is 42."),
])
```

### Single tool call
```python
mock_model_client.set_responses([
    MockLLMResponse.with_tool_call("Bash", {"command": "ls"}),
    MockLLMResponse.with_text("Here are the files."),
])
```

### Multiple tools in one turn
```python
mock_model_client.set_responses([
    MockLLMResponse(
        content="I'll help.",
        tool_calls=[
            {"id": "c1", "type": "function", "function": {"name": "Bash", "arguments": '{"command":"echo 1"}'}},
            {"id": "c2", "type": "function", "function": {"name": "Bash", "arguments": '{"command":"echo 2"}'}},
        ],
        finish_reason="tool_calls",
    ),
    MockLLMResponse.with_text("Done!"),
])
```

### Inspecting history
```python
# After the test runs
messages = mock_model_client.get_last_messages()
assert mock_model_client.call_count == 2
```

## Writing a New Integration Test

```python
import pytest
from tests.mock_llm import MockLLMResponse

class TestMyFeature:
    @pytest.mark.asyncio
    async def test_feature(self, mock_model_client, query_engine_factory, auto_allow_permissions):
        mock_model_client.set_responses([
            MockLLMResponse.with_tool_call("FileWrite", {"file_path": "/tmp/x.txt", "content": "hi"}),
            MockLLMResponse.with_text("File written."),
        ])

        engine = query_engine_factory(tools=get_all_tools())

        # First turn: capture tool call
        tool_msgs = []
        async for result in engine.submit_message("Write a file"):
            if isinstance(result.message, ToolUseMessage):
                tool_msgs.append(result.message)

        assert len(tool_msgs) == 1
        assert tool_msgs[0].name == "FileWrite"

        # Execute tool manually (or let REPL do it in higher-level tests)
        from pilotcode.permissions.tool_executor import ToolExecutor
        executor = ToolExecutor()
        res = await executor.execute_tool_by_name(tool_msgs[0].name, tool_msgs[0].input, ToolUseContext())
        assert res.success

        # Feed result back to engine
        engine.add_tool_result(tool_msgs[0].tool_use_id, str(res.result.data))

        # Second turn: LLM final response
        async for result in engine.submit_message("Continue"):
            if isinstance(result.message, AssistantMessage) and result.is_complete:
                assert "written" in result.message.content.lower()
```

## Running Tests Directly with pytest

```bash
PYTHONPATH=src python -m pytest tests/ -v
PYTHONPATH=src python -m pytest tests/test_integration.py -v
PYTHONPATH=src python -m pytest tests/ -k "test_bash" -v
```

## Notes

- Web tests (`test_web_search`, `test_web_fetch`) are skipped by default because they require network. Run them explicitly with `python run_tests.py --run-web-tests` or remove the `@pytest.mark.skip` decorator.
- The legacy `src/tests/test_tools.py` is preserved but not run by default due to a module naming conflict with the root `tests/` directory.
