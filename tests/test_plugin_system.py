"""Tests for the plugin system."""

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

import pytest

# Skip if plugins not available
try:
    from pilotcode.plugins.core.types import (
        PluginManifest,
        MarketplaceSource,
        PluginScope,
        SkillDefinition,
    )
    from pilotcode.plugins.core.config import PluginConfig
    from pilotcode.plugins.loader.skills import load_skill_from_file, parse_frontmatter
    PLUGINS_AVAILABLE = True
except ImportError:
    PLUGINS_AVAILABLE = False


pytestmark = pytest.mark.skipif(not PLUGINS_AVAILABLE, reason="Plugin system not available")


class TestFrontmatterParsing:
    """Test frontmatter parsing."""
    
    def test_parse_frontmatter_with_yaml(self):
        content = """---
name: test-skill
description: A test skill
allowedTools: [Read, Bash]
---

This is the skill content.
More content here.
"""
        frontmatter, markdown = parse_frontmatter(content)
        
        assert frontmatter["name"] == "test-skill"
        assert frontmatter["description"] == "A test skill"
        assert frontmatter["allowedTools"] == ["Read", "Bash"]
        assert "This is the skill content" in markdown
    
    def test_parse_frontmatter_without_yaml(self):
        content = "Just markdown content\nNo frontmatter here."
        frontmatter, markdown = parse_frontmatter(content)
        
        assert frontmatter == {}
        assert markdown == content
    
    def test_parse_frontmatter_empty_yaml(self):
        content = """---
---

Content only.
"""
        frontmatter, markdown = parse_frontmatter(content)
        
        assert frontmatter == {}
        assert "Content only" in markdown


class TestSkillLoading:
    """Test skill loading."""
    
    def test_load_skill_from_file(self, tmp_path):
        skill_file = tmp_path / "test-skill.md"
        skill_file.write_text("""---
name: my-skill
description: My test skill
aliases: [ms, my]
---

Do something useful.
""")
        
        skill = load_skill_from_file(skill_file)
        
        assert skill.name == "my-skill"
        assert skill.description == "My test skill"
        assert skill.aliases == ["ms", "my"]
        assert "Do something useful" in skill.content
    
    def test_load_skill_without_name_uses_filename(self, tmp_path):
        skill_file = tmp_path / "filename-skill.md"
        skill_file.write_text("""---
description: Uses filename
---

Content here.
""")
        
        skill = load_skill_from_file(skill_file)
        
        assert skill.name == "filename-skill"


class TestPluginManifest:
    """Test plugin manifest handling."""
    
    def test_manifest_from_dict(self):
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "description": "A test plugin",
            "author": {
                "name": "Test Author",
                "email": "test@example.com"
            }
        }
        
        manifest = PluginManifest(**data)
        
        assert manifest.name == "test-plugin"
        assert manifest.version == "1.0.0"
        assert manifest.author.name == "Test Author"
    
    def test_manifest_validation_name_with_spaces(self):
        with pytest.raises(ValueError):
            PluginManifest(name="invalid name", version="1.0.0")


class TestPluginConfig:
    """Test plugin configuration."""
    
    def test_config_directory_creation(self, tmp_path):
        config = PluginConfig(config_dir=tmp_path)
        
        assert config.plugins_dir.exists()
        assert config.cache_dir.exists()
        assert config.marketplaces_cache_dir.exists()
    
    def test_save_and_load_known_marketplaces(self, tmp_path):
        config = PluginConfig(config_dir=tmp_path)
        
        from pilotcode.plugins.core.types import KnownMarketplace
        
        marketplaces = {
            "test-marketplace": KnownMarketplace(
                source=MarketplaceSource(source="github", repo="test/repo"),
                install_location="test-location"
            )
        }
        
        config.save_known_marketplaces(marketplaces)
        loaded = config.load_known_marketplaces()
        
        assert "test-marketplace" in loaded
        assert loaded["test-marketplace"].source.repo == "test/repo"
    
    def test_save_and_load_installed_plugins(self, tmp_path):
        config = PluginConfig(config_dir=tmp_path)
        
        from pilotcode.plugins.core.types import PluginInstallation
        from datetime import datetime
        
        installations = [
            PluginInstallation(
                plugin_id="docker@official",
                scope=PluginScope.USER,
                install_path=tmp_path / "docker",
                version="1.0.0",
                installed_at=datetime.now()
            )
        ]
        
        config.save_installed_plugins(installations)
        loaded = config.load_installed_plugins()
        
        assert len(loaded) == 1
        assert loaded[0].plugin_id == "docker@official"


class TestMarketplaceSource:
    """Test marketplace source types."""
    
    def test_github_source(self):
        source = MarketplaceSource(
            source="github",
            repo="anthropics/claude-plugins-official"
        )
        
        assert source.source == "github"
        assert source.repo == "anthropics/claude-plugins-official"
    
    def test_github_source_validation(self):
        with pytest.raises(ValueError):
            MarketplaceSource(source="github")  # Missing repo
    
    def test_url_source(self):
        source = MarketplaceSource(
            source="url",
            url="https://example.com/marketplace.json"
        )
        
        assert source.source == "url"
        assert source.url == "https://example.com/marketplace.json"


@pytest.mark.asyncio
class TestPluginManager:
    """Test plugin manager functionality."""
    
    async def test_initialize_loads_marketplaces(self, tmp_path):
        from pilotcode.plugins.core.manager import PluginManager
        
        config = PluginConfig(config_dir=tmp_path)
        manager = PluginManager(config)
        
        await manager.initialize()
        
        # Should have official marketplace
        assert "claude-plugins-official" in manager.marketplace.list_marketplaces()
    
    async def test_install_local_plugin(self, tmp_path):
        from pilotcode.plugins.core.manager import PluginManager
        
        # Create a test plugin
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "test-plugin",
            "version": "1.0.0",
            "description": "Test plugin"
        }))
        
        # Create local marketplace
        marketplace_file = tmp_path / "marketplace.json"
        marketplace_file.write_text(json.dumps({
            "name": "local",
            "plugins": [{
                "name": "test-plugin",
                "description": "Test",
                "source": str(plugin_dir)
            }]
        }))
        
        config = PluginConfig(config_dir=tmp_path)
        manager = PluginManager(config)
        
        # Add local marketplace
        await manager.marketplace.add_marketplace(
            "local",
            MarketplaceSource(source="file", file_path=str(marketplace_file))
        )
        
        # Install plugin
        plugin = await manager.install_plugin("test-plugin@local")
        
        assert plugin.manifest.name == "test-plugin"
        assert plugin.enabled is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
