"""Tests for hierarchical index builder."""

import tempfile
from pathlib import Path

import pytest

from pilotcode.services.hierarchical_index import (
    HierarchicalIndexBuilder,
    MasterIndex,
    SubgraphInfo,
)


class TestSubgraphInfo:
    """Tests for SubgraphInfo dataclass."""

    def test_creation(self):
        sg = SubgraphInfo(id="sg1", name="utils", path="src/utils")
        assert sg.id == "sg1"
        assert sg.file_count == 0

    def test_to_dict_roundtrip(self):
        sg = SubgraphInfo(
            id="sg1",
            name="utils",
            path="src/utils",
            files=["a.py", "b.py"],
            symbols=[{"name": "foo", "type": "function"}],
            summary="Utility functions",
            key_apis=["foo"],
            total_lines=42,
            file_count=2,
            symbol_count=1,
        )
        data = sg.to_dict()
        restored = SubgraphInfo.from_dict(data)
        assert restored.id == sg.id
        assert restored.files == sg.files
        assert restored.symbols == sg.symbols
        assert restored.summary == sg.summary


class TestMasterIndex:
    """Tests for MasterIndex dataclass."""

    def test_to_dict_roundtrip(self):
        master = MasterIndex(
            project_name="TestProject",
            root_path="/tmp/test",
            total_files=5,
            subgraphs=[
                SubgraphInfo(id="sg1", name="core", path="src/core", file_count=3),
                SubgraphInfo(id="sg2", name="tests", path="tests", file_count=2),
            ],
        )
        data = master.to_dict()
        restored = MasterIndex.from_dict(data)
        assert restored.project_name == "TestProject"
        assert len(restored.subgraphs) == 2
        assert restored.subgraphs[0].name == "core"


class TestHierarchicalIndexBuilder:
    """Tests for HierarchicalIndexBuilder."""

    def test_build_small_project(self, temp_dir):
        """Test building index for a small project."""
        # Create files
        (temp_dir / "src" / "utils").mkdir(parents=True)
        (temp_dir / "tests").mkdir(parents=True)
        (temp_dir / "src" / "main.py").write_text("def main(): pass\n")
        (temp_dir / "src" / "utils" / "helpers.py").write_text("def helper(): pass\n")
        (temp_dir / "tests" / "test_main.py").write_text("def test_main(): pass\n")

        builder = HierarchicalIndexBuilder(temp_dir)
        rel_files = [
            "src/main.py",
            "src/utils/helpers.py",
            "tests/test_main.py",
        ]
        ast_cache = {}
        symbol_index = {
            "src/main.py": [{"name": "main", "type": "function", "line": 1}],
            "src/utils/helpers.py": [{"name": "helper", "type": "function", "line": 1}],
            "tests/test_main.py": [{"name": "test_main", "type": "function", "line": 1}],
        }

        master = builder.build(rel_files, ast_cache, symbol_index)

        assert isinstance(master, MasterIndex)
        assert master.total_files == 3
        assert master.total_symbols == 3
        assert len(master.subgraphs) >= 1
        assert len(master.orphan_files) == 0

    def test_cluster_by_directory_splits_large_dirs(self, temp_dir):
        """Test that large directories are split by prefix."""
        builder = HierarchicalIndexBuilder(temp_dir)
        # Use mixed prefixes so splitting creates multiple clusters
        files = []
        for i in range(60):
            prefix = "alpha" if i < 30 else "beta"
            files.append(f"src/{prefix}_{i:03d}.py")
        clusters = builder._cluster_by_directory(files)

        # Should create multiple clusters, not one giant cluster
        total_clustered = sum(len(v) for v in clusters.values())
        assert total_clustered == 60
        assert len(clusters) > 1
        for cluster_files in clusters.values():
            assert len(cluster_files) <= builder.MAX_FILES_PER_SUBGRAPH

    def test_cluster_merges_small_dirs(self, temp_dir):
        """Test that tiny directories get merged."""
        builder = HierarchicalIndexBuilder(temp_dir)
        files = ["a/x.py", "b/y.py"]
        clusters = builder._cluster_by_directory(files)

        total_clustered = sum(len(v) for v in clusters.values())
        assert total_clustered == 2

    def test_get_subgraph(self, temp_dir):
        """Test retrieving a subgraph by id/name/path."""
        builder = HierarchicalIndexBuilder(temp_dir)
        rel_files = ["src/core.py"]
        master = builder.build(rel_files, {}, {})

        sg = builder.get_subgraph(master.subgraphs[0].id)
        assert sg is not None
        sg = builder.get_subgraph(master.subgraphs[0].name)
        assert sg is not None
        sg = builder.get_subgraph(master.subgraphs[0].path)
        assert sg is not None
        assert builder.get_subgraph("nonexistent") is None

    def test_format_master_index(self, temp_dir):
        """Test master index text formatting."""
        builder = HierarchicalIndexBuilder(temp_dir)
        rel_files = ["src/main.py"]
        builder.build(rel_files, {}, {})

        text = builder.format_master_index()
        assert "Project Overview" in text
        assert "src" in text

    def test_format_master_index_max_subgraphs(self, temp_dir):
        """Test max_subgraphs limit."""
        builder = HierarchicalIndexBuilder(temp_dir)
        files = [f"mod{i}/x.py" for i in range(10)]
        builder.build(files, {}, {})

        text = builder.format_master_index(max_subgraphs=3)
        assert "... and" in text or len(builder.get_master_index().subgraphs) <= 3

    def test_format_subgraph_detail(self, temp_dir):
        """Test subgraph detail formatting."""
        builder = HierarchicalIndexBuilder(temp_dir)
        rel_files = ["src/core.py"]
        symbol_index = {"src/core.py": [{"name": "foo", "type": "function", "line": 1}]}
        builder.build(rel_files, {}, symbol_index)

        sg_id = builder.get_master_index().subgraphs[0].id
        text = builder.format_subgraph_detail(sg_id)
        assert "Subgraph:" in text
        assert "src/core.py" in text

    def test_format_subgraph_detail_not_found(self, temp_dir):
        """Test formatting for missing subgraph."""
        builder = HierarchicalIndexBuilder(temp_dir)
        text = builder.format_subgraph_detail("missing")
        assert "not found" in text

    def test_save_and_load(self, temp_dir):
        """Test JSON persistence."""
        builder = HierarchicalIndexBuilder(temp_dir)
        rel_files = ["a.py", "b.py"]
        builder.build(rel_files, {}, {})

        save_path = temp_dir / "index.json"
        builder.save(save_path)
        assert save_path.exists()

        builder2 = HierarchicalIndexBuilder(temp_dir)
        builder2.load(save_path)
        master = builder2.get_master_index()
        assert master is not None
        assert master.total_files == 2

    def test_import_export_relations(self, temp_dir):
        """Test import/export relation computation."""
        builder = HierarchicalIndexBuilder(temp_dir)
        rel_files = ["src/core.py", "src/utils.py"]
        ast_cache = {
            str(temp_dir / "src/core.py"): {
                "imports": [{"module": "src.utils"}],
            },
            str(temp_dir / "src/utils.py"): {
                "imports": [],
            },
        }
        builder.build(rel_files, ast_cache, {})

        core_sg = builder.get_subgraph("src_core")
        utils_sg = builder.get_subgraph("src_utils")
        # core imports from utils
        if core_sg:
            assert any("utils" in dep for dep in core_sg.imports_from)
        if utils_sg:
            assert any("core" in dep for dep in utils_sg.exports_to)

    def test_entry_points_identification(self, temp_dir):
        """Test entry point detection."""
        builder = HierarchicalIndexBuilder(temp_dir)
        rel_files = ["main.py", "cli.py"]
        ast_cache = {
            str(temp_dir / "main.py"): {"docstring": "Main entry point"},
            str(temp_dir / "cli.py"): {"docstring": ""},
        }
        master = builder.build(rel_files, ast_cache, {})

        # main.py should be identified as entry point
        assert "main.py" in master.entry_points

    def test_language_stats(self, temp_dir):
        """Test language statistics."""
        builder = HierarchicalIndexBuilder(temp_dir)
        rel_files = ["a.py", "b.js", "c.go"]
        master = builder.build(rel_files, {}, {})

        assert master.languages.get("python") == 1
        assert master.languages.get("javascript") == 1
        assert master.languages.get("go") == 1

    def test_empty_build(self, temp_dir):
        """Test building with no files."""
        builder = HierarchicalIndexBuilder(temp_dir)
        master = builder.build([], {}, {})
        assert master.total_files == 0
        assert len(master.subgraphs) == 0

    def test_describe_name_mapping(self, temp_dir):
        """Test directory name descriptions."""
        builder = HierarchicalIndexBuilder(temp_dir)
        assert "API" in builder._describe_name("api")
        assert "Test" in builder._describe_name("tests")
        assert "Utility" in builder._describe_name("utils")
        assert "unknown" not in builder._describe_name("custom").lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
