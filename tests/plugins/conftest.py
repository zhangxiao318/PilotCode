"""Fixtures for plugin system tests."""

import json
import tempfile
from pathlib import Path

import pytest

# Skip if plugins not available
try:
    from pilotcode.plugins.core.config import PluginConfig
    from pilotcode.plugins.core.types import (
        PluginManifest,
        MarketplaceSource,
        PluginScope,
        SkillDefinition,
        PluginMarketplace,
        PluginMarketplaceEntry,
    )
    PLUGINS_AVAILABLE = True
except ImportError:
    PLUGINS_AVAILABLE = False


@pytest.fixture
def temp_config_dir():
    """Create a temporary config directory."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def plugin_config(temp_config_dir):
    """Create a PluginConfig with temp directory."""
    if not PLUGINS_AVAILABLE:
        pytest.skip("Plugin system not available")
    return PluginConfig(config_dir=temp_config_dir)


@pytest.fixture
def sample_manifest():
    """Create a sample plugin manifest."""
    return PluginManifest(
        name="test-plugin",
        version="1.0.0",
        description="A test plugin",
        author={"name": "Test Author", "email": "test@example.com"},
        license="MIT",
        keywords=["test", "example"],
        dependencies=[],
    )


@pytest.fixture
def sample_marketplace():
    """Create a sample marketplace."""
    return PluginMarketplace(
        name="test-marketplace",
        description="Test marketplace",
        version="1.0.0",
        plugins=[
            PluginMarketplaceEntry(
                name="test-plugin",
                description="Test plugin",
                version="1.0.0",
                source={"source": "github", "repo": "test/plugin"},
            )
        ],
    )


@pytest.fixture
def create_test_plugin(temp_config_dir):
    """Factory fixture to create test plugins."""
    def _create(name: str, version: str = "1.0.0", with_skills: bool = True):
        plugin_dir = temp_config_dir / "test_plugins" / name
        plugin_dir.mkdir(parents=True, exist_ok=True)
        
        # Create plugin.json
        manifest = {
            "name": name,
            "version": version,
            "description": f"Test plugin: {name}",
        }
        with open(plugin_dir / "plugin.json", "w") as f:
            json.dump(manifest, f, indent=2)
        
        # Create skills if requested
        if with_skills:
            skills_dir = plugin_dir / "skills"
            skills_dir.mkdir(exist_ok=True)
            
            skill_content = """---
name: test-skill
description: A test skill
---

This is a test skill content.
"""
            with open(skills_dir / "test.md", "w") as f:
                f.write(skill_content)
        
        return plugin_dir
    
    return _create


@pytest.fixture
def github_source():
    """Create a GitHub marketplace source."""
    return MarketplaceSource(
        source="github",
        repo="anthropics/claude-plugins-official",
    )


@pytest.fixture
def mock_github_response():
    """Mock response for GitHub API calls."""
    return {
        "sha": "abc123def456",
        "commit": {
            "message": "Update plugins",
            "author": {"name": "Test", "email": "test@example.com"},
        },
    }


@pytest.fixture
def sample_skill_content():
    """Sample skill markdown content."""
    return """---
name: code-review
description: Review code for issues
aliases: [review, cr]
allowedTools: [Read, Grep, Bash]
---

Please review the code at {path} for:
1. Code quality issues
2. Security vulnerabilities
3. Performance problems

Path: {path}
"""


@pytest.fixture
def sample_hooks_config():
    """Sample hooks configuration."""
    return {
        "preToolUse": [
            {"command": "echo 'Pre-tool hook'"}
        ],
        "postToolUse": [
            {"command": "echo 'Post-tool hook'"}
        ],
    }


@pytest.fixture
def mock_lsp_config():
    """Sample LSP server configuration."""
    return {
        "command": "typescript-language-server",
        "args": ["--stdio"],
        "extensionToLanguage": {
            ".ts": "typescript",
            ".tsx": "typescript",
        },
    }


@pytest.fixture
def sample_policy():
    """Sample policy configuration."""
    return {
        "name": "test-policy",
        "version": "1.0",
        "description": "Test policy",
        "allowed_marketplaces": ["claude-plugins-official"],
        "require_signatures": False,
        "audit_all_installs": True,
    }


@pytest.fixture
def sample_signature_data():
    """Sample signature data."""
    return {
        "plugin_name": "test-plugin",
        "plugin_version": "1.0.0",
        "hash_algorithm": "sha256",
        "content_hash": "abc123...",
        "signer": "test-signer",
        "timestamp": "2024-01-01T00:00:00",
        "signature": "base64encoded...",
    }


# Async fixtures
@pytest.fixture
async def async_temp_dir():
    """Async fixture for temp directory."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


# Markers for test categories
pytest.mark.unit = pytest.mark.unit
pytest.mark.integration = pytest.mark.integration
pytest.mark.slow = pytest.mark.slow
