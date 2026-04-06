"""Tests for FileSelector Tool."""

import pytest
import os
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from pilotcode.tools.file_selector import (
    FileSelectorInput,
    FileSelectorOutput,
    FileInfo,
    SortBy,
    SortOrder,
    select_files,
    load_gitignore,
    is_gitignored,
    collect_files,
    apply_filters,
    sort_files,
    is_binary,
    get_preview,
    file_selector_call,
)
from pilotcode.tools.base import ToolUseContext


# Fixtures
@pytest.fixture
def temp_dir():
    """Create a temporary directory with test files."""
    temp_path = tempfile.mkdtemp()
    
    # Create test files
    (Path(temp_path) / "file1.py").write_text("print('hello')\nprint('world')")
    (Path(temp_path) / "file2.py").write_text("def foo():\n    pass")
    (Path(temp_path) / "readme.md").write_text("# README\n\nThis is a test")
    (Path(temp_path) / "config.json").write_text('{"key": "value"}')
    (Path(temp_path) / "large_file.txt").write_text("x" * 10000)
    
    # Create subdirectory
    subdir = Path(temp_path) / "subdir"
    subdir.mkdir()
    (subdir / "nested.py").write_text("# nested file")
    (subdir / "data.csv").write_text("a,b,c\n1,2,3")
    
    # Create hidden file
    (Path(temp_path) / ".hidden").write_text("hidden content")
    
    yield temp_path
    
    # Cleanup
    shutil.rmtree(temp_path)


@pytest.fixture
def tool_context():
    """Create a tool context for testing."""
    return ToolUseContext()


# Test FileInfo dataclass
class TestFileInfo:
    """Test FileInfo dataclass."""
    
    def test_file_info_creation(self):
        """Test creating FileInfo."""
        info = FileInfo(
            path="/test/file.py",
            name="file.py",
            size=1024,
            modified=datetime.now(),
            is_dir=False,
            extension=".py"
        )
        assert info.path == "/test/file.py"
        assert info.name == "file.py"
        assert info.size == 1024
        assert info.is_dir is False
        assert info.extension == ".py"
    
    def test_size_human_bytes(self):
        """Test human-readable size for bytes."""
        info = FileInfo(
            path="/test/file.txt",
            name="file.txt",
            size=500,
            modified=datetime.now(),
            is_dir=False
        )
        assert "B" in info.size_human
        assert "500" in info.size_human
    
    def test_size_human_kb(self):
        """Test human-readable size for kilobytes."""
        info = FileInfo(
            path="/test/file.txt",
            name="file.txt",
            size=2048,
            modified=datetime.now(),
            is_dir=False
        )
        assert "KB" in info.size_human
    
    def test_size_human_mb(self):
        """Test human-readable size for megabytes."""
        info = FileInfo(
            path="/test/file.txt",
            name="file.txt",
            size=5 * 1024 * 1024,
            modified=datetime.now(),
            is_dir=False
        )
        assert "MB" in info.size_human
    
    def test_modified_str(self):
        """Test formatted modification time."""
        now = datetime(2024, 1, 15, 10, 30)
        info = FileInfo(
            path="/test/file.txt",
            name="file.txt",
            size=100,
            modified=now,
            is_dir=False
        )
        assert "2024-01-15" in info.modified_str
        assert "10:30" in info.modified_str


# Test basic file selection
class TestFileSelectorBasic:
    """Test basic FileSelector functionality."""
    
    @pytest.mark.asyncio
    async def test_select_all_files(self, temp_dir, tool_context):
        """Test selecting all files."""
        input_data = FileSelectorInput(
            directory=temp_dir,
            pattern="*",
            include_hidden=True
        )
        
        result = await file_selector_call(
            input_data, tool_context, lambda *args: True, None, lambda *args: None
        )
        
        assert result.error is None
        assert result.data is not None
        # Should find all files including hidden
        assert result.data.total_count >= 6
    
    @pytest.mark.asyncio
    async def test_select_python_files(self, temp_dir, tool_context):
        """Test selecting Python files."""
        input_data = FileSelectorInput(
            directory=temp_dir,
            pattern="*.py"
        )
        
        result = await file_selector_call(
            input_data, tool_context, lambda *args: True, None, lambda *args: None
        )
        
        assert result.error is None
        # Should find file1.py, file2.py, and subdir/nested.py
        py_files = [f for f in result.data.files if f["path"].endswith(".py")]
        assert len(py_files) == 3
    
    @pytest.mark.asyncio
    async def test_select_by_extension(self, temp_dir, tool_context):
        """Test selecting by extension list."""
        input_data = FileSelectorInput(
            directory=temp_dir,
            extensions=["py", "md"]
        )
        
        result = await file_selector_call(
            input_data, tool_context, lambda *args: True, None, lambda *args: None
        )
        
        assert result.error is None
        
        for file in result.data.files:
            if not file["is_directory"]:
                assert file["extension"] in [".py", ".md"]
    
    @pytest.mark.asyncio
    async def test_nonexistent_directory(self, tool_context):
        """Test with non-existent directory."""
        input_data = FileSelectorInput(
            directory="/nonexistent/path/12345"
        )
        
        result = await file_selector_call(
            input_data, tool_context, lambda *args: True, None, lambda *args: None
        )
        
        assert result.error is not None
        assert "not found" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_file_as_directory(self, temp_dir, tool_context):
        """Test with file path instead of directory."""
        input_data = FileSelectorInput(
            directory=str(Path(temp_dir) / "file1.py")
        )
        
        result = await file_selector_call(
            input_data, tool_context, lambda *args: True, None, lambda *args: None
        )
        
        assert result.error is not None
        assert "not a directory" in result.error.lower()


# Test filtering
class TestFileSelectorFiltering:
    """Test FileSelector filtering options."""
    
    def test_exclude_patterns(self, temp_dir):
        """Test exclude patterns."""
        input_data = FileSelectorInput(
            directory=temp_dir,
            pattern="*",
            exclude_patterns=["*.py"]
        )
        
        files = collect_files(Path(temp_dir), input_data, [])
        files = apply_filters(files, input_data)
        
        for file in files:
            assert not file.path.endswith(".py")
    
    def test_regex_filter(self, temp_dir):
        """Test regex filtering."""
        input_data = FileSelectorInput(
            directory=temp_dir,
            regex=r"^file\d+\.py$"
        )
        
        files = collect_files(Path(temp_dir), input_data, [])
        files = apply_filters(files, input_data)
        
        py_files = [f for f in files if f.path.endswith(".py")]
        assert len(py_files) == 2  # file1.py and file2.py
    
    def test_min_size_filter(self, temp_dir):
        """Test minimum size filter."""
        input_data = FileSelectorInput(
            directory=temp_dir,
            min_size=5000  # 5KB
        )
        
        files = collect_files(Path(temp_dir), input_data, [])
        files = apply_filters(files, input_data)
        
        # Should only find large_file.txt
        txt_files = [f for f in files if f.name == "large_file.txt"]
        assert len(txt_files) == 1
    
    def test_max_size_filter(self, temp_dir):
        """Test maximum size filter."""
        input_data = FileSelectorInput(
            directory=temp_dir,
            max_size=100  # 100 bytes
        )
        
        files = collect_files(Path(temp_dir), input_data, [])
        files = apply_filters(files, input_data)
        
        for file in files:
            if not file.is_dir:
                assert file.size <= 100
    
    def test_hidden_files(self, temp_dir):
        """Test hidden files inclusion."""
        # Without hidden files
        input_data = FileSelectorInput(
            directory=temp_dir,
            include_hidden=False
        )
        
        files = collect_files(Path(temp_dir), input_data, [])
        
        hidden_files = [f for f in files if f.name.startswith(".")]
        assert len(hidden_files) == 0
        
        # With hidden files
        input_data = FileSelectorInput(
            directory=temp_dir,
            include_hidden=True
        )
        
        files = collect_files(Path(temp_dir), input_data, [])
        
        hidden_files = [f for f in files if f.name.startswith(".")]
        assert len(hidden_files) == 1  # .hidden file


# Test sorting
class TestFileSelectorSorting:
    """Test FileSelector sorting options."""
    
    def test_sort_by_name_asc(self, temp_dir):
        """Test sorting by name ascending."""
        input_data = FileSelectorInput(
            directory=temp_dir,
            sort_by=SortBy.NAME,
            sort_order=SortOrder.ASC
        )
        
        files = collect_files(Path(temp_dir), input_data, [])
        files = sort_files(files, input_data.sort_by, input_data.sort_order)
        
        names = [f.name for f in files if not f.is_dir]
        assert names == sorted(names)
    
    def test_sort_by_name_desc(self, temp_dir):
        """Test sorting by name descending."""
        input_data = FileSelectorInput(
            directory=temp_dir,
            sort_by=SortBy.NAME,
            sort_order=SortOrder.DESC
        )
        
        files = collect_files(Path(temp_dir), input_data, [])
        files = sort_files(files, input_data.sort_by, input_data.sort_order)
        
        names = [f.name for f in files if not f.is_dir]
        assert names == sorted(names, reverse=True)
    
    def test_sort_by_size(self, temp_dir):
        """Test sorting by size."""
        input_data = FileSelectorInput(
            directory=temp_dir,
            sort_by=SortBy.SIZE,
            sort_order=SortOrder.DESC
        )
        
        files = collect_files(Path(temp_dir), input_data, [])
        files = sort_files(files, input_data.sort_by, input_data.sort_order)
        
        sizes = [f.size for f in files if not f.is_dir]
        assert sizes == sorted(sizes, reverse=True)
    
    def test_directories_first(self, temp_dir):
        """Test that directories come first when sorting by name."""
        input_data = FileSelectorInput(
            directory=temp_dir,
            sort_by=SortBy.NAME,
            sort_order=SortOrder.ASC
        )
        
        files = collect_files(Path(temp_dir), input_data, [])
        files = sort_files(files, input_data.sort_by, input_data.sort_order)
        
        # First items should be directories
        if len(files) > 0:
            dirs_first = all(
                files[i].is_dir or not files[i+1].is_dir
                for i in range(len(files) - 1)
            )
            assert dirs_first is True


# Test recursive/non-recursive
class TestFileSelectorRecursive:
    """Test recursive vs non-recursive search."""
    
    def test_recursive_search(self, temp_dir):
        """Test recursive file search."""
        input_data = FileSelectorInput(
            directory=temp_dir,
            pattern="*.py",
            recursive=True
        )
        
        files = collect_files(Path(temp_dir), input_data, [])
        
        # Should find Python files in subdirectories
        paths = [f.path for f in files]
        assert any("subdir" in p for p in paths)
    
    def test_non_recursive_search(self, temp_dir):
        """Test non-recursive file search."""
        input_data = FileSelectorInput(
            directory=temp_dir,
            pattern="*.py",
            recursive=False
        )
        
        files = collect_files(Path(temp_dir), input_data, [])
        py_files = [f for f in files if f.path.endswith(".py")]
        
        # Should only find Python files in root
        assert len(py_files) == 2  # file1.py and file2.py
        for file in py_files:
            assert "subdir" not in file.path


# Test preview
class TestFileSelectorPreview:
    """Test file preview functionality."""
    
    def test_preview_text_file(self, temp_dir):
        """Test file preview."""
        filepath = str(Path(temp_dir) / "file1.py")
        preview = get_preview(filepath, 2)
        
        assert preview is not None
        assert "print('hello')" in preview
    
    def test_preview_binary_file(self, temp_dir):
        """Test preview for binary file."""
        # Create a binary file
        binary_path = Path(temp_dir) / "binary.dat"
        binary_path.write_bytes(bytes(range(256)))
        
        preview = get_preview(str(binary_path), 10)
        
        assert "[Binary file]" == preview


# Test gitignore
class TestFileSelectorGitignore:
    """Test .gitignore handling."""
    
    def test_load_gitignore(self, temp_dir):
        """Test loading .gitignore."""
        # Create .gitignore
        gitignore = Path(temp_dir) / ".gitignore"
        gitignore.write_text("*.pyc\n__pycache__/\n")
        
        patterns = load_gitignore(Path(temp_dir))
        
        assert "*.pyc" in patterns
        assert "__pycache__/" in patterns
    
    def test_is_gitignored(self, temp_dir):
        """Test gitignore matching."""
        patterns = ["*.pyc", "__pycache__/"]
        
        # Create test paths
        pyc_file = Path(temp_dir) / "test.pyc"
        pycache = Path(temp_dir) / "__pycache__"
        normal_file = Path(temp_dir) / "test.py"
        
        assert is_gitignored(pyc_file, Path(temp_dir), patterns) is True
        assert is_gitignored(pycache, Path(temp_dir), patterns) is True
        assert is_gitignored(normal_file, Path(temp_dir), patterns) is False
    
    def test_respect_gitignore(self, temp_dir):
        """Test respecting .gitignore patterns."""
        # Create .gitignore
        gitignore = Path(temp_dir) / ".gitignore"
        gitignore.write_text("*.pyc\n__pycache__/\n")
        
        # Create files that should be ignored
        (Path(temp_dir) / "test.pyc").write_text("compiled")
        pycache = Path(temp_dir) / "__pycache__"
        pycache.mkdir()
        (pycache / "cache.pyc").write_text("cache")
        
        input_data = FileSelectorInput(
            directory=temp_dir,
            pattern="*",
            respect_gitignore=True
        )
        
        patterns = load_gitignore(Path(temp_dir))
        files = collect_files(Path(temp_dir), input_data, patterns)
        
        paths = [f.path for f in files]
        assert not any(p.endswith(".pyc") for p in paths)
        assert not any("__pycache__" in p for p in paths)
    
    def test_ignore_gitignore(self, temp_dir):
        """Test ignoring .gitignore patterns."""
        # Create .gitignore
        gitignore = Path(temp_dir) / ".gitignore"
        gitignore.write_text("*.pyc\n")
        
        # Create file that would be ignored
        (Path(temp_dir) / "test.pyc").write_text("compiled")
        
        input_data = FileSelectorInput(
            directory=temp_dir,
            pattern="*.pyc",
            respect_gitignore=False
        )
        
        files = collect_files(Path(temp_dir), input_data, [])
        files = apply_filters(files, input_data)
        
        assert len(files) == 1
        assert files[0].name == "test.pyc"


# Test max results
class TestFileSelectorLimits:
    """Test result limiting."""
    
    @pytest.mark.asyncio
    async def test_max_results(self, temp_dir, tool_context):
        """Test max_results limit."""
        input_data = FileSelectorInput(
            directory=temp_dir,
            pattern="*",
            max_results=3
        )
        
        result = await file_selector_call(
            input_data, tool_context, lambda *args: True, None, lambda *args: None
        )
        
        assert result.error is None
        assert len(result.data.files) <= 3
        assert result.data.total_count >= 3  # Total should reflect all matches


# Test output format
class TestFileSelectorOutput:
    """Test output format."""
    
    @pytest.mark.asyncio
    async def test_output_structure(self, temp_dir, tool_context):
        """Test output has correct structure."""
        input_data = FileSelectorInput(
            directory=temp_dir,
            pattern="file1.py"
        )
        
        result = await file_selector_call(
            input_data, tool_context, lambda *args: True, None, lambda *args: None
        )
        
        assert result.error is None
        data = result.data
        
        assert hasattr(data, 'files')
        assert hasattr(data, 'total_count')
        assert hasattr(data, 'total_size')
        assert hasattr(data, 'directory')
        
        if len(data.files) > 0:
            file_info = data.files[0]
            assert "path" in file_info
            assert "name" in file_info
            assert "size" in file_info
            assert "size_human" in file_info
            assert "modified" in file_info
            assert "is_directory" in file_info
            assert "extension" in file_info


# Test is_binary
class TestIsBinary:
    """Test binary file detection."""
    
    def test_text_file_not_binary(self, temp_dir):
        """Test text file detection."""
        text_file = Path(temp_dir) / "text.txt"
        text_file.write_text("This is a text file\nwith multiple lines")
        
        assert is_binary(str(text_file)) is False
    
    def test_binary_file_detection(self, temp_dir):
        """Test binary file detection."""
        binary_file = Path(temp_dir) / "binary.dat"
        binary_file.write_bytes(bytes(range(256)))
        
        assert is_binary(str(binary_file)) is True
    
    def test_binary_with_null_bytes(self, temp_dir):
        """Test binary detection with null bytes."""
        binary_file = Path(temp_dir) / "binary_null.dat"
        binary_file.write_bytes(b"Hello\x00World")
        
        assert is_binary(str(binary_file)) is True
