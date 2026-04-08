# Plugin System Tests

This directory contains comprehensive tests for the PilotCode plugin system.

## Test Organization

```
tests/plugins/
├── conftest.py              # Shared fixtures and configuration
├── README.md                # This file
├── unit/                    # Unit tests
│   ├── test_core_types.py   # Core type definitions
│   ├── test_config.py       # Configuration management
│   ├── test_loader_skills.py # Skill loader tests
│   ├── test_hooks.py        # Hook system tests
│   ├── test_dependencies.py # Dependency resolution tests
│   ├── test_versioning.py   # Version management tests
│   ├── test_security.py     # Security and signature tests
│   ├── test_policy.py       # Policy and audit tests
│   └── test_lsp.py          # LSP support tests
└── integration/             # Integration tests
    └── test_plugin_lifecycle.py # Full lifecycle tests
```

## Running Tests

### Run all plugin tests
```bash
cd /home/zx/mycc/PilotCode
PYTHONPATH=src python3 -m pytest tests/plugins/ -v
```

### Run only unit tests
```bash
PYTHONPATH=src python3 -m pytest tests/plugins/unit/ -v -m unit
```

### Run only integration tests
```bash
PYTHONPATH=src python3 -m pytest tests/plugins/integration/ -v -m integration
```

### Run with coverage
```bash
PYTHONPATH=src python3 -m pytest tests/plugins/ -v --cov=pilotcode.plugins
```

### Run specific test file
```bash
PYTHONPATH=src python3 -m pytest tests/plugins/unit/test_hooks.py -v
```

## Test Markers

- `@pytest.mark.unit` - Fast unit tests (no external dependencies)
- `@pytest.mark.integration` - Integration tests (may use temp files)
- `@pytest.mark.slow` - Slow tests (comprehensive scenarios)

## Fixtures

Common fixtures available in `conftest.py`:

- `temp_config_dir` - Temporary configuration directory
- `plugin_config` - PluginConfig instance with temp directory
- `sample_manifest` - Sample PluginManifest
- `sample_marketplace` - Sample PluginMarketplace
- `create_test_plugin` - Factory to create test plugins
- `github_source` - Sample GitHub marketplace source

## Writing New Tests

### Unit Test Example

```python
import pytest
from pilotcode.plugins.core.types import PluginManifest

pytestmark = [pytest.mark.unit]

class TestMyFeature:
    def test_something(self):
        manifest = PluginManifest(name="test")
        assert manifest.name == "test"
```

### Integration Test Example

```python
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

class TestMyIntegration:
    async def test_full_flow(self, plugin_config):
        # Use fixtures
        assert plugin_config.plugins_dir.exists()
```

## Coverage Goals

- Core types: 100%
- Configuration: 100%
- Loader: 100%
- Hooks: 95%
- Dependencies: 90%
- Security: 90%
- Policy: 90%
- LSP: 80%
- Integration: 80%
