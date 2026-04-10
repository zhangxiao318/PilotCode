"""Plugin dependency resolution.

Handles dependency graphs, version constraints, and resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

from .types import PluginManifest, PluginInstallation


class DependencyStatus(Enum):
    """Status of a dependency."""

    SATISFIED = "satisfied"
    MISSING = "missing"
    DISABLED = "disabled"
    VERSION_MISMATCH = "version_mismatch"
    CIRCULAR = "circular"


@dataclass
class DependencyNode:
    """A node in the dependency graph."""

    plugin_id: str
    manifest: Optional[PluginManifest] = None
    installation: Optional[PluginInstallation] = None
    required_by: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    status: DependencyStatus = DependencyStatus.SATISFIED
    error_message: Optional[str] = None


@dataclass
class DependencyEdge:
    """An edge in the dependency graph."""

    from_plugin: str
    to_plugin: str
    version_constraint: Optional[str] = None
    optional: bool = False


class DependencyGraph:
    """Graph of plugin dependencies.

    Manages the dependency relationships between plugins and
    detects issues like missing dependencies or circular dependencies.
    """

    def __init__(self):
        self.nodes: dict[str, DependencyNode] = {}
        self.edges: list[DependencyEdge] = []

    def add_plugin(
        self,
        plugin_id: str,
        manifest: PluginManifest,
        installation: Optional[PluginInstallation] = None,
    ) -> DependencyNode:
        """Add a plugin to the graph."""
        node = DependencyNode(
            plugin_id=plugin_id,
            manifest=manifest,
            installation=installation,
            depends_on=list(manifest.dependencies) if manifest.dependencies else [],
        )
        self.nodes[plugin_id] = node

        # Create edges
        for dep in node.depends_on:
            edge = DependencyEdge(from_plugin=plugin_id, to_plugin=dep)
            self.edges.append(edge)

        return node

    def get_node(self, plugin_id: str) -> Optional[DependencyNode]:
        """Get a node by plugin ID."""
        return self.nodes.get(plugin_id)

    def get_dependencies(self, plugin_id: str) -> list[str]:
        """Get direct dependencies of a plugin."""
        node = self.nodes.get(plugin_id)
        if node:
            return list(node.depends_on)
        return []

    def get_dependents(self, plugin_id: str) -> list[str]:
        """Get plugins that depend on this plugin."""
        return [edge.from_plugin for edge in self.edges if edge.to_plugin == plugin_id]

    def detect_cycles(self) -> list[list[str]]:
        """Detect circular dependencies.

        Returns:
            List of cycles (each cycle is a list of plugin IDs)
        """
        cycles = []
        visited = set()
        rec_stack = set()

        def dfs(node_id: str, path: list[str]) -> None:
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)

            node = self.nodes.get(node_id)
            if node:
                for dep in node.depends_on:
                    if dep not in visited:
                        dfs(dep, path)
                    elif dep in rec_stack:
                        # Found cycle
                        cycle_start = path.index(dep)
                        cycle = path[cycle_start:] + [dep]
                        cycles.append(cycle)

            path.pop()
            rec_stack.remove(node_id)

        for node_id in self.nodes:
            if node_id not in visited:
                dfs(node_id, [])

        return cycles

    def get_installation_order(self) -> list[str]:
        """Get topological sort for installation order.

        Returns:
            List of plugin IDs in dependency order (dependencies first)
        """
        # Kahn's algorithm
        in_degree = {node_id: 0 for node_id in self.nodes}

        # Calculate in-degrees
        for edge in self.edges:
            if edge.to_plugin in in_degree:
                in_degree[edge.from_plugin] = in_degree.get(edge.from_plugin, 0) + 1

        # Start with nodes that have no dependencies
        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node_id = queue.pop(0)
            result.append(node_id)

            # Find nodes that depend on this one
            for edge in self.edges:
                if edge.to_plugin == node_id:
                    in_degree[edge.from_plugin] -= 1
                    if in_degree[edge.from_plugin] == 0:
                        queue.append(edge.from_plugin)

        # Check for cycles
        if len(result) != len(self.nodes):
            # There are cycles - return what we have
            pass

        return result

    def validate(self) -> list[str]:
        """Validate the dependency graph.

        Returns:
            List of error messages
        """
        errors = []

        # Check for missing dependencies
        for node in self.nodes.values():
            for dep in node.depends_on:
                if dep not in self.nodes:
                    errors.append(
                        f"Plugin '{node.plugin_id}' depends on '{dep}' which is not installed"
                    )
                    node.status = DependencyStatus.MISSING

        # Check for cycles
        cycles = self.detect_cycles()
        for cycle in cycles:
            cycle_str = " -> ".join(cycle)
            errors.append(f"Circular dependency detected: {cycle_str}")
            for plugin_id in cycle[:-1]:  # Exclude the repeated last element
                if plugin_id in self.nodes:
                    self.nodes[plugin_id].status = DependencyStatus.CIRCULAR

        return errors


class DependencyResolver:
    """Resolves plugin dependencies.

    Handles finding, installing, and validating dependencies.
    """

    def __init__(self, manager):
        from .manager import PluginManager

        self.manager: PluginManager = manager

    async def resolve_dependencies(
        self,
        plugin_id: str,
        install_missing: bool = True,
    ) -> DependencyGraph:
        """Resolve all dependencies for a plugin.

        Args:
            plugin_id: Plugin to resolve dependencies for
            install_missing: Whether to auto-install missing dependencies

        Returns:
            DependencyGraph with resolved dependencies
        """
        graph = DependencyGraph()
        visited = set()

        async def resolve(plugin_id: str) -> None:
            if plugin_id in visited:
                return
            visited.add(plugin_id)

            # Get plugin info
            installation = self.manager._get_installation(plugin_id)
            if not installation:
                return

            manifest = self.manager._load_manifest(installation.install_path)

            # Add to graph
            graph.add_plugin(plugin_id, manifest, installation)

            # Resolve dependencies
            for dep in manifest.dependencies or []:
                # Normalize dependency name
                dep_id = self._normalize_dependency(dep, plugin_id)

                # Check if installed
                dep_installation = self.manager._get_installation(dep_id)

                if not dep_installation and install_missing:
                    # Try to auto-install
                    try:
                        await self.manager.install_plugin(dep_id)
                        dep_installation = self.manager._get_installation(dep_id)
                    except Exception as e:
                        # Add to graph as missing
                        graph.add_plugin(
                            dep_id,
                            PluginManifest(name=dep_id),
                            None,
                        )
                        if dep_id in graph.nodes:
                            graph.nodes[dep_id].status = DependencyStatus.MISSING
                            graph.nodes[dep_id].error_message = str(e)

                if dep_installation:
                    await resolve(dep_id)

        await resolve(plugin_id)

        # Validate the graph
        graph.validate()

        return graph

    def check_reverse_dependencies(
        self,
        plugin_id: str,
    ) -> list[str]:
        """Check which plugins depend on the given plugin.

        Used before uninstalling to warn about dependents.

        Args:
            plugin_id: Plugin to check

        Returns:
            List of plugin IDs that depend on this one
        """
        dependents = []

        for installation in self.manager.config.load_installed_plugins():
            if installation.plugin_id == plugin_id:
                continue

            try:
                manifest = self.manager._load_manifest(installation.install_path)
                deps = manifest.dependencies or []

                # Check if this plugin is a dependency
                for dep in deps:
                    dep_id = self._normalize_dependency(dep, installation.plugin_id)
                    if dep_id == plugin_id:
                        dependents.append(installation.plugin_id)
                        break
            except Exception:
                pass

        return dependents

    def _normalize_dependency(
        self,
        dep: str,
        source_plugin_id: str,
    ) -> str:
        """Normalize a dependency reference to full plugin_id.

        Args:
            dep: Dependency reference (can be name or name@marketplace)
            source_plugin_id: Plugin that has this dependency

        Returns:
            Full plugin_id
        """
        if "@" in dep:
            return dep

        # Try to infer marketplace from source plugin
        if "@" in source_plugin_id:
            marketplace = source_plugin_id.split("@", 1)[1]
            return f"{dep}@{marketplace}"

        return dep


class VersionConstraint:
    """Version constraint parser and checker.

    Supports basic semver constraints:
    - Exact: 1.2.3
    - Caret: ^1.2.3 (compatible with 1.x.x)
    - Tilde: ~1.2.3 (compatible with 1.2.x)
    - Greater: >1.2.3, >=1.2.3
    - Less: <1.2.3, <=1.2.3
    - Range: 1.2.3 - 2.0.0
    - Any: * or x
    """

    def __init__(self, constraint: str):
        self.constraint = constraint.strip()
        self._parsed = self._parse()

    def _parse(self) -> dict:
        """Parse the constraint string."""
        c = self.constraint

        # Any version
        if c in ("*", "x", "X"):
            return {"type": "any"}

        # Caret (^) - compatible with major version
        if c.startswith("^"):
            version = c[1:]
            parts = version.split(".")
            return {
                "type": "caret",
                "major": int(parts[0]) if len(parts) > 0 else 0,
                "minor": int(parts[1]) if len(parts) > 1 else 0,
                "patch": int(parts[2]) if len(parts) > 2 else 0,
            }

        # Tilde (~) - compatible with minor version
        if c.startswith("~"):
            version = c[1:]
            parts = version.split(".")
            return {
                "type": "tilde",
                "major": int(parts[0]) if len(parts) > 0 else 0,
                "minor": int(parts[1]) if len(parts) > 1 else 0,
                "patch": int(parts[2]) if len(parts) > 2 else 0,
            }

        # Comparison operators
        for op in [">=", "<=", ">", "<"]:
            if c.startswith(op):
                return {
                    "type": "compare",
                    "op": op,
                    "version": c[len(op) :].strip(),
                }

        # Exact version
        return {
            "type": "exact",
            "version": c,
        }

    def matches(self, version: str) -> bool:
        """Check if a version matches this constraint."""
        p = self._parsed

        if p["type"] == "any":
            return True

        if p["type"] == "exact":
            return version == p["version"]

        if p["type"] == "caret":
            v_parts = version.split(".")
            v_major = int(v_parts[0]) if len(v_parts) > 0 else 0

            # Must have same major version
            if v_major != p["major"]:
                return False

            # If major is 0, minor must match
            if p["major"] == 0:
                v_minor = int(v_parts[1]) if len(v_parts) > 1 else 0
                if v_minor != p["minor"]:
                    return False

            return True

        if p["type"] == "tilde":
            v_parts = version.split(".")
            v_major = int(v_parts[0]) if len(v_parts) > 0 else 0
            v_minor = int(v_parts[1]) if len(v_parts) > 1 else 0

            # Must have same major and minor
            return v_major == p["major"] and v_minor == p["minor"]

        if p["type"] == "compare":
            return self._compare_versions(version, p["version"], p["op"])

        return False

    def _compare_versions(self, v1: str, v2: str, op: str) -> bool:
        """Compare two versions."""
        p1 = [int(x) for x in v1.split(".")]
        p2 = [int(x) for x in v2.split(".")]

        # Pad to same length
        while len(p1) < len(p2):
            p1.append(0)
        while len(p2) < len(p1):
            p2.append(0)

        # Compare
        for a, b in zip(p1, p2):
            if a != b:
                if op == ">":
                    return a > b
                elif op == ">=":
                    return a > b
                elif op == "<":
                    return a < b
                elif op == "<=":
                    return a < b

        # Equal
        if op in (">=", "<=", "="):
            return True
        return False
