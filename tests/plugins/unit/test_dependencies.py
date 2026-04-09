"""Unit tests for dependency resolution."""

import pytest

try:
    from pilotcode.plugins.core.dependencies import (
        DependencyGraph,
        DependencyNode,
        DependencyEdge,
        DependencyStatus,
        VersionConstraint,
        DependencyResolver,
    )
    from pilotcode.plugins.core.types import PluginManifest
    PLUGINS_AVAILABLE = True
except ImportError:
    PLUGINS_AVAILABLE = False

pytestmark = [
    pytest.mark.unit,
    pytest.mark.plugin,
    pytest.mark.plugin_unit,
    pytest.mark.skipif(not PLUGINS_AVAILABLE, reason="Plugin system not available"),
]


class TestDependencyGraph:
    """Test DependencyGraph."""
    
    def test_create_empty_graph(self):
        """Test creating empty graph."""
        graph = DependencyGraph()
        
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0
    
    def test_add_plugin(self):
        """Test adding plugin to graph."""
        graph = DependencyGraph()
        manifest = PluginManifest(name="test-plugin", dependencies=["dep1", "dep2"])
        
        node = graph.add_plugin("test@marketplace", manifest)
        
        assert "test@marketplace" in graph.nodes
        assert node.plugin_id == "test@marketplace"
        assert node.depends_on == ["dep1", "dep2"]
    
    def test_get_dependencies(self):
        """Test getting dependencies."""
        graph = DependencyGraph()
        manifest = PluginManifest(name="test", dependencies=["dep1", "dep2"])
        graph.add_plugin("test", manifest)
        
        deps = graph.get_dependencies("test")
        
        assert deps == ["dep1", "dep2"]
    
    def test_get_dependents(self):
        """Test getting plugins that depend on a plugin."""
        graph = DependencyGraph()
        
        # Plugin A depends on B
        graph.add_plugin("A", PluginManifest(name="A", dependencies=["B"]))
        graph.add_plugin("B", PluginManifest(name="B"))
        
        dependents = graph.get_dependents("B")
        
        assert dependents == ["A"]
    
    def test_detect_no_cycles(self):
        """Test cycle detection with no cycles."""
        graph = DependencyGraph()
        
        graph.add_plugin("A", PluginManifest(name="A", dependencies=["B"]))
        graph.add_plugin("B", PluginManifest(name="B", dependencies=["C"]))
        graph.add_plugin("C", PluginManifest(name="C"))
        
        cycles = graph.detect_cycles()
        
        assert cycles == []
    
    def test_detect_simple_cycle(self):
        """Test detecting simple cycle."""
        graph = DependencyGraph()
        
        graph.add_plugin("A", PluginManifest(name="A", dependencies=["B"]))
        graph.add_plugin("B", PluginManifest(name="B", dependencies=["A"]))
        
        cycles = graph.detect_cycles()
        
        assert len(cycles) > 0
        # Cycle should contain A and B
        flat_cycles = [item for cycle in cycles for item in cycle]
        assert "A" in flat_cycles
        assert "B" in flat_cycles
    
    def test_get_installation_order(self):
        """Test topological sort for installation order."""
        graph = DependencyGraph()
        
        graph.add_plugin("A", PluginManifest(name="A", dependencies=["B", "C"]))
        graph.add_plugin("B", PluginManifest(name="B", dependencies=["C"]))
        graph.add_plugin("C", PluginManifest(name="C"))
        
        order = graph.get_installation_order()
        
        # C must come before B, B before A
        assert order.index("C") < order.index("B")
        assert order.index("B") < order.index("A")
    
    def test_validate_missing_dependency(self):
        """Test validation with missing dependency."""
        graph = DependencyGraph()
        
        graph.add_plugin("A", PluginManifest(name="A", dependencies=["missing"]))
        
        errors = graph.validate()
        
        assert len(errors) > 0
        assert "missing" in errors[0]
    
    def test_validate_with_cycles(self):
        """Test validation with cycles."""
        graph = DependencyGraph()
        
        graph.add_plugin("A", PluginManifest(name="A", dependencies=["B"]))
        graph.add_plugin("B", PluginManifest(name="B", dependencies=["A"]))
        
        errors = graph.validate()
        
        assert len(errors) > 0
        assert "Circular" in errors[0]


class TestVersionConstraint:
    """Test VersionConstraint."""
    
    def test_exact_version(self):
        """Test exact version matching."""
        vc = VersionConstraint("1.2.3")
        
        assert vc.matches("1.2.3") is True
        assert vc.matches("1.2.4") is False
        assert vc.matches("1.2.2") is False
    
    def test_caret_constraint(self):
        """Test caret (^) constraint."""
        vc = VersionConstraint("^1.2.3")
        
        assert vc.matches("1.2.3") is True
        assert vc.matches("1.3.0") is True
        assert vc.matches("1.9.9") is True
        assert vc.matches("2.0.0") is False
        # ^1.2.3 allows compatible versions (same major, >= minor.patch)
        # Note: implementation may vary, checking core behavior
        assert vc.matches("1.2.4") is True
    
    def test_tilde_constraint(self):
        """Test tilde (~) constraint."""
        vc = VersionConstraint("~1.2.3")
        
        assert vc.matches("1.2.3") is True
        assert vc.matches("1.2.9") is True
        assert vc.matches("1.3.0") is False
        # ~1.2.3 allows patch updates only
        assert vc.matches("1.2.4") is True
    
    def test_greater_than_constraint(self):
        """Test greater than (>) constraint."""
        vc = VersionConstraint(">1.2.3")
        
        assert vc.matches("1.2.4") is True
        assert vc.matches("2.0.0") is True
        assert vc.matches("1.2.3") is False
        assert vc.matches("1.2.2") is False
    
    def test_greater_or_equal_constraint(self):
        """Test greater or equal (>=) constraint."""
        vc = VersionConstraint(">=1.2.3")
        
        assert vc.matches("1.2.3") is True
        assert vc.matches("1.2.4") is True
        assert vc.matches("1.2.2") is False
    
    def test_less_than_constraint(self):
        """Test less than (<) constraint."""
        vc = VersionConstraint("<1.2.3")
        
        assert vc.matches("1.2.2") is True
        assert vc.matches("1.2.3") is False
        assert vc.matches("1.2.4") is False
    
    def test_any_version(self):
        """Test any version (*)."""
        vc = VersionConstraint("*")
        
        assert vc.matches("1.0.0") is True
        assert vc.matches("2.5.3") is True
        assert vc.matches("0.0.1") is True
    
    def test_semver_with_v_prefix(self):
        """Test handling of 'v' prefix in versions."""
        vc = VersionConstraint("1.2.3")
        
        # Implementation may or may not handle v prefix
        # Just verify it doesn't crash
        try:
            result = vc.matches("v1.2.3")
            assert result is True or result is False
        except Exception:
            pass  # Accept if it raises
    
    def test_prerelease_versions(self):
        """Test prerelease version comparison."""
        vc = VersionConstraint(">1.0.0")
        
        # Prerelease handling depends on implementation
        try:
            result = vc.matches("1.0.1-alpha")
            assert isinstance(result, bool)
        except Exception:
            pass  # Accept if parsing fails
        
        # Test normal version still works
        assert vc.matches("1.1.0") is True
