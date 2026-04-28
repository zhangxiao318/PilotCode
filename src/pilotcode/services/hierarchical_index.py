"""Hierarchical code indexing for large codebases.

Divides the codebase into subgraphs (components) based on directory structure
and import dependencies. Provides a tiered index:

- Tier 1 (Master Index): Project overview + subgraph summaries (low token cost)
- Tier 2 (Subgraph Index): Detailed symbol listings for a specific subgraph
- Tier 3 (Symbol Detail): Full code via existing CodeContext/CodeSearch tools

This enables LLMs with small context windows to first understand the codebase
structure, then selectively drill down into relevant components.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SubgraphInfo:
    """Information about a code subgraph (component)."""

    id: str
    name: str
    path: str  # Relative directory path
    files: list[str] = field(default_factory=list)
    symbols: list[dict] = field(default_factory=list)
    summary: str = ""
    key_apis: list[str] = field(default_factory=list)
    imports_from: list[str] = field(default_factory=list)
    exports_to: list[str] = field(default_factory=list)
    total_lines: int = 0
    file_count: int = 0
    symbol_count: int = 0
    class_count: int = 0
    function_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "files": self.files,
            "symbols": self.symbols,
            "summary": self.summary,
            "key_apis": self.key_apis,
            "imports_from": self.imports_from,
            "exports_to": self.exports_to,
            "total_lines": self.total_lines,
            "file_count": self.file_count,
            "symbol_count": self.symbol_count,
            "class_count": self.class_count,
            "function_count": self.function_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SubgraphInfo:
        return cls(
            id=data["id"],
            name=data["name"],
            path=data["path"],
            files=data.get("files", []),
            symbols=data.get("symbols", []),
            summary=data.get("summary", ""),
            key_apis=data.get("key_apis", []),
            imports_from=data.get("imports_from", []),
            exports_to=data.get("exports_to", []),
            total_lines=data.get("total_lines", 0),
            file_count=data.get("file_count", 0),
            symbol_count=data.get("symbol_count", 0),
            class_count=data.get("class_count", 0),
            function_count=data.get("function_count", 0),
        )


@dataclass
class MasterIndex:
    """Top-level index containing subgraph summaries."""

    project_name: str = ""
    root_path: str = ""
    total_files: int = 0
    total_symbols: int = 0
    total_lines: int = 0
    languages: dict[str, int] = field(default_factory=dict)
    subgraphs: list[SubgraphInfo] = field(default_factory=list)
    core_subgraphs: list[str] = field(default_factory=list)
    shared_modules: list[dict] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    orphan_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "root_path": self.root_path,
            "total_files": self.total_files,
            "total_symbols": self.total_symbols,
            "total_lines": self.total_lines,
            "languages": self.languages,
            "subgraphs": [s.to_dict() for s in self.subgraphs],
            "core_subgraphs": self.core_subgraphs,
            "shared_modules": self.shared_modules,
            "entry_points": self.entry_points,
            "orphan_files": self.orphan_files,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MasterIndex:
        return cls(
            project_name=data.get("project_name", ""),
            root_path=data.get("root_path", ""),
            total_files=data.get("total_files", 0),
            total_symbols=data.get("total_symbols", 0),
            total_lines=data.get("total_lines", 0),
            languages=data.get("languages", {}),
            subgraphs=[SubgraphInfo.from_dict(s) for s in data.get("subgraphs", [])],
            core_subgraphs=data.get("core_subgraphs", []),
            shared_modules=data.get("shared_modules", []),
            entry_points=data.get("entry_points", []),
            orphan_files=data.get("orphan_files", []),
        )


class HierarchicalIndexBuilder:
    """Builds a hierarchical index from AST analysis results."""

    # Tunable parameters
    MAX_FILES_PER_SUBGRAPH = 50
    MIN_FILES_PER_SUBGRAPH = 2
    MAX_SYMBOLS_PER_SUBGRAPH_DETAIL = 200  # Limit symbols in tier-2 output

    def __init__(self, root_path: str | Path):
        self.root_path = Path(root_path).resolve()
        self._master: MasterIndex | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        files: list[str],
        ast_cache: dict[str, Any],
        symbol_index: dict[str, list[dict]] | None = None,
    ) -> MasterIndex:
        """Build the full hierarchical index.

        Args:
            files: List of indexed file paths (absolute or relative)
            ast_cache: AST analyzer cache: {file_path: ModuleInfo dict}
            symbol_index: Optional {file_path: [symbol dicts]} from CodeIndexer
        """
        # Normalize file paths to be relative to root
        rel_files = [self._rel(f) for f in files]
        abs_to_rel = {self._abs(f): self._rel(f) for f in files}

        # Step 1: Directory clustering
        clusters = self._cluster_by_directory(rel_files)

        # Step 2: Build subgraphs from clusters
        subgraphs: list[SubgraphInfo] = []
        for cluster_path, cluster_files in clusters.items():
            sg = self._build_subgraph(cluster_path, cluster_files, ast_cache, symbol_index)
            subgraphs.append(sg)

        # Step 3: Compute cross-subgraph import/export relations
        self._compute_import_relations(subgraphs, ast_cache, abs_to_rel)

        # Step 4: Generate summaries
        self._generate_subgraph_summaries(subgraphs, ast_cache)

        # Step 5: Identify core subgraphs and shared modules
        core_subgraphs = self._identify_core_subgraphs(subgraphs)
        shared_modules = self._identify_shared_modules(subgraphs, ast_cache)

        # Step 6: Identify entry points
        entry_points = self._identify_entry_points(rel_files, ast_cache)

        # Step 7: Collect orphans (files not in any cluster – should be rare)
        clustered_files = set()
        for sg in subgraphs:
            clustered_files.update(sg.files)
        orphan_files = [f for f in rel_files if f not in clustered_files]

        # Step 8: Language stats
        languages: dict[str, int] = defaultdict(int)
        for f in rel_files:
            lang = self._detect_language(f)
            languages[lang] += 1

        # Step 9: Totals
        total_lines = sum(sg.total_lines for sg in subgraphs)
        total_symbols = sum(sg.symbol_count for sg in subgraphs)

        self._master = MasterIndex(
            project_name=self.root_path.name or "Project",
            root_path=str(self.root_path),
            total_files=len(rel_files),
            total_symbols=total_symbols,
            total_lines=total_lines,
            languages=dict(languages),
            subgraphs=subgraphs,
            core_subgraphs=core_subgraphs,
            shared_modules=shared_modules,
            entry_points=entry_points,
            orphan_files=orphan_files,
        )
        return self._master

    def get_master_index(self) -> MasterIndex | None:
        return self._master

    def get_subgraph(self, subgraph_id: str) -> SubgraphInfo | None:
        if self._master is None:
            return None
        for sg in self._master.subgraphs:
            if sg.id == subgraph_id or sg.name == subgraph_id or sg.path == subgraph_id:
                return sg
        return None

    def format_master_index(self, max_subgraphs: int | None = None) -> str:
        """Format the master index as a concise text for LLM consumption."""
        if self._master is None:
            return "# Codebase Index\n\nNot indexed yet."

        m = self._master
        lines: list[str] = []
        lines.append(f"# Project Overview: {m.project_name}")
        lines.append("")
        lines.append(f"- **Total files**: {m.total_files}")
        lines.append(f"- **Total symbols**: {m.total_symbols}")
        lines.append(f"- **Total lines**: {m.total_lines}")
        if m.languages:
            lang_str = ", ".join(
                f"{k}: {v}" for k, v in sorted(m.languages.items(), key=lambda x: -x[1])
            )
            lines.append(f"- **Languages**: {lang_str}")
        lines.append("")

        # Subgraphs
        subgraphs = m.subgraphs
        if max_subgraphs:
            subgraphs = subgraphs[:max_subgraphs]

        lines.append(f"## Subgraphs ({len(m.subgraphs)} total)")
        lines.append("")
        for i, sg in enumerate(subgraphs, 1):
            lines.append(f"### {i}. {sg.name} ({sg.file_count} files, {sg.symbol_count} symbols)")
            lines.append(f"- **Path**: `{sg.path}`")
            if sg.summary:
                lines.append(f"- **Summary**: {sg.summary}")
            if sg.key_apis:
                apis = ", ".join(f"`{a}`" for a in sg.key_apis[:8])
                lines.append(f"- **Key APIs**: {apis}")
            if sg.imports_from:
                deps = ", ".join(f"`{d}`" for d in sg.imports_from[:5])
                lines.append(f"- **Depends on**: {deps}")
            lines.append("")

        if max_subgraphs and len(m.subgraphs) > max_subgraphs:
            lines.append(f"*... and {len(m.subgraphs) - max_subgraphs} more subgraphs*")
            lines.append("")

        # Core subgraphs
        if m.core_subgraphs:
            lines.append("## Core Subgraphs (most depended upon)")
            for cs in m.core_subgraphs:
                lines.append(f"- `{cs}`")
            lines.append("")

        # Shared modules
        if m.shared_modules:
            lines.append("## Shared Modules (high reuse)")
            for mod in m.shared_modules[:10]:
                name = mod.get("name", "?")
                count = mod.get("imported_by", 0)
                lines.append(f"- `{name}` (imported by {count} subgraphs)")
            lines.append("")

        # Entry points
        if m.entry_points:
            lines.append("## Entry Points")
            for ep in m.entry_points[:5]:
                lines.append(f"- `{ep}`")
            lines.append("")

        # Orphans
        if m.orphan_files:
            lines.append(f"## Unclustered Files ({len(m.orphan_files)})")
            for of in m.orphan_files[:10]:
                lines.append(f"- `{of}`")
            lines.append("")

        lines.append(
            "---\n" "*To explore a subgraph in detail, use the subgraph name or path as a filter.*"
        )
        return "\n".join(lines)

    def format_subgraph_detail(self, subgraph_id: str, max_symbols: int = 100) -> str:
        """Format detailed information for a specific subgraph."""
        sg = self.get_subgraph(subgraph_id)
        if sg is None:
            return f"# Subgraph not found: {subgraph_id}"

        lines: list[str] = []
        lines.append(f"# Subgraph: {sg.name}")
        lines.append(f"- **Path**: `{sg.path}`")
        lines.append(f"- **Files**: {sg.file_count}")
        lines.append(
            f"- **Symbols**: {sg.symbol_count} ({sg.class_count} classes, {sg.function_count} functions)"
        )
        lines.append("")

        if sg.summary:
            lines.append(f"## Summary\n{sg.summary}\n")

        # Files
        lines.append("## Files")
        for f in sg.files:
            lines.append(f"- `{f}`")
        lines.append("")

        # Symbols
        if sg.symbols:
            lines.append("## Symbols")
            displayed = sg.symbols[:max_symbols]
            for sym in displayed:
                name = sym.get("name", "?")
                stype = sym.get("type", "?")
                file_path = sym.get("file", "?")
                line = sym.get("line", "?")
                sig = sym.get("signature", "")
                parent = sym.get("parent", "")
                prefix = f"{parent}." if parent else ""
                sig_part = f" - `{sig}`" if sig else ""
                lines.append(f"- `{prefix}{name}` ({stype}) [{file_path}:{line}]{sig_part}")
            if len(sg.symbols) > max_symbols:
                lines.append(f"- ... and {len(sg.symbols) - max_symbols} more symbols")
            lines.append("")

        # Key APIs
        if sg.key_apis:
            lines.append("## Key Public APIs")
            for api in sg.key_apis:
                lines.append(f"- `{api}`")
            lines.append("")

        # Dependencies
        if sg.imports_from:
            lines.append("## Imports From")
            for dep in sg.imports_from:
                lines.append(f"- `{dep}`")
            lines.append("")
        if sg.exports_to:
            lines.append("## Exported To")
            for dep in sg.exports_to:
                lines.append(f"- `{dep}`")
            lines.append("")

        return "\n".join(lines)

    def save(self, path: str | Path) -> None:
        """Save the master index to a JSON file."""
        if self._master is None:
            return
        Path(path).write_text(json.dumps(self._master.to_dict(), indent=2), encoding="utf-8")

    def load(self, path: str | Path) -> MasterIndex:
        """Load the master index from a JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self._master = MasterIndex.from_dict(data)
        return self._master

    # ------------------------------------------------------------------
    # Clustering
    # ------------------------------------------------------------------

    def _cluster_by_directory(self, rel_files: list[str]) -> dict[str, list[str]]:
        """Group files into clusters based on directory structure.

        Strategy:
        1. Build directory tree with file counts
        2. Start from deepest directories
        3. If directory has [min, max] files -> standalone cluster
        4. If too many files -> try to split by subdirectories
        5. If too few files -> merge with siblings or parent
        """
        # Build tree: dir -> {files: [...], children: {...}}
        tree: dict[str, Any] = {"files": [], "children": {}}
        for f in rel_files:
            parts = Path(f).parts
            node = tree
            for part in parts[:-1]:
                if part not in node["children"]:
                    node["children"][part] = {"files": [], "children": {}}
                node = node["children"][part]
            node["files"].append(f)

        clusters: dict[str, list[str]] = {}

        def _collect_files(node: dict) -> list[str]:
            """Recursively collect all files under a node."""
            files = list(node["files"])
            for child in node["children"].values():
                files.extend(_collect_files(child))
            return files

        def _split_flat_directory(path: str, files: list[str]) -> list[str] | None:
            """Split a flat directory into sub-clusters by prefix."""
            prefix_groups: dict[str, list[str]] = defaultdict(list)
            for f in files:
                stem = Path(f).stem
                prefix = stem.split("_")[0] if "_" in stem else stem[:3]
                prefix_groups[prefix].append(f)

            unclustered: list[str] = []
            for prefix, group in prefix_groups.items():
                if len(group) >= self.MIN_FILES_PER_SUBGRAPH:
                    sub_path = f"{path}/{prefix}*"
                    clusters[sub_path] = group
                else:
                    unclustered.extend(group)

            if len(unclustered) >= self.MIN_FILES_PER_SUBGRAPH:
                clusters[path] = unclustered
                return None
            elif unclustered:
                return unclustered
            return None

        def _process_node(path: str, node: dict) -> list[str] | None:
            """Process a directory node. Returns unclustered files or None."""
            all_files = _collect_files(node)
            count = len(all_files)

            if count == 0:
                return None

            # If this node fits perfectly, cluster it
            if self.MIN_FILES_PER_SUBGRAPH <= count <= self.MAX_FILES_PER_SUBGRAPH:
                clusters[path] = all_files
                return None

            # If too small, return for parent to handle
            if count < self.MIN_FILES_PER_SUBGRAPH:
                return all_files

            # If too large, try to split by children
            if node["children"]:
                unclustered: list[str] = []
                child_was_clustered = False

                for child_name, child_node in node["children"].items():
                    child_path = f"{path}/{child_name}" if path else child_name
                    result = _process_node(child_path, child_node)
                    if result is not None:
                        unclustered.extend(result)
                    else:
                        child_was_clustered = True

                # If no child could be clustered independently and total is still
                # too large, split everything by prefix instead of one giant cluster.
                if not child_was_clustered and len(all_files) > self.MAX_FILES_PER_SUBGRAPH:
                    return _split_flat_directory(path, all_files)

                # Handle unclustered (too-small children) by grouping them
                if unclustered:
                    if len(unclustered) >= self.MIN_FILES_PER_SUBGRAPH:
                        # Don't merge back into an already-oversized parent;
                        # create a sibling "misc" group instead.
                        group_path = f"{path}_misc" if path else "misc"
                        # Ensure unique path
                        idx = 1
                        final_path = group_path
                        while final_path in clusters:
                            final_path = f"{group_path}_{idx}"
                            idx += 1
                        clusters[final_path] = unclustered
                    else:
                        # Return to parent
                        return unclustered
                return None

            # Too large and no children -> split by file prefix or type
            return _split_flat_directory(path, all_files)

        # Process root children (don't cluster at root level directly)
        root_unclustered: list[str] = []
        for child_name, child_node in tree["children"].items():
            result = _process_node(child_name, child_node)
            if result:
                root_unclustered.extend(result)

        # Group any root-level unclustered files
        if root_unclustered:
            clusters["root_misc"] = root_unclustered

        return clusters

    # ------------------------------------------------------------------
    # Subgraph building
    # ------------------------------------------------------------------

    def _build_subgraph(
        self,
        cluster_path: str,
        cluster_files: list[str],
        ast_cache: dict[str, Any],
        symbol_index: dict[str, list[dict]] | None,
    ) -> SubgraphInfo:
        """Build a SubgraphInfo from a file cluster."""
        # Determine name
        name = Path(cluster_path).name
        if name.endswith("*"):
            name = name[:-1]
        if not name or name == ".":
            name = "root"

        sg_id = re.sub(r"[^a-zA-Z0-9_-]", "_", cluster_path).strip("_")
        if not sg_id:
            sg_id = "root"

        sg = SubgraphInfo(
            id=sg_id,
            name=name,
            path=cluster_path,
            files=sorted(cluster_files),
        )

        # Collect symbols and stats
        symbols: list[dict] = []
        total_lines = 0
        class_count = 0
        function_count = 0

        for rel_file in cluster_files:
            abs_file = str(self.root_path / rel_file)

            # Lines
            try:
                content = Path(abs_file).read_text(encoding="utf-8", errors="ignore")
                total_lines += len(content.split("\n"))
            except Exception:
                pass

            # AST-based symbols
            module = ast_cache.get(abs_file)
            if module:
                for cls in module.get("classes", []):
                    class_count += 1
                    methods = cls.get("methods", [])
                    method_names = [m.get("name", "") for m in methods[:5]]
                    method_str = ", ".join(method_names)
                    if len(methods) > 5:
                        method_str += f" +{len(methods) - 5}"
                    symbols.append(
                        {
                            "name": cls.get("name", "?"),
                            "type": "class",
                            "file": rel_file,
                            "line": cls.get("line_number", 1),
                            "signature": f"class {cls.get('name', '?')}({', '.join(cls.get('bases', []))})",
                            "methods": method_str,
                        }
                    )
                    for method in methods:
                        function_count += 1
                        args = ", ".join(method.get("args", [])[:5])
                        symbols.append(
                            {
                                "name": method.get("name", "?"),
                                "type": "method",
                                "file": rel_file,
                                "line": method.get("line_number", 1),
                                "signature": f"def {method.get('name', '?')}({args})",
                                "parent": cls.get("name", ""),
                            }
                        )

                for func in module.get("functions", []):
                    # Skip methods already counted
                    function_count += 1
                    args = ", ".join(func.get("args", [])[:5])
                    symbols.append(
                        {
                            "name": func.get("name", "?"),
                            "type": "function",
                            "file": rel_file,
                            "line": func.get("line_number", 1),
                            "signature": f"def {func.get('name', '?')}({args})",
                        }
                    )

            # Fallback to symbol_index if AST not available
            if not module and symbol_index and rel_file in symbol_index:
                for sym in symbol_index[rel_file]:
                    if sym.get("type") == "class":
                        class_count += 1
                    elif sym.get("type") in ("function", "method"):
                        function_count += 1
                    symbols.append(
                        {
                            "name": sym.get("name", "?"),
                            "type": sym.get("type", "?"),
                            "file": rel_file,
                            "line": sym.get("line", 1),
                            "signature": sym.get("signature", ""),
                            "parent": sym.get("parent", ""),
                        }
                    )

        sg.symbols = symbols
        sg.total_lines = total_lines
        sg.file_count = len(cluster_files)
        sg.symbol_count = len(symbols)
        sg.class_count = class_count
        sg.function_count = function_count
        return sg

    # ------------------------------------------------------------------
    # Import / export relations
    # ------------------------------------------------------------------

    def _compute_import_relations(
        self,
        subgraphs: list[SubgraphInfo],
        ast_cache: dict[str, Any],
        abs_to_rel: dict[str, str],
    ) -> None:
        """Compute which subgraphs import from which other subgraphs."""
        # Map file -> subgraph id
        file_to_sg: dict[str, str] = {}
        for sg in subgraphs:
            for f in sg.files:
                file_to_sg[f] = sg.id

        # Collect imports per subgraph
        sg_imports: dict[str, Counter] = {sg.id: Counter() for sg in subgraphs}

        for abs_file, module in ast_cache.items():
            rel_file = abs_to_rel.get(abs_file)
            if not rel_file or rel_file not in file_to_sg:
                continue

            sg_id = file_to_sg[rel_file]
            for imp in module.get("imports", []):
                imp_module = imp.get("module", "")
                if not imp_module:
                    continue

                # Try to map import to a subgraph
                # Heuristic: import module name -> file path stem
                target_sg = self._resolve_import_to_subgraph(imp_module, subgraphs)
                if target_sg and target_sg != sg_id:
                    sg_imports[sg_id][target_sg] += 1

        # Apply to subgraphs
        for sg in subgraphs:
            imports = sg_imports[sg.id]
            # Only include subgraphs with >= 2 imports (avoid noise)
            sg.imports_from = [s for s, c in imports.most_common() if c >= 1]
            # Exports computed in reverse

        # Compute exports (reverse of imports)
        for sg in subgraphs:
            exports: list[str] = []
            for other in subgraphs:
                if other.id == sg.id:
                    continue
                if sg.id in other.imports_from:
                    exports.append(other.id)
            sg.exports_to = exports

    def _resolve_import_to_subgraph(
        self, module_name: str, subgraphs: list[SubgraphInfo]
    ) -> str | None:
        """Try to map an imported module name to a subgraph id.

        Heuristic: match module name against file stem or directory path.
        """
        parts = module_name.split(".")
        # Try full path match, then partial
        for depth in range(len(parts), 0, -1):
            candidate = "/".join(parts[-depth:])
            for sg in subgraphs:
                if candidate in sg.path.replace("\\", "/"):
                    return sg.id
                for f in sg.files:
                    if Path(f).stem == parts[-1]:
                        return sg.id
        return None

    # ------------------------------------------------------------------
    # Summary generation
    # ------------------------------------------------------------------

    def _generate_subgraph_summaries(
        self, subgraphs: list[SubgraphInfo], ast_cache: dict[str, Any]
    ) -> None:
        """Generate one-line summaries for each subgraph."""
        for sg in subgraphs:
            parts: list[str] = []

            # Base description from directory name and content types
            name_desc = self._describe_name(sg.name)
            content_types = []
            if sg.class_count > 0:
                content_types.append(f"{sg.class_count} classes")
            if sg.function_count > 0:
                content_types.append(f"{sg.function_count} functions")

            if content_types:
                parts.append(f"{name_desc} with {', '.join(content_types)}")
            else:
                parts.append(name_desc)

            # Add docstring hints
            docstrings = []
            for f in sg.files:
                module = ast_cache.get(str(self.root_path / f))
                if module and module.get("docstring"):
                    docstrings.append(module["docstring"])

            if docstrings:
                # Use first docstring as hint
                hint = docstrings[0].split("\n")[0].strip()[:80]
                parts.append(f"— {hint}")

            sg.summary = " ".join(parts)

            # Key APIs: symbols that are likely public
            # Heuristic: classes and top-level functions with no underscore prefix
            key_apis = []
            for sym in sg.symbols:
                name = sym.get("name", "")
                stype = sym.get("type", "")
                if not name.startswith("_") and stype in ("class", "function"):
                    key_apis.append(name)
            sg.key_apis = key_apis[:10]

    def _describe_name(self, name: str) -> str:
        """Generate a human-readable description from a directory name."""
        name_lower = name.lower()
        mapping = {
            "web": "Web layer",
            "server": "Server infrastructure",
            "client": "Client-side code",
            "api": "API definitions and handlers",
            "model": "Data models",
            "models": "Data models",
            "service": "Business logic services",
            "services": "Business logic services",
            "tool": "Tool implementations",
            "tools": "Tool implementations",
            "util": "Utility functions",
            "utils": "Utility functions",
            "common": "Common utilities",
            "config": "Configuration",
            "test": "Tests",
            "tests": "Tests",
            "cmd": "Commands",
            "command": "Commands",
            "commands": "Commands",
            "cli": "Command-line interface",
            "db": "Database layer",
            "db_": "Database layer",
            "repo": "Repository / data access",
            "core": "Core business logic",
            "lib": "Library code",
            "plugin": "Plugin system",
            "auth": "Authentication",
            "middleware": "Middleware",
            "handler": "Request handlers",
            "view": "Views / UI",
            "controller": "Controllers",
            "router": "Routing logic",
            "schema": "Data schemas",
            "type": "Type definitions",
            "types": "Type definitions",
            "protocol": "Protocol definitions",
            "interface": "Interface definitions",
            "exception": "Exceptions and errors",
            "error": "Error handling",
            "log": "Logging utilities",
            "cache": "Caching layer",
            "queue": "Queue / messaging",
            "task": "Background tasks",
            "worker": "Worker processes",
            "script": "Scripts",
            "migration": "Database migrations",
            "seed": "Seed data",
            "fixture": "Test fixtures",
            "mock": "Mocks and stubs",
            "stub": "Stubs",
            "fake": "Test fakes",
            "helper": "Helpers",
            "helpers": "Helpers",
            "base": "Base classes",
            "abstract": "Abstract definitions",
            "mixin": "Mixins",
            "decorator": "Decorators",
            "context": "Context managers",
            "manager": "Managers",
            "factory": "Factories",
            "builder": "Builders",
            "parser": "Parsers",
            "lexer": "Lexers",
            "compiler": "Compilers",
            "transform": "Transformations",
            "converter": "Converters",
            "serializer": "Serializers",
            "validator": "Validators",
            "filter": "Filters",
            "search": "Search functionality",
            "index": "Indexing",
            "query": "Query handling",
            "storage": "Storage layer",
            "file": "File operations",
            "io": "I/O operations",
            "net": "Networking",
            "http": "HTTP layer",
            "ws": "WebSocket layer",
            "socket": "Socket handling",
            "rpc": "RPC layer",
            "grpc": "gRPC layer",
            "rest": "REST API",
            "graphql": "GraphQL layer",
            "event": "Event handling",
            "hook": "Hooks",
            "signal": "Signals",
            "observer": "Observers",
            "pubsub": "Pub/sub messaging",
            "stream": "Streaming",
            "batch": "Batch processing",
            "pipeline": "Pipelines",
            "workflow": "Workflows",
            "state": "State management",
            "store": "State store",
            "reducer": "Reducers",
            "action": "Actions",
            "dispatch": "Dispatchers",
            "resolver": "Resolvers",
            "provider": "Providers",
            "injector": "Dependency injection",
            "container": "DI container",
            "registry": "Registries",
            "catalog": "Catalogs",
            "metadata": "Metadata",
            "annotation": "Annotations",
            "marker": "Markers",
            "tag": "Tags",
            "label": "Labels",
            "const": "Constants",
            "enum": "Enumerations",
            "flag": "Feature flags",
            "setting": "Settings",
            "preference": "Preferences",
            "option": "Options",
            "argument": "Arguments",
            "param": "Parameters",
            "field": "Fields",
            "column": "Columns",
            "attr": "Attributes",
            "prop": "Properties",
            "relation": "Relations",
            "assoc": "Associations",
            "link": "Links",
            "ref": "References",
            "pointer": "Pointers",
            "addr": "Addresses",
            "loc": "Locations",
            "pos": "Positions",
            "coord": "Coordinates",
            "region": "Regions",
            "zone": "Zones",
            "area": "Areas",
            "sector": "Sectors",
            "segment": "Segments",
            "section": "Sections",
            "partition": "Partitions",
            "shard": "Shards",
            "chunk": "Chunks",
            "block": "Blocks",
            "unit": "Units",
            "cell": "Cells",
            "item": "Items",
            "element": "Elements",
            "component": "Components",
            "part": "Parts",
            "piece": "Pieces",
            "module": "Modules",
            "package": "Packages",
            "bundle": "Bundles",
            "assembly": "Assemblies",
            "artifact": "Artifacts",
            "resource": "Resources",
            "asset": "Assets",
            "static": "Static assets",
            "media": "Media files",
            "template": "Templates",
            "layout": "Layouts",
            "partial": "Partials",
            "fragment": "Fragments",
            "snippet": "Snippets",
            "include": "Includes",
            "import": "Imports",
            "export": "Exports",
            "bind": "Bindings",
            "wrap": "Wrappers",
            "adapter": "Adapters",
            "bridge": "Bridges",
            "proxy": "Proxies",
            "delegate": "Delegates",
            "fallback": "Fallbacks",
            "default": "Defaults",
            "override": "Overrides",
            "custom": "Customizations",
            "extension": "Extensions",
            "addon": "Add-ons",
            "plugin_": "Plugins",
            "integration": "Integrations",
            "connector": "Connectors",
            "driver": "Drivers",
            "backend": "Backends",
            "frontend": "Frontends",
            "ui": "UI components",
            "gui": "GUI layer",
            "widget": "Widgets",
            "control": "Controls",
            "panel": "Panels",
            "dialog": "Dialogs",
            "form": "Forms",
            "input": "Input handling",
            "output": "Output handling",
            "render": "Rendering",
            "draw": "Drawing",
            "paint": "Painting",
            "display": "Display",
            "screen": "Screen management",
            "window": "Window management",
            "frame": "Frames",
            "canvas": "Canvas",
            "surface": "Surfaces",
            "texture": "Textures",
            "sprite": "Sprites",
            "mesh": "Meshes",
            "geometry": "Geometry",
            "shape": "Shapes",
            "path": "Paths",
            "curve": "Curves",
            "line": "Lines",
            "point": "Points",
            "vertex": "Vertices",
            "edge": "Edges",
            "face": "Faces",
            "poly": "Polygons",
            "grid": "Grids",
            "map": "Maps",
            "chart": "Charts",
            "graph": "Graphs",
            "tree": "Trees",
            "node": "Nodes",
            "leaf": "Leaves",
            "branch": "Branches",
            "root_": "Root structures",
            "parent": "Parent structures",
            "child": "Child structures",
            "sibling": "Sibling structures",
            "descendant": "Descendants",
            "ancestor": "Ancestors",
            "peer": "Peers",
            "group": "Groups",
            "cluster": "Clusters",
            "set": "Sets",
            "list": "Lists",
            "array": "Arrays",
            "vector": "Vectors",
            "matrix": "Matrices",
            "tuple": "Tuples",
            "dict": "Dictionaries",
            "map_": "Maps",
            "hash": "Hashes",
            "table": "Tables",
            "record": "Records",
            "row": "Rows",
            "entry": "Entries",
            "slot": "Slots",
            "bucket": "Buckets",
            "bin": "Bins",
            "pile": "Piles",
            "stack": "Stacks",
            "queue_": "Queues",
            "heap": "Heaps",
            "priority": "Priority queues",
            "deque": "Deques",
            "list_": "Lists",
            "chain": "Chains",
            "link_": "Linked structures",
            "ring": "Rings",
            "cycle": "Cycles",
            "loop": "Loops",
            "iter": "Iterators",
            "generator": "Generators",
            "yield": "Yielding",
            "stream_": "Streams",
            "flow": "Flows",
            "pipe": "Pipes",
            "channel": "Channels",
            "bus": "Buses",
            "line_": "Lines",
            "wire": "Wires",
            "circuit": "Circuits",
            "network": "Network layer",
            "topology": "Topologies",
            "graph_": "Graph structures",
            "dag": "DAG structures",
            "forest": "Forests",
            "heap_": "Heaps",
            "trie": "Tries",
            "bloom": "Bloom filters",
            "skip": "Skip lists",
            "rb": "Red-black trees",
            "avl": "AVL trees",
            "btree": "B-trees",
            "bst": "Binary search trees",
            "segment_": "Segment trees",
            "fenwick": "Fenwick trees",
            "sparse": "Sparse tables",
            "suffix": "Suffix structures",
            "trie_": "Tries",
            "auto": "Automata",
            "dfa": "DFAs",
            "nfa": "NFAs",
            "pda": "PDAs",
            "tm": "Turing machines",
            "state_": "State machines",
            "fsm": "Finite state machines",
            "hsm": "Hierarchical state machines",
            "mealy": "Mealy machines",
            "moore": "Moore machines",
            "petri": "Petri nets",
            "markov": "Markov chains",
            "bayes": "Bayesian networks",
            "neural": "Neural networks",
            "layer": "Layers",
            "activation": "Activations",
            "loss": "Loss functions",
            "optimizer": "Optimizers",
            "scheduler": "Schedulers",
            "lr": "Learning rate",
            "batch_": "Batching",
            "epoch": "Epochs",
            "iteration": "Iterations",
            "step": "Steps",
            "phase": "Phases",
            "stage": "Stages",
            "level": "Levels",
            "tier": "Tiers",
            "rank": "Ranks",
            "grade": "Grades",
            "class_": "Classes",
            "category": "Categories",
            "kind": "Kinds",
            "sort": "Sorts",
            "type_": "Types",
            "variant": "Variants",
            "version": "Versions",
            "edition": "Editions",
            "release": "Releases",
            "build_": "Build system",
            "ci": "CI/CD",
            "deploy": "Deployment",
            "infra": "Infrastructure",
            "devops": "DevOps",
            "sre": "SRE",
            "ops": "Operations",
            "monitor": "Monitoring",
            "alert": "Alerts",
            "metric": "Metrics",
            "trace": "Tracing",
            "span": "Spans",
            "log_": "Logging",
            "audit": "Auditing",
            "security": "Security",
            "crypto": "Cryptography",
            "cipher": "Ciphers",
            "hash_": "Hashing",
            "digest": "Digests",
            "signature_": "Signatures",
            "cert": "Certificates",
            "key_": "Keys",
            "token_": "Tokens",
            "secret": "Secrets",
            "vault": "Vaults",
            "kms": "Key management",
            "iam": "Identity management",
            "rbac": "RBAC",
            "acl": "ACLs",
            "policy": "Policies",
            "rule": "Rules",
            "permission": "Permissions",
            "role": "Roles",
            "claim": "Claims",
            "scope": "Scopes",
            "grant": "Grants",
            "entitlement": "Entitlements",
            "license": "Licenses",
            "agreement": "Agreements",
            "contract": "Contracts",
            "terms": "Terms",
            "condition": "Conditions",
            "constraint": "Constraints",
            "limit": "Limits",
            "quota": "Quotas",
            "rate": "Rate limiting",
            "throttle": "Throttling",
            "circuit_": "Circuit breakers",
            "retry": "Retries",
            "backoff": "Backoff",
            "timeout": "Timeouts",
            "deadline": "Deadlines",
            "ttl": "TTL",
            "expiry": "Expiry",
            "lease": "Leases",
            "lock": "Locks",
            "mutex": "Mutexes",
            "semaphore": "Semaphores",
            "barrier": "Barriers",
            "latch": "Latches",
            "condition_": "Conditions",
            "event_": "Events",
            "signal_": "Signals",
            "notify": "Notifications",
            "subscribe": "Subscriptions",
            "publish": "Publishing",
            "broadcast": "Broadcasting",
            "multicast": "Multicasting",
            "unicast": "Unicasting",
            "anycast": "Anycasting",
            "peer_": "Peer-to-peer",
            "relay": "Relays",
            "proxy_": "Proxies",
            "gateway": "Gateways",
            "lb": "Load balancers",
            "balancer": "Balancers",
            "dispatcher": "Dispatchers",
            "router_": "Routers",
            "switch": "Switches",
            "hub": "Hubs",
            "repeater": "Repeaters",
            "bridge_": "Bridges",
            "tunnel": "Tunnels",
            "vpn": "VPN",
            "nat": "NAT",
            "firewall": "Firewalls",
            "waf": "WAF",
            "ddos": "DDoS protection",
            "cdn": "CDN",
            "origin": "Origins",
            "cache_": "Caching",
            "store_": "Storage",
            "persist": "Persistence",
            "archive": "Archives",
            "backup": "Backups",
            "snapshot": "Snapshots",
            "checkpoint": "Checkpoints",
            "restore": "Restores",
            "recover": "Recovery",
            "replicate": "Replication",
            "sync": "Synchronization",
            "mirror": "Mirrors",
            "clone": "Clones",
            "fork": "Forks",
            "branch_": "Branches",
            "merge": "Merges",
            "rebase": "Rebases",
            "cherry": "Cherry-picks",
            "stash": "Stashes",
            "patch": "Patches",
            "diff": "Differences",
            "blame": "Blame",
            "annotate": "Annotations",
            "tag_": "Tags",
            "label_": "Labels",
            "mark": "Marks",
            "stamp": "Stamps",
            "sign": "Signatures",
            "verify": "Verification",
            "validate": "Validation",
            "check": "Checks",
            "inspect": "Inspection",
            "scan": "Scanning",
            "detect": "Detection",
            "find_": "Finding",
            "locate": "Locating",
            "lookup": "Lookups",
            "resolve_": "Resolution",
            "fetch": "Fetching",
            "get_": "Getters",
            "set_": "Setters",
            "put": "Puts",
            "post": "Posts",
            "create": "Creation",
            "make": "Making",
            "construct": "Construction",
            "instantiate": "Instantiation",
            "init": "Initialization",
            "setup": "Setup",
            "configure": "Configuration",
            "prepare": "Preparation",
            "ready": "Readiness",
            "start": "Starting",
            "begin": "Beginning",
            "launch": "Launching",
            "run_": "Running",
            "execute": "Execution",
            "perform": "Performance",
            "carry": "Carrying",
            "bring": "Bringing",
            "move": "Movement",
            "transfer": "Transfers",
            "copy": "Copying",
            "clone_": "Cloning",
            "duplicate": "Duplication",
            "replicate_": "Replication",
            "spawn": "Spawning",
            "fork_": "Forking",
            "split": "Splitting",
            "divide": "Division",
            "separate": "Separation",
            "partition_": "Partitioning",
            "shard_": "Sharding",
            "slice": "Slicing",
            "chunk_": "Chunking",
            "fragment_": "Fragmentation",
            "piece_": "Pieces",
            "part_": "Parts",
            "portion": "Portions",
            "share": "Sharing",
            "distribute": "Distribution",
            "allocate": "Allocation",
            "assign": "Assignment",
            "delegate_": "Delegation",
            "appoint": "Appointment",
            "nominate": "Nomination",
            "elect": "Election",
            "select": "Selection",
            "choose": "Choosing",
            "pick": "Picking",
            "sample": "Sampling",
            "random": "Randomization",
            "shuffle": "Shuffling",
            "sort_": "Sorting",
            "order": "Ordering",
            "rank_": "Ranking",
            "grade_": "Grading",
            "score": "Scoring",
            "rate_": "Rating",
            "evaluate": "Evaluation",
            "assess": "Assessment",
            "measure": "Measurement",
            "gauge": "Gauging",
            "meter": "Metering",
            "count": "Counting",
            "tally": "Tallies",
            "sum": "Summation",
            "total": "Totals",
            "aggregate": "Aggregation",
            "collect": "Collection",
            "gather": "Gathering",
            "accumulate": "Accumulation",
            "reduce": "Reduction",
            "fold": "Folding",
            "compress": "Compression",
            "compact": "Compaction",
            "consolidate": "Consolidation",
            "merge_": "Merging",
            "join": "Joining",
            "combine": "Combination",
            "union": "Unions",
            "intersect": "Intersections",
            "difference": "Differences",
            "complement": "Complements",
            "subset": "Subsets",
            "superset": "Supersets",
            "powerset": "Powersets",
            "cartesian": "Cartesian products",
            "cross": "Cross products",
            "outer": "Outer products",
            "inner": "Inner products",
            "dot": "Dot products",
            "tensor": "Tensors",
            "matrix_": "Matrices",
            "vector_": "Vectors",
            "scalar": "Scalars",
            "complex": "Complex numbers",
            "quaternion": "Quaternions",
            "octonion": "Octonions",
            "sedenion": "Sedenions",
            "polynomial": "Polynomials",
            "rational": "Rationals",
            "irrational": "Irrationals",
            "transcendental": "Transcendentals",
            "algebraic": "Algebraics",
            "integer": "Integers",
            "natural": "Natural numbers",
            "whole": "Whole numbers",
            "real": "Real numbers",
            "imaginary": "Imaginary numbers",
            "infinity": "Infinity",
            "nan": "NaN",
            "null": "Null handling",
            "nil": "Nil handling",
            "none": "None handling",
            "void": "Void handling",
            "empty": "Empty handling",
            "zero": "Zero handling",
            "one": "One handling",
            "unit_": "Unit handling",
            "identity": "Identity",
            "inverse": "Inverses",
            "conjugate": "Conjugates",
            "transpose": "Transposes",
            "adjoint": "Adjoints",
            "determinant": "Determinants",
            "trace_": "Traces",
            "eigen": "Eigenvalues/vectors",
            "singular": "SVD",
            "norm": "Norms",
            "distance": "Distances",
            "similarity": "Similarities",
            "difference_": "Differences",
            "error_": "Errors",
            "residual": "Residuals",
            "deviation": "Deviations",
            "variance": "Variances",
            "covariance": "Covariances",
            "correlation": "Correlations",
            "regression": "Regressions",
            "interpolation": "Interpolations",
            "extrapolation": "Extrapolations",
            "approximation": "Approximations",
            "estimation": "Estimations",
            "prediction": "Predictions",
            "forecast": "Forecasts",
            "projection": "Projections",
            "simulation": "Simulations",
            "emulation": "Emulations",
            "model_": "Models",
            "template_": "Templates",
            "pattern": "Patterns",
            "schema_": "Schemas",
            "structure": "Structures",
            "shape_": "Shapes",
            "geometry_": "Geometries",
            "topology_": "Topologies",
            "morphology": "Morphologies",
            "syntax": "Syntax",
            "grammar": "Grammars",
            "language_": "Languages",
            "parser_": "Parsers",
            "lexer_": "Lexers",
            "tokenizer": "Tokenizers",
            "scanner": "Scanners",
            "interpreter": "Interpreters",
            "evaluator": "Evaluators",
            "engine": "Engines",
            "runtime": "Runtimes",
            "vm": "Virtual machines",
            "jit": "JIT compilation",
            "aot": "AOT compilation",
            "compiler_": "Compilers",
            "assembler": "Assemblers",
            "linker": "Linkers",
            "loader": "Loaders",
            "binder": "Binders",
            "resolver_": "Resolvers",
            "mapper": "Mappers",
            "reducer_": "Reducers",
            "filter_": "Filters",
            "transformer": "Transformers",
            "converter_": "Converters",
            "encoder": "Encoders",
            "decoder": "Decoders",
            "codec": "Codecs",
            "compressor": "Compressors",
            "decompressor": "Decompressors",
            "archiver": "Archivers",
            "extractor": "Extractors",
            "packer": "Packers",
            "unpacker": "Unpackers",
            "serializer_": "Serializers",
            "deserializer": "Deserializers",
            "marshaler": "Marshalers",
            "unmarshaler": "Unmarshalers",
            "picker": "Picklers",
            "unpickler": "Unpicklers",
            "json_": "JSON handling",
            "xml_": "XML handling",
            "yaml_": "YAML handling",
            "toml_": "TOML handling",
            "csv_": "CSV handling",
            "tsv_": "TSV handling",
            "parquet": "Parquet handling",
            "avro": "Avro handling",
            "protobuf": "Protobuf handling",
            "thrift": "Thrift handling",
            "msgpack": "MessagePack handling",
            "bson": "BSON handling",
            "cbor": "CBOR handling",
            "flexbuf": "FlexBuffers handling",
            "flatbuf": "FlatBuffers handling",
            "capnp": "Cap'n Proto handling",
            "grpc_": "gRPC handling",
            "graphql_": "GraphQL handling",
            "rest_": "REST handling",
            "soap": "SOAP handling",
            "rpc_": "RPC handling",
            "socket_": "Socket handling",
            "tcp": "TCP handling",
            "udp": "UDP handling",
            "icmp": "ICMP handling",
            "ip": "IP handling",
            "arp": "ARP handling",
            "dhcp": "DHCP handling",
            "dns": "DNS handling",
            "http_": "HTTP handling",
            "https": "HTTPS handling",
            "ftp": "FTP handling",
            "sftp": "SFTP handling",
            "ssh": "SSH handling",
            "telnet": "Telnet handling",
            "smtp": "SMTP handling",
            "imap": "IMAP handling",
            "pop3": "POP3 handling",
            "webdav": "WebDAV handling",
            "ldap": "LDAP handling",
            "sasl": "SASL handling",
            "oauth": "OAuth handling",
            "openid": "OpenID handling",
            "saml": "SAML handling",
            "jwt": "JWT handling",
            "jws": "JWS handling",
            "jwe": "JWE handling",
            "jwk": "JWK handling",
            "pem": "PEM handling",
            "der": "DER handling",
            "x509": "X.509 handling",
            "crl": "CRL handling",
            "ocsp": "OCSP handling",
            "cst": "Certificate transparency",
            "hpkp": "HPKP handling",
            "hsts": "HSTS handling",
            "csp": "CSP handling",
            "cors": "CORS handling",
            "csrf": "CSRF handling",
            "xss": "XSS handling",
            "sqli": "SQL injection",
            "nosql": "NoSQL injection",
            "cmdi": "Command injection",
            "lfi": "LFI handling",
            "rfi": "RFI handling",
            "xxe": "XXE handling",
            "ssrf": "SSRF handling",
            "idor": "IDOR handling",
            "bac": "BAC handling",
            "race": "Race conditions",
            "toctou": "TOCTOU handling",
            "deadlock": "Deadlocks",
            "livelock": "Livelocks",
            "starvation": "Starvation",
            "priority_": "Priority inversion",
            "aba": "ABA problems",
            "memory": "Memory management",
            "gc": "Garbage collection",
            "refcount": "Reference counting",
            "weakref": "Weak references",
            "softref": "Soft references",
            "phantom": "Phantom references",
            "finalizer": "Finalizers",
            "cleaner": "Cleaners",
            "disposer": "Disposers",
            "destructor": "Destructors",
            "allocator": "Allocators",
            "deallocator": "Deallocators",
            "pool": "Pools",
            "arena": "Arenas",
            "zone_": "Zones",
            "region_": "Regions",
            "generation": "Generations",
            "eden": "Eden space",
            "survivor": "Survivor space",
            "tenured": "Tenured space",
            "perm": "Perm gen",
            "metaspace": "Metaspace",
            "codecache": "Code cache",
            "jit_": "JIT cache",
            "icache": "Instruction cache",
            "dcache": "Data cache",
            "tlb": "TLB",
            "mmu": "MMU",
            "dma": "DMA",
            "irq": "IRQ handling",
            "isr": "ISRs",
            "dpc": "DPCs",
            "apc": "APCs",
            "syscall": "Syscalls",
            "ioctl": "IOCTLs",
            "mmap": "Memory mapping",
            "mprotect": "Memory protection",
            "munmap": "Memory unmapping",
            "brk": "Break handling",
            "sbrk": "Sbrk handling",
            "page": "Page management",
            "frame_": "Frame management",
            "swap": "Swapping",
            "paging": "Paging",
            "protection": "Protection",
            "isolation": "Isolation",
            "sandbox": "Sandboxing",
            "jail": "Jailing",
            "container_": "Containers",
            "namespace_": "Namespaces",
            "cgroup": "Cgroups",
            "seccomp": "Seccomp",
            "apparmor": "AppArmor",
            "selinux": "SELinux",
            "capabilities": "Capabilities",
            "overlay": "Overlays",
            "bind_": "Bind mounts",
            "tmpfs": "Tmpfs",
            "procfs": "Procfs",
            "sysfs": "Sysfs",
            "devfs": "Devfs",
            "cgroupfs": "Cgroupfs",
            "debugfs": "Debugfs",
            "tracefs": "Tracefs",
            "configfs": "Configfs",
            "securityfs": "Securityfs",
            "bpf": "BPF",
            "ebpf": "eBPF",
            "kprobe": "Kprobes",
            "uprobe": "Uprobes",
            "tracepoint": "Tracepoints",
            "perf": "Perf events",
            "ftrace": "Ftrace",
            "lttng": "LTTng",
            "systemtap": "SystemTap",
            "dtrace": "DTrace",
            "strace": "Strace",
            "ltrace": "Ltrace",
            "ptrace": "Ptrace",
            "gdb": "GDB",
            "lldb": "LLDB",
            "debugger": "Debuggers",
            "profiler": "Profilers",
            "tracer": "Tracers",
            "sampler": "Samplers",
            "counter": "Counters",
            "gauge_": "Gauges",
            "histogram": "Histograms",
            "summary_": "Summaries",
            "dashboard": "Dashboards",
            "alert_": "Alerts",
            "notification": "Notifications",
            "webhook": "Webhooks",
            "email": "Email",
            "sms": "SMS",
            "push": "Push notifications",
            "slack": "Slack integration",
            "pagerduty": "PagerDuty integration",
            "opsgenie": "Opsgenie integration",
            "victorops": "VictorOps integration",
            "telegram": "Telegram integration",
            "discord": "Discord integration",
            "teams": "Teams integration",
            "irc": "IRC integration",
            "xmpp": "XMPP integration",
            "mqtt": "MQTT handling",
            "amqp": "AMQP handling",
            "stomp": "STOMP handling",
            "xmtp": "XMTP handling",
            "coap": "CoAP handling",
            "lwm2m": "LwM2M handling",
            "zigbee": "Zigbee handling",
            "zwave": "Z-Wave handling",
            "ble": "Bluetooth LE",
            "thread": "Thread handling",
            "matter": "Matter handling",
            "homekit": "HomeKit handling",
            "kn": "KNX handling",
            "bacnet": "BACnet handling",
            "modbus": "Modbus handling",
            "opc": "OPC handling",
            "plc": "PLC handling",
            "scada": "SCADA handling",
            "dcs": "DCS handling",
            "hmi": "HMI handling",
            "m2m": "M2M handling",
            "iot": "IoT handling",
            "edge_": "Edge handling",
            "fog": "Fog handling",
            "cloud": "Cloud handling",
            "saas": "SaaS handling",
            "paas": "PaaS handling",
            "iaas": "IaaS handling",
            "faas": "FaaS handling",
            "daas": "DaaS handling",
            "baas": "BaaS handling",
            "mbaas": "MBaaS handling",
            "dbaas": "DBaaS handling",
            "ai": "AI layer",
            "ml": "ML layer",
            "dl": "Deep learning",
            "nlp": "NLP",
            "cv": "Computer vision",
            "asr": "ASR",
            "tts": "TTS",
            "ocr": "OCR",
            "stt": "STT",
            "mt": "Machine translation",
            "qa": "QA systems",
            "chatbot": "Chatbots",
            "agent": "Agents",
            "bot": "Bots",
            "automation": "Automation",
            "workflow_": "Workflows",
            "orchestration": "Orchestration",
            "choreography": "Choreography",
            "saga": "Sagas",
            "compensation": "Compensations",
            "transaction": "Transactions",
            "acid": "ACID",
            "cap": "CAP theorem",
            "paxos": "Paxos",
            "raft": "Raft",
            "pbft": "PBFT",
            "tendermint": "Tendermint",
            "hotstuff": "HotStuff",
            "libra": "LibraBFT",
            "sync_": "Synchronization",
            "async_": "Async handling",
            "await": "Await handling",
            "future": "Futures",
            "promise": "Promises",
            "deferred": "Deferreds",
            "callback": "Callbacks",
            "continuation": "Continuations",
            "coroutine": "Coroutines",
            "fiber": "Fibers",
            "greenlet": "Greenlets",
            "tasklet": "Tasklets",
            "process_": "Processes",
            "thread_": "Threads",
            "pool_": "Pools",
            "worker_": "Workers",
            "executor": "Executors",
            "engine_": "Engines",
            "driver_": "Drivers",
            "handler_": "Handlers",
            "processor": "Processors",
            "consumer": "Consumers",
            "producer": "Producers",
            "publisher": "Publishers",
            "subscriber_": "Subscribers",
            "observer_": "Observers",
            "listener": "Listeners",
            "watcher": "Watchers",
            "monitor_": "Monitors",
            "supervisor": "Supervisors",
            "manager_": "Managers",
            "controller_": "Controllers",
            "coordinator": "Coordinators",
            "leader": "Leaders",
            "follower": "Followers",
            "replica": "Replicas",
            "primary": "Primaries",
            "secondary": "Secondaries",
            "master_": "Masters",
            "slave": "Slaves",
            "standby": "Standbys",
            "backup_": "Backups",
            "mirror_": "Mirrors",
            "shadow": "Shadows",
            "copy_": "Copies",
            "duplicate_": "Duplicates",
            "replica_": "Replicas",
            "slice_": "Slices",
            "block_": "Blocks",
            "page_": "Pages",
            "section_": "Sections",
            "area_": "Areas",
            "domain": "Domains",
            "realm": "Realms",
            "kingdom": "Kingdoms",
            "territory": "Territories",
            "jurisdiction": "Jurisdictions",
            "boundary": "Boundaries",
            "border": "Borders",
            "frontier": "Frontiers",
            "horizon": "Horizons",
            "scope_": "Scopes",
            "range": "Ranges",
            "extent": "Extents",
            "span_": "Spans",
            "reach": "Reaches",
            "coverage": "Coverage",
            "footprint": "Footprints",
            "impact": "Impacts",
            "influence": "Influences",
            "effect": "Effects",
            "consequence": "Consequences",
            "result": "Results",
            "outcome": "Outcomes",
            "output_": "Outputs",
            "product": "Products",
            "artifact_": "Artifacts",
            "byproduct": "Byproducts",
            "sideeffect": "Side effects",
            "residue": "Residues",
            "remnant": "Remnants",
            "vestige": "Vestiges",
            "relic": "Relics",
            "remains": "Remains",
            "debris": "Debris",
            "rubble": "Rubble",
            "wreckage": "Wreckage",
            "ruins": "Ruins",
            "ashes": "Ashes",
            "dust": "Dust",
            "smoke": "Smoke",
            "fog_": "Fog",
            "mist": "Mist",
            "haze": "Haze",
            "cloud_": "Clouds",
            "storm": "Storms",
            "rain": "Rain",
            "snow": "Snow",
            "ice": "Ice",
            "frost": "Frost",
            "freeze": "Freezing",
            "thaw": "Thawing",
            "melt": "Melting",
            "boil": "Boiling",
            "steam": "Steam",
            "vapor": "Vapor",
            "gas": "Gas handling",
            "liquid": "Liquid handling",
            "solid": "Solid handling",
            "plasma": "Plasma handling",
            "phase_": "Phase transitions",
            "change": "Changes",
            "transition": "Transitions",
            "transformation": "Transformations",
            "conversion": "Conversions",
            "mutation": "Mutations",
            "variation": "Variations",
            "modification": "Modifications",
            "adaptation": "Adaptations",
            "evolution": "Evolution",
            "devolution": "Devolution",
            "revolution": "Revolutions",
            "rotation": "Rotations",
            "orbit": "Orbits",
            "trajectory": "Trajectories",
            "path_": "Paths",
            "course": "Courses",
            "route": "Routes",
            "way": "Ways",
            "direction": "Directions",
            "orientation": "Orientations",
            "position": "Positions",
            "location": "Locations",
            "placement": "Placements",
            "arrangement": "Arrangements",
            "configuration": "Configurations",
            "layout_": "Layouts",
            "design": "Designs",
            "plan": "Plans",
            "scheme": "Schemes",
            "strategy": "Strategies",
            "tactic": "Tactics",
            "method": "Methods",
            "approach": "Approaches",
            "technique": "Techniques",
            "procedure": "Procedures",
            "protocol_": "Protocols",
            "standard": "Standards",
            "convention": "Conventions",
            "guideline": "Guidelines",
            "principle": "Principles",
            "rule_": "Rules",
            "law": "Laws",
            "theorem": "Theorems",
            "lemma": "Lemmas",
            "corollary": "Corollaries",
            "proposition": "Propositions",
            "axiom": "Axioms",
            "postulate": "Postulates",
            "hypothesis": "Hypotheses",
            "thesis": "Theses",
            "antithesis": "Antitheses",
            "synthesis": "Syntheses",
            "analysis_": "Analyses",
            "evaluation_": "Evaluations",
            "assessment_": "Assessments",
            "appraisal": "Appraisals",
            "review": "Reviews",
            "survey": "Surveys",
            "study": "Studies",
            "research": "Research",
            "investigation": "Investigations",
            "inquiry": "Inquiries",
            "query_": "Queries",
            "question": "Questions",
            "answer": "Answers",
            "response": "Responses",
            "reply": "Replies",
            "feedback": "Feedback",
            "comment": "Comments",
            "annotation_": "Annotations",
            "note": "Notes",
            "remark": "Remarks",
            "observation": "Observations",
            "finding": "Findings",
            "discovery": "Discoveries",
            "insight": "Insights",
            "intuition": "Intuitions",
            "hunch": "Hunches",
            "guess": "Guesses",
            "estimate_": "Estimates",
            "approximation_": "Approximations",
            "bound": "Bounds",
            "limit_": "Limits",
            "constraint_": "Constraints",
            "restriction": "Restrictions",
            "prohibition": "Prohibitions",
            "ban": "Bans",
            "obstacle": "Obstacles",
            "hurdle": "Hurdles",
            "challenge": "Challenges",
            "problem": "Problems",
            "issue": "Issues",
            "bug": "Bugs",
            "defect": "Defects",
            "flaw": "Flaws",
            "fault": "Faults",
            "mistake": "Mistakes",
            "failure": "Failures",
            "crash": "Crashes",
            "panic": "Panics",
            "abort": "Aborts",
            "kill": "Kills",
            "terminate": "Termination",
            "exit": "Exits",
            "quit": "Quits",
            "stop": "Stops",
            "halt": "Halts",
            "suspend": "Suspension",
            "pause": "Pauses",
            "resume": "Resumes",
            "continue": "Continuation",
            "restart": "Restarts",
            "reboot": "Reboots",
            "reset": "Resets",
            "reload": "Reloads",
            "refresh": "Refreshes",
            "renew": "Renewals",
            "restore_": "Restores",
            "revert": "Reverts",
            "rollback": "Rollbacks",
            "undo": "Undos",
            "redo": "Redos",
            "replay": "Replays",
            "rewind": "Rewinds",
            "fastforward": "Fast forwards",
            "skip_": "Skips",
            "jump": "Jumps",
            "hop": "Hops",
            "leap": "Leaps",
            "bound_": "Bounds",
            "bounce": "Bounces",
            "ricochet": "Ricochets",
            "reflect": "Reflections",
            "refract": "Refractions",
            "diffract": "Diffractions",
            "interfere": "Interference",
            "scatter": "Scattering",
            "absorb": "Absorption",
            "emit": "Emission",
            "radiate": "Radiation",
            "propagate": "Propagation",
            "transmit": "Transmission",
            "receive_": "Reception",
            "capture": "Capture",
            "acquire": "Acquisition",
            "obtain": "Obtaining",
            "gain": "Gains",
            "lose": "Losses",
            "miss": "Misses",
            "hit": "Hits",
            "strike": "Strikes",
            "impact_": "Impacts",
            "collide": "Collisions",
            "crash_": "Crashes",
            "smash": "Smashes",
            "break_": "Breaks",
            "fracture": "Fractures",
            "shatter": "Shatters",
            "crack": "Cracks",
            "split_": "Splits",
            "tear": "Tears",
            "rip": "Rips",
            "cut": "Cuts",
            "dice": "Dicing",
            "chop": "Chopping",
            "mince": "Mincing",
            "grind": "Grinding",
            "crush": "Crushing",
            "compress_": "Compression",
            "squeeze": "Squeezing",
            "press": "Pressing",
            "push_": "Pushing",
            "pull": "Pulling",
            "drag": "Dragging",
            "drop": "Dropping",
            "fall": "Falling",
            "rise": "Rising",
            "lift": "Lifting",
            "raise": "Raising",
            "lower": "Lowering",
            "elevate": "Elevation",
            "descend": "Descent",
            "ascend": "Ascent",
            "climb": "Climbing",
            "crawl": "Crawling",
            "walk": "Walking",
            "sprint": "Sprinting",
            "dash": "Dashing",
            "rush": "Rushing",
            "hurry": "Hurrying",
            "speed": "Speed",
            "velocity": "Velocities",
            "acceleration": "Accelerations",
            "deceleration": "Decelerations",
            "jerk": "Jerks",
            "snap": "Snaps",
            "crackle": "Crackles",
            "pop": "Pops",
            "bang": "Bangs",
            "boom": "Booms",
            "crash__": "Crashes",
            "splash": "Splashes",
            "spray": "Sprays",
            "spurt": "Spurts",
            "squirt": "Squirts",
            "drip": "Drips",
            "drop_": "Drops",
            "pour": "Pouring",
            "flow_": "Flows",
            "river": "Rivers",
            "ocean": "Oceans",
            "sea": "Seas",
            "lake": "Lakes",
            "pond": "Ponds",
            "puddle": "Puddles",
            "basin": "Basins",
            "bowl": "Bowls",
            "cup": "Cups",
            "glass": "Glasses",
            "bottle": "Bottles",
            "jar": "Jars",
            "jug": "Jugs",
            "vessel": "Vessels",
            "holder": "Holders",
            "carrier": "Carriers",
            "transporter": "Transporters",
            "conveyor": "Conveyors",
            "pipeline_": "Pipelines",
            "channel_": "Channels",
            "conduit": "Conduits",
            "duct": "Ducts",
            "tube": "Tubes",
            "pipe_": "Pipes",
            "hose": "Hoses",
            "cable": "Cables",
            "wire_": "Wires",
            "cord": "Cords",
            "strand": "Strands",
            "fiber_": "Fibers",
            "filament": "Filaments",
            "string": "Strings",
            "chain_": "Chains",
            "bond": "Bonds",
            "connection": "Connections",
            "tie": "Ties",
            "knot": "Knots",
            "loop_": "Loops",
            "ring_": "Rings",
            "circle": "Circles",
            "ellipse": "Ellipses",
            "oval": "Ovals",
            "arc": "Arcs",
            "curve_": "Curves",
            "bend": "Bends",
            "turn": "Turns",
            "twist": "Twists",
            "spin": "Spins",
            "roll": "Rolls",
            "rotate": "Rotations",
            "revolve": "Revolutions",
            "orbit_": "Orbits",
            "cycle_": "Cycles",
            "period": "Periods",
            "frequency": "Frequencies",
            "wavelength": "Wavelengths",
            "amplitude": "Amplitudes",
            "polarity": "Polarities",
            "charge": "Charges",
            "current": "Currents",
            "voltage": "Voltages",
            "resistance": "Resistances",
            "capacitance": "Capacitances",
            "inductance": "Inductances",
            "impedance": "Impedances",
            "admittance": "Admittances",
            "conductance": "Conductances",
            "susceptance": "Susceptances",
            "reactance": "Reactances",
            "power": "Power",
            "energy": "Energy",
            "work": "Work",
            "force": "Forces",
            "mass": "Mass",
            "weight": "Weights",
            "density": "Densities",
            "volume": "Volumes",
            "length": "Lengths",
            "width": "Widths",
            "height": "Heights",
            "depth": "Depths",
            "thickness": "Thicknesses",
            "diameter": "Diameters",
            "radius": "Radii",
            "circumference": "Circumferences",
            "perimeter": "Perimeters",
            "boundary_": "Boundaries",
            "vertex_": "Vertices",
            "corner": "Corners",
            "angle": "Angles",
            "slope": "Slopes",
            "gradient": "Gradients",
            "incline": "Inclines",
            "decline": "Declines",
            "ascent": "Ascents",
            "descent_": "Descents",
            "elevation_": "Elevations",
            "altitude": "Altitudes",
            "depth_": "Depths",
            "level_": "Levels",
            "layer_": "Layers",
            "stratum": "Strata",
            "tier_": "Tiers",
            "order_": "Orders",
            "family": "Families",
            "genus": "Genera",
            "species": "Species",
            "variety": "Varieties",
            "breed": "Breeds",
            "strain": "Strains",
            "cultivar": "Cultivars",
            "hybrid": "Hybrids",
            "mutant": "Mutants",
            "wildtype": "Wild types",
            "phenotype": "Phenotypes",
            "genotype": "Genotypes",
            "allele": "Alleles",
            "locus": "Loci",
            "gene": "Genes",
            "chromosome": "Chromosomes",
            "dna": "DNA",
            "rna": "RNA",
            "protein": "Proteins",
            "enzyme": "Enzymes",
            "hormone": "Hormones",
            "neurotransmitter": "Neurotransmitters",
            "receptor": "Receptors",
            "ligand": "Ligands",
            "agonist": "Agonists",
            "antagonist": "Antagonists",
            "modulator": "Modulators",
            "inhibitor": "Inhibitors",
            "activator": "Activators",
            "catalyst": "Catalysts",
            "promoter": "Promoters",
            "suppressor": "Suppressors",
            "enhancer": "Enhancers",
            "silencer": "Silencers",
            "operator": "Operators",
            "operon": "Operons",
            "pathway": "Pathways",
            "network_": "Networks",
            "system_": "Systems",
            "organ": "Organs",
            "tissue": "Tissues",
            "cell_": "Cells",
            "organelle": "Organelles",
            "molecule": "Molecules",
            "atom": "Atoms",
            "particle": "Particles",
            "quark": "Quarks",
            "lepton": "Leptons",
            "boson": "Bosons",
            "fermion": "Fermions",
            "hadron": "Hadrons",
            "baryon": "Baryons",
            "meson": "Mesons",
            "nucleon": "Nucleons",
            "proton": "Protons",
            "neutron": "Neutrons",
            "electron": "Electrons",
            "photon": "Photons",
            "gluon": "Gluons",
            "wboson": "W bosons",
            "zboson": "Z bosons",
            "higgs": "Higgs bosons",
            "graviton": "Gravitons",
            "tachyon": "Tachyons",
            "neutrino": "Neutrinos",
            "muon": "Muons",
            "tau": "Taus",
            "pion": "Pions",
            "kaon": "Kaons",
            "lambda": "Lambda particles",
            "sigma": "Sigma particles",
            "xi": "Xi particles",
            "omega": "Omega particles",
            "delta": "Delta particles",
            "upsilon": "Upsilon particles",
            "chi": "Chi particles",
            "psi": "Psi particles",
            "phi": "Phi particles",
            "eta": "Eta particles",
            "rho": "Rho particles",
            "theta": "Theta particles",
            "iota": "Iota particles",
            "kappa": "Kappa particles",
            "nu": "Nu particles",
            "omicron": "Omicron particles",
            "pi": "Pi particles",
            "beta": "Beta particles",
            "gamma": "Gamma particles",
            "alpha": "Alpha particles",
            "epsilon": "Epsilon particles",
            "zeta": "Zeta particles",
            "omicron_": "Omicron",
            "tau_": "Tau",
            "pi_": "Pi",
            "mu_": "Mu",
            "nu_": "Nu",
            "xi_": "Xi",
            "sigma_": "Sigma",
            "lambda_": "Lambda",
            "delta_": "Delta",
            "gamma_": "Gamma",
            "beta_": "Beta",
            "alpha_": "Alpha",
            "omega_": "Omega",
            "theta_": "Theta",
            "phi_": "Phi",
            "psi_": "Psi",
            "chi_": "Chi",
            "upsilon_": "Upsilon",
            "iota_": "Iota",
            "kappa_": "Kappa",
            "omicron__": "Omicron",
            "rho_": "Rho",
            "eta_": "Eta",
            "zeta_": "Zeta",
            "epsilon_": "Epsilon",
        }
        for key, desc in mapping.items():
            if key in name_lower or name_lower.startswith(key.rstrip("_")):
                return desc
        return name.replace("_", " ").capitalize() + " layer"

    def _identify_core_subgraphs(self, subgraphs: list[SubgraphInfo]) -> list[str]:
        """Identify subgraphs that are most depended upon."""
        import_counts: Counter = Counter()
        for sg in subgraphs:
            for other in subgraphs:
                if other.id == sg.id:
                    continue
                if sg.id in other.imports_from:
                    import_counts[sg.id] += 1
        return [sg_id for sg_id, _ in import_counts.most_common(5)]

    def _identify_shared_modules(
        self, subgraphs: list[SubgraphInfo], ast_cache: dict[str, Any]
    ) -> list[dict]:
        """Identify modules that are imported by many subgraphs."""
        module_importers: dict[str, set[str]] = defaultdict(set)
        for abs_file, module in ast_cache.items():
            for imp in module.get("imports", []):
                mod_name = imp.get("module", "")
                if mod_name:
                    # Find which subgraph imports this
                    for sg in subgraphs:
                        rel_file = self._rel(abs_file)
                        if rel_file in sg.files:
                            module_importers[mod_name].add(sg.id)
                            break

        shared = []
        for mod_name, importers in module_importers.items():
            if len(importers) >= 3:
                shared.append({"name": mod_name, "imported_by": len(importers)})

        shared.sort(key=lambda x: -x["imported_by"])
        return shared[:20]

    def _identify_entry_points(self, rel_files: list[str], ast_cache: dict[str, Any]) -> list[str]:
        """Find entry point files (e.g., __main__, cli main functions)."""
        entry_points = []
        for f in rel_files:
            if f.endswith("__main__.py") or f.endswith("main.py"):
                entry_points.append(f)
                continue
            abs_file = str(self.root_path / f)
            module = ast_cache.get(abs_file)
            if module:
                for func in module.get("functions", []):
                    if func.get("name") in ("main", "cli", "run", "start"):
                        entry_points.append(f)
                        break
        return sorted(set(entry_points))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _rel(self, path: str | Path) -> str:
        """Make path relative to root."""
        try:
            return str(Path(path).relative_to(self.root_path)).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")

    def _abs(self, path: str | Path) -> str:
        """Make path absolute."""
        p = Path(path)
        if p.is_absolute():
            return str(p).replace("\\", "/")
        return str(self.root_path / p).replace("\\", "/")

    def _detect_language(self, file_path: str) -> str:
        """Detect language from file extension."""
        ext = Path(file_path).suffix.lower()
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".hpp": "cpp",
            ".cc": "cpp",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".r": "r",
            ".cs": "csharp",
            ".fs": "fsharp",
            ".elm": "elm",
        }
        return ext_map.get(ext, "unknown")
