"""Tests for code indexing service."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from pilotcode.services.code_index import (
    CodeIndexer,
    CodeIndex,
    Symbol,
    get_code_indexer,
)


class TestSymbol:
    """Tests for Symbol dataclass."""
    
    def test_symbol_creation(self):
        """Test creating a symbol."""
        symbol = Symbol(
            name="test_func",
            symbol_type="function",
            file_path="test.py",
            line_number=10,
            column=4
        )
        
        assert symbol.name == "test_func"
        assert symbol.symbol_type == "function"
        assert symbol.line_number == 10


class TestCodeIndex:
    """Tests for CodeIndex."""
    
    def test_find_symbol(self):
        """Test finding symbols."""
        index = CodeIndex()
        index.symbols = [
            Symbol("func1", "function", "file.py", 1, 0),
            Symbol("func2", "function", "file.py", 2, 0),
            Symbol("MyClass", "class", "file.py", 5, 0),
        ]
        
        results = index.find_symbol("func1")
        assert len(results) == 1
        assert results[0].name == "func1"
    
    def test_find_symbol_with_type(self):
        """Test finding symbols with type filter."""
        index = CodeIndex()
        index.symbols = [
            Symbol("test", "function", "file.py", 1, 0),
            Symbol("test", "class", "file.py", 5, 0),
        ]
        
        results = index.find_symbol("test", symbol_type="class")
        assert len(results) == 1
        assert results[0].symbol_type == "class"


class TestCodeIndexer:
    """Tests for CodeIndexer."""
    
    def test_init(self):
        """Test initialization."""
        indexer = CodeIndexer()
        assert indexer._index is not None
    
    def test_get_language(self):
        """Test language detection."""
        indexer = CodeIndexer()
        
        assert indexer._get_language("test.py") == "python"
        assert indexer._get_language("test.js") == "javascript"
        assert indexer._get_language("test.ts") == "typescript"
        assert indexer._get_language("test.java") == "java"
        assert indexer._get_language("test.txt") is None
    
    @pytest.mark.asyncio
    async def test_index_python_file(self):
        """Test indexing a Python file."""
        indexer = CodeIndexer()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('''
def hello():
    pass

class MyClass:
    def method(self):
        pass

world = "test"
''')
            temp_path = f.name
        
        try:
            symbols = await indexer.index_file(temp_path)
            
            # Should find class and functions
            names = [s.name for s in symbols]
            assert "MyClass" in names
            assert "hello" in names
            assert "method" in names
        finally:
            Path(temp_path).unlink()
    
    @pytest.mark.asyncio
    async def test_index_javascript_file(self):
        """Test indexing a JavaScript file."""
        indexer = CodeIndexer()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write('''
function hello() {
    return "world";
}

class MyClass {
    method() {
        return 42;
    }
}
''')
            temp_path = f.name
        
        try:
            symbols = await indexer.index_file(temp_path)
            
            names = [s.name for s in symbols]
            assert "MyClass" in names
            assert "hello" in names
        finally:
            Path(temp_path).unlink()
    
    @pytest.mark.asyncio
    async def test_index_directory(self):
        """Test indexing a directory."""
        indexer = CodeIndexer()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            (Path(tmpdir) / "file1.py").write_text("def func1(): pass")
            (Path(tmpdir) / "file2.py").write_text("def func2(): pass")
            
            indexed = await indexer.index_directory(tmpdir, pattern="*.py")
            
            assert indexed == 2
            
            stats = indexer.get_index_stats()
            assert stats["indexed_files"] == 2
    
    @pytest.mark.asyncio
    async def test_search_symbols(self):
        """Test searching symbols."""
        indexer = CodeIndexer()
        
        # Manually add symbols
        indexer._index.symbols = [
            Symbol("hello_world", "function", "file.py", 1, 0),
            Symbol("hello_test", "function", "file.py", 2, 0),
            Symbol("goodbye", "function", "file.py", 3, 0),
        ]
        
        results = indexer.search_symbols("hello")
        
        assert len(results) == 2
        assert all("hello" in s.name for s in results)
    
    def test_get_index_stats(self):
        """Test getting index statistics."""
        indexer = CodeIndexer()
        
        indexer._index.symbols = [
            Symbol("func1", "function", "file.py", 1, 0),
            Symbol("func2", "function", "file.py", 2, 0),
            Symbol("MyClass", "class", "file.py", 5, 0),
        ]
        
        stats = indexer.get_index_stats()
        
        assert stats["total_symbols"] == 3
        assert stats["symbol_types"]["function"] == 2
        assert stats["symbol_types"]["class"] == 1
    
    def test_clear_index(self):
        """Test clearing the index."""
        indexer = CodeIndexer()
        
        indexer._index.symbols = [Symbol("test", "function", "file.py", 1, 0)]
        indexer._indexed_files.add("file.py")
        
        indexer.clear_index()
        
        assert len(indexer._index.symbols) == 0
        assert len(indexer._indexed_files) == 0
    
    @pytest.mark.asyncio
    async def test_remove_file(self):
        """Test removing a file from index."""
        indexer = CodeIndexer()
        
        indexer._index.symbols = [
            Symbol("func1", "function", "file1.py", 1, 0),
            Symbol("func2", "function", "file2.py", 1, 0),
        ]
        indexer._indexed_files.add("file1.py")
        indexer._indexed_files.add("file2.py")
        
        await indexer.remove_file("file1.py")
        
        assert len(indexer._index.symbols) == 1
        assert indexer._index.symbols[0].file_path == "file2.py"
        assert "file1.py" not in indexer._indexed_files


class TestGlobalFunctions:
    """Tests for global functions."""
    
    def test_get_code_indexer(self):
        """Test getting global indexer."""
        indexer1 = get_code_indexer()
        indexer2 = get_code_indexer()
        assert indexer1 is indexer2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
