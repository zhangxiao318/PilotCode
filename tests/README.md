# PilotCode Test Suite

This directory contains the comprehensive test suite for PilotCode.

## Structure

```
tests/
├── conftest.py              # Shared pytest fixtures and configuration
├── README.md                # This file
├── unit/                    # Unit tests
│   ├── tools/               # Tool-specific tests
│   │   ├── test_bash.py
│   │   ├── test_file_tools.py
│   │   ├── test_git.py
│   │   └── ...
│   ├── core/                # Core functionality tests
│   │   ├── test_query_engine.py
│   │   └── ...
│   └── services/            # Service tests
│       ├── test_permissions.py
│       └── ...
├── integration/             # Integration tests
│   └── ...
├── e2e/                     # End-to-end tests
│   └── ...
└── fixtures/                # Test fixtures
    ├── files/               # Sample files
    └── repos/               # Sample git repos
```

## Running Tests

### Run all tests
```bash
make test
# or
pytest tests/
```

### Run specific test categories

```bash
# Unit tests only (fast)
make test-unit
pytest tests/unit -v

# Integration tests
make test-integration
pytest tests/integration -v

# Tool tests
make test-tools
pytest tests/unit/tools -v

# E2E tests
make test-e2e
pytest tests/e2e -v
```

### Run tests with markers

```bash
# Exclude slow tests
pytest tests/ -m "not slow"

# Run only network tests
pytest tests/ -m "network"

# Run only tests that don't require network
pytest tests/ -m "not network"
```

### Run tests with coverage

```bash
make test-cov
# Generates HTML report at htmlcov/index.html
```

## Test Categories

### Markers

- `@pytest.mark.unit` - Unit tests (fast, isolated)
- `@pytest.mark.integration` - Integration tests (may use real services)
- `@pytest.mark.e2e` - End-to-end tests (full workflows)
- `@pytest.mark.network` - Tests requiring network access
- `@pytest.mark.slow` - Slow tests (> 1 second)
- `@pytest.mark.tui` - Tests requiring TUI/display

## Writing Tests

### Basic Test Structure

```python
import pytest
from tests.conftest import run_tool_test

class TestMyTool:
    """Tests for MyTool."""
    
    @pytest.mark.asyncio
    async def test_basic_functionality(self, tool_context, allow_callback):
        """Test basic tool functionality."""
        result = await run_tool_test(
            "MyTool",
            {"param": "value"},
            tool_context,
            allow_callback
        )
        
        assert not result.is_error
        assert result.data.expected_field == "expected_value"
```

### Available Fixtures

- `temp_dir` - Temporary directory (auto-cleaned)
- `temp_git_repo` - Temporary git repository
- `app_store` - Fresh app store instance
- `tool_context` - Tool execution context
- `allow_callback` - Permission callback that allows all
- `deny_callback` - Permission callback that denies all
- `sample_python_file` - Sample Python file
- `sample_json_file` - Sample JSON file

### Best Practices

1. **Use fixtures** - Don't create test data manually
2. **Test one thing** - Each test should verify one concept
3. **Clear naming** - Test names should describe what's being tested
4. **Async tests** - Use `@pytest.mark.asyncio` for async tests
5. **Clean up** - Use `temp_dir` for file operations
6. **Mock external** - Mock LLM calls and network requests

## CI/CD

Tests are run automatically on:
- Every push to main/master/develop branches
- Every pull request
- Tagged releases

See `.github/workflows/test.yml` for details.
