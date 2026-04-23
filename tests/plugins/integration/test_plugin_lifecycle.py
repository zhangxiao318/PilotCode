"""Integration tests for plugin lifecycle."""

import json
import pytest

try:
    from pilotcode.plugins import get_plugin_manager
    from pilotcode.plugins.core.config import PluginConfig
    from pilotcode.plugins.core.types import PluginScope, MarketplaceSource
    from pilotcode.plugins.loader.skills import SkillLoader
    from pilotcode.plugins.hooks import HookType, HookResult

    PLUGINS_AVAILABLE = True
except ImportError:
    PLUGINS_AVAILABLE = False

pytestmark = [
    pytest.mark.integration,
    pytest.mark.plugin,
    pytest.mark.plugin_integration,
    pytest.mark.slow,
    pytest.mark.skipif(not PLUGINS_AVAILABLE, reason="Plugin system not available"),
]


@pytest.fixture
async def manager(temp_config_dir, monkeypatch):
    """Create plugin manager with temp config."""
    import json as json_mod
    from pathlib import Path

    # Reset global plugin manager to ensure fresh state for each test
    import pilotcode.plugins.core.manager as manager_module

    manager_module._manager = None

    config = PluginConfig(config_dir=temp_config_dir)

    # Mock network calls to avoid timeouts
    from pilotcode.plugins.core.marketplace import MarketplaceManager

    original_update = MarketplaceManager.update_marketplace

    async def mock_update(self, name):
        """Mock update that loads from source directory instead of network."""
        import shutil

        # Get the known marketplace config
        known = config.load_known_marketplaces()
        if name not in known:
            return True

        marketplace_config = known[name]
        source = marketplace_config.source

        # Handle directory source (local marketplace)
        if source.source == "directory" and source.file_path:
            source_path = Path(source.file_path)
            # Try .claude-plugin/marketplace.json first
            marketplace_file = source_path / ".claude-plugin" / "marketplace.json"
            if not marketplace_file.exists():
                marketplace_file = source_path / "marketplace.json"

            if marketplace_file.exists():
                # Copy to cache
                target_path = Path(marketplace_config.install_location)
                target_path.mkdir(parents=True, exist_ok=True)
                shutil.copy2(marketplace_file, target_path / "marketplace.json")

                # Load into memory
                try:
                    with open(marketplace_file) as f:
                        data = json_mod.load(f)
                    from pilotcode.plugins.core.types import PluginMarketplace

                    marketplace = PluginMarketplace(**data)
                    self._marketplaces[name] = marketplace
                except Exception:
                    pass
        return True

    MarketplaceManager.update_marketplace = mock_update

    manager = await get_plugin_manager(config)
    yield manager
    # Cleanup
    (
        await manager.marketplace.stop_background_checks()
        if hasattr(manager.marketplace, "stop_background_checks")
        else None
    )
    # Reset global manager
    manager_module._manager = None
    # Restore original
    MarketplaceManager.update_marketplace = original_update


@pytest.fixture
def create_local_marketplace(temp_config_dir):
    """Create a local marketplace for testing."""

    def _create(plugins):
        marketplace_dir = temp_config_dir / "marketplace"
        marketplace_dir.mkdir(exist_ok=True)

        marketplace_data = {
            "name": "test-marketplace",
            "description": "Test marketplace",
            "version": "1.0.0",
            "plugins": plugins,
        }

        marketplace_file = marketplace_dir / "marketplace.json"
        with open(marketplace_file, "w") as f:
            json.dump(marketplace_data, f, indent=2)

        return marketplace_dir

    return _create


class TestPluginLifecycle:
    """Test complete plugin lifecycle."""

    async def test_full_plugin_lifecycle(
        self,
        manager,
        create_local_marketplace,
        create_test_plugin,
        temp_config_dir,
    ):
        """Test complete plugin lifecycle: install → load → use → uninstall."""
        # 1. Create test plugin
        plugin_dir = create_test_plugin("test-lifecycle", with_skills=True)

        # 2. Create local marketplace
        marketplace_dir = create_local_marketplace(
            [
                {
                    "name": "test-lifecycle",
                    "description": "Test plugin for lifecycle",
                    "version": "1.0.0",
                    "source": str(plugin_dir),
                }
            ]
        )

        # 3. Add marketplace
        await manager.marketplace.add_marketplace(
            "test-lifecycle-marketplace",
            MarketplaceSource(source="directory", file_path=str(marketplace_dir)),
        )

        # 4. Install plugin
        plugin = await manager.install_plugin(
            "test-lifecycle@test-lifecycle-marketplace",
            scope=PluginScope.USER,
        )

        assert plugin.manifest.name == "test-lifecycle"
        assert plugin.enabled is True

        # 5. Load plugins
        result = await manager.load_plugins()

        assert len(result.enabled) >= 1
        loaded_plugin = manager.get_loaded_plugin("test-lifecycle@test-lifecycle-marketplace")
        assert loaded_plugin is not None

        # 6. Load and verify skills
        if loaded_plugin.skills_path:
            skill_loader = SkillLoader(loaded_plugin.skills_path)
            skills = skill_loader.load_all()

            assert len(skills) >= 1
            assert skills[0].name == "test-skill"

        # 7. Disable plugin
        success = await manager.disable_plugin("test-lifecycle@test-lifecycle-marketplace")
        assert success is True

        result = await manager.load_plugins()
        loaded = [p for p in result.disabled if p.manifest.name == "test-lifecycle"]
        assert len(loaded) >= 1

        # 8. Re-enable plugin
        success = await manager.enable_plugin("test-lifecycle@test-lifecycle-marketplace")
        assert success is True

        # 9. Uninstall plugin
        success = await manager.uninstall_plugin("test-lifecycle@test-lifecycle-marketplace")
        assert success is True

        # Verify uninstalled
        plugin_after = manager.get_loaded_plugin("test-lifecycle@test-lifecycle-marketplace")
        assert plugin_after is None


class TestPluginWithHooks:
    """Test plugin with hooks integration."""

    async def test_hook_registration_from_plugin(self, temp_config_dir):
        """Test that hooks from plugins are properly registered."""
        from pilotcode.plugins.hooks import get_hook_manager

        hook_manager = get_hook_manager()

        # Register a test hook
        hook_called = False

        async def test_hook(context):
            nonlocal hook_called
            hook_called = True
            return HookResult()

        hook_manager.register(HookType.PRE_TOOL_USE, test_hook)

        # Execute hooks
        from pilotcode.plugins.hooks.types import HookContext

        context = HookContext(hook_type=HookType.PRE_TOOL_USE, tool_name="Read")
        result = await hook_manager.execute_hooks(HookType.PRE_TOOL_USE, context)

        assert hook_called is True
        assert result.allow_execution is True

        # Cleanup
        hook_manager.unregister(HookType.PRE_TOOL_USE, test_hook)


class TestPluginDependencies:
    """Test plugin dependency resolution."""

    async def test_dependency_graph(self, manager, temp_config_dir):
        """Test dependency graph resolution."""
        # Create dependent plugins
        plugin_a_dir = temp_config_dir / "plugin-a"
        plugin_a_dir.mkdir()
        with open(plugin_a_dir / "plugin.json", "w") as f:
            json.dump(
                {
                    "name": "plugin-a",
                    "version": "1.0.0",
                    "dependencies": ["plugin-b"],
                },
                f,
            )

        plugin_b_dir = temp_config_dir / "plugin-b"
        plugin_b_dir.mkdir()
        with open(plugin_b_dir / "plugin.json", "w") as f:
            json.dump(
                {
                    "name": "plugin-b",
                    "version": "1.0.0",
                },
                f,
            )

        # Check dependencies
        from pilotcode.plugins.core.dependencies import DependencyGraph
        from pilotcode.plugins.core.types import PluginManifest

        graph = DependencyGraph()

        manifest_a = PluginManifest(name="plugin-a", dependencies=["plugin-b"])
        manifest_b = PluginManifest(name="plugin-b")

        graph.add_plugin("plugin-a", manifest_a)
        graph.add_plugin("plugin-b", manifest_b)

        deps = graph.get_dependencies("plugin-a")
        assert deps == ["plugin-b"]

        order = graph.get_installation_order()
        assert order.index("plugin-b") < order.index("plugin-a")


class TestMarketplaceIntegration:
    """Test marketplace integration."""

    async def test_marketplace_update_flow(self, manager, temp_config_dir):
        """Test marketplace update flow."""
        # Create initial marketplace
        marketplace_dir = temp_config_dir / "test-marketplace"
        marketplace_dir.mkdir()

        marketplace_data = {
            "name": "test-marketplace",
            "description": "Test",
            "version": "1.0.0",
            "plugins": [],
        }

        with open(marketplace_dir / "marketplace.json", "w") as f:
            json.dump(marketplace_data, f)

        # Add marketplace
        await manager.marketplace.add_marketplace(
            "test-mp",
            MarketplaceSource(source="directory", file_path=str(marketplace_dir)),
        )

        # Verify loaded
        mp = manager.marketplace.get_marketplace("test-mp")
        assert mp is not None
        assert mp.name == "test-marketplace"

    async def test_plugin_search(self, manager, create_local_marketplace):
        """Test plugin search functionality."""
        # Create marketplace with plugins
        marketplace_dir = create_local_marketplace(
            [
                {
                    "name": "docker-helper",
                    "description": "Docker management tools",
                    "version": "1.0.0",
                    "source": "test/docker",
                },
                {
                    "name": "git-helper",
                    "description": "Git helpers",
                    "version": "1.0.0",
                    "source": "test/git",
                },
            ]
        )

        await manager.marketplace.add_marketplace(
            "search-test",
            MarketplaceSource(source="directory", file_path=str(marketplace_dir)),
        )

        # Search
        results = manager.marketplace.search_plugins("docker")

        assert len(results) >= 1
        names = [entry.name for entry, _ in results]
        assert "docker-helper" in names
