"""Unit tests for core plugin types."""

import pytest
from pydantic import ValidationError

try:
    from pilotcode.plugins.core.types import (
        PluginManifest,
        PluginAuthor,
        MarketplaceSource,
        PluginScope,
        SkillDefinition,
        HooksConfig,
        MCPServerConfig,
        PluginMarketplace,
        PluginMarketplaceEntry,
    )

    PLUGINS_AVAILABLE = True
except ImportError:
    PLUGINS_AVAILABLE = False

pytestmark = [
    pytest.mark.plugin,
    pytest.mark.plugin_unit,
    pytest.mark.unit,
    pytest.mark.skipif(not PLUGINS_AVAILABLE, reason="Plugin system not available"),
]


class TestPluginManifest:
    """Test PluginManifest model."""

    def test_create_minimal_manifest(self):
        """Test creating minimal manifest."""
        manifest = PluginManifest(name="test-plugin")
        assert manifest.name == "test-plugin"
        assert manifest.version == "1.0.0"  # Default
        assert manifest.description == ""

    def test_create_full_manifest(self):
        """Test creating full manifest."""
        manifest = PluginManifest(
            name="full-plugin",
            version="2.0.0",
            description="A full plugin",
            author=PluginAuthor(name="Test", email="test@example.com"),
            license="MIT",
            keywords=["test", "plugin"],
            dependencies=["other-plugin"],
        )
        assert manifest.name == "full-plugin"
        assert manifest.version == "2.0.0"
        assert manifest.author.name == "Test"
        assert manifest.keywords == ["test", "plugin"]

    def test_name_validation_no_spaces(self):
        """Test that names with spaces are rejected."""
        with pytest.raises(ValidationError):
            PluginManifest(name="invalid name")

    def test_to_dict(self):
        """Test conversion to dict."""
        manifest = PluginManifest(name="test", version="1.0.0")
        data = manifest.model_dump()
        assert data["name"] == "test"
        assert data["version"] == "1.0.0"


class TestMarketplaceSource:
    """Test MarketplaceSource model."""

    def test_github_source(self):
        """Test GitHub source creation."""
        source = MarketplaceSource(
            source="github",
            repo="owner/repo",
            ref="main",
        )
        assert source.source == "github"
        assert source.repo == "owner/repo"
        assert source.ref == "main"

    def test_github_source_requires_repo(self):
        """Test GitHub source requires repo field."""
        # Validation should raise at construction time
        with pytest.raises(ValueError):
            MarketplaceSource(source="github")

    def test_url_source(self):
        """Test URL source creation."""
        source = MarketplaceSource(
            source="url",
            url="https://example.com/marketplace.json",
        )
        assert source.source == "url"
        assert source.url == "https://example.com/marketplace.json"

    def test_file_source(self):
        """Test file source creation."""
        source = MarketplaceSource(
            source="file",
            file_path="/path/to/marketplace.json",
        )
        assert source.source == "file"
        assert source.file_path == "/path/to/marketplace.json"


class TestSkillDefinition:
    """Test SkillDefinition model."""

    def test_create_skill(self):
        """Test creating skill definition."""
        skill = SkillDefinition(
            name="test-skill",
            description="A test skill",
            aliases=["ts", "test"],
            allowed_tools=["Read", "Grep"],
            content="Test content",
        )
        assert skill.name == "test-skill"
        assert skill.aliases == ["ts", "test"]
        assert skill.allowed_tools == ["Read", "Grep"]

    def test_default_values(self):
        """Test skill default values."""
        skill = SkillDefinition(name="test", description="Test")
        assert skill.aliases == []
        assert skill.allowed_tools == []
        assert skill.content == ""


class TestPluginScope:
    """Test PluginScope enum."""

    def test_scope_values(self):
        """Test scope enum values."""
        assert PluginScope.USER.value == "user"
        assert PluginScope.PROJECT.value == "project"
        assert PluginScope.LOCAL.value == "local"

    def test_scope_comparison(self):
        """Test scope comparison."""
        assert PluginScope.USER == PluginScope.USER
        assert PluginScope.USER != PluginScope.PROJECT


class TestHooksConfig:
    """Test HooksConfig model."""

    def test_create_hooks(self):
        """Test creating hooks config."""
        hooks = HooksConfig(
            pre_tool_use=["hook1.sh", "hook2.sh"],
            post_tool_use=["post-hook.sh"],
        )
        assert hooks.pre_tool_use == ["hook1.sh", "hook2.sh"]
        assert hooks.post_tool_use == ["post-hook.sh"]

    def test_default_hooks(self):
        """Test default empty hooks."""
        hooks = HooksConfig()
        assert hooks.pre_tool_use == []
        assert hooks.post_tool_use == []
        assert hooks.session_start == []


class TestMCPServerConfig:
    """Test MCPServerConfig model."""

    def test_create_config(self):
        """Test creating MCP config."""
        config = MCPServerConfig(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-example"],
            env={"KEY": "value"},
            enabled=True,
        )
        assert config.command == "npx"
        assert config.args == ["-y", "@modelcontextprotocol/server-example"]
        assert config.env == {"KEY": "value"}
        assert config.enabled is True

    def test_default_values(self):
        """Test MCP config defaults."""
        config = MCPServerConfig(command="test")
        assert config.args == []
        assert config.env == {}
        assert config.enabled is True


class TestPluginMarketplace:
    """Test PluginMarketplace model."""

    def test_create_marketplace(self):
        """Test creating marketplace."""
        marketplace = PluginMarketplace(
            name="test-marketplace",
            description="Test marketplace",
            version="1.0.0",
        )
        assert marketplace.name == "test-marketplace"
        assert marketplace.plugins == []

    def test_marketplace_with_plugins(self):
        """Test marketplace with plugins."""
        entry = PluginMarketplaceEntry(
            name="test-plugin",
            description="Test plugin",
            version="1.0.0",
            source="github:test/plugin",
        )
        marketplace = PluginMarketplace(
            name="test",
            plugins=[entry],
        )
        assert len(marketplace.plugins) == 1
        assert marketplace.plugins[0].name == "test-plugin"


class TestKnownMarketplace:
    """Test KnownMarketplace model."""

    def test_create_known_marketplace(self):
        """Test creating known marketplace entry."""
        from pilotcode.plugins.core.types import KnownMarketplace

        source = MarketplaceSource(source="github", repo="test/repo")
        km = KnownMarketplace(
            source=source,
            install_location="marketplaces/test",
            last_updated="2024-01-01T00:00:00",
            auto_update=True,
        )
        assert km.source.repo == "test/repo"
        assert km.install_location == "marketplaces/test"
        assert km.auto_update is True
