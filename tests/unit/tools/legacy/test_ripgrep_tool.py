"""Tests for ripgrep tool integration."""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from pilotcode.tools.ripgrep_tool import (
    RipgrepRunner,
    RipgrepInput,
    RipgrepOutput,
    RipgrepMatch,
    get_ripgrep_runner,
    ripgrep_call,
)


class TestRipgrepRunner:
    """Tests for RipgrepRunner."""
    
    def test_init(self):
        """Test initialization."""
        runner = RipgrepRunner()
        assert runner._rg_path is None
        assert runner._checked is False
    
    def test_find_rg_not_available(self):
        """Test when ripgrep is not available."""
        runner = RipgrepRunner()
        
        with patch('shutil.which', return_value=None):
            result = runner._find_rg()
        
        assert result is None
        assert runner._rg_path is None
    
    def test_find_rg_available(self):
        """Test finding system ripgrep."""
        runner = RipgrepRunner()
        
        with patch('shutil.which', return_value='/usr/bin/rg'):
            result = runner._find_rg()
        
        assert result == '/usr/bin/rg'
        assert runner._rg_path == '/usr/bin/rg'
    
    def test_is_available(self):
        """Test checking availability."""
        runner = RipgrepRunner()
        
        with patch.object(runner, '_find_rg', return_value='/usr/bin/rg'):
            assert runner.is_available() is True
        
        with patch.object(runner, '_find_rg', return_value=None):
            assert runner.is_available() is False
    
    @pytest.mark.asyncio
    async def test_search_not_available(self):
        """Test search when ripgrep not available."""
        runner = RipgrepRunner()
        
        with patch.object(runner, '_find_rg', return_value=None):
            result = await runner.search("test", ".")
        
        assert result.error is not None
        assert "not found" in result.error
        assert result.total_matches == 0
    
    @pytest.mark.asyncio
    async def test_search_success(self):
        """Test successful search."""
        runner = RipgrepRunner()
        
        # Create temp directory with test file
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("hello world\ntest line\n")
            
            # Mock subprocess
            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.stdout.readline = AsyncMock(side_effect=[
                b'{"type":"match","data":{"path":{"text":"test.txt"},"line_number":1,"lines":{"text":"hello world"},"submatches":[]}}\n',
                b''  # EOF
            ])
            mock_process.communicate = AsyncMock(return_value=(b'', b''))
            mock_process.wait = AsyncMock(return_value=0)
            
            with patch('asyncio.create_subprocess_exec', return_value=mock_process):
                with patch.object(runner, '_find_rg', return_value='/usr/bin/rg'):
                    result = await runner.search("hello", tmpdir)
        
        assert result.error is None
    
    def test_parse_json_output(self):
        """Test parsing JSON output."""
        runner = RipgrepRunner()
        
        output = '''
{"type":"match","data":{"path":{"text":"file.py"},"line_number":10,"lines":{"text":"def hello():"},"submatches":[{"start":4}]}}
{"type":"match","data":{"path":{"text":"file.py"},"line_number":20,"lines":{"text":"print(hello)"},"submatches":[]}}
'''
        
        matches, files = runner._parse_json_output(output, 100)
        
        assert len(matches) == 2
        assert files == 1
        assert matches[0].path == "file.py"
        assert matches[0].line_number == 10


class TestRipgrepInput:
    """Tests for RipgrepInput schema."""
    
    def test_default_values(self):
        """Test default input values."""
        input_data = RipgrepInput(pattern="test")
        
        assert input_data.pattern == "test"
        assert input_data.path == "."
        assert input_data.case_sensitive is False
        assert input_data.max_results == 1000
    
    def test_custom_values(self):
        """Test custom input values."""
        input_data = RipgrepInput(
            pattern="test",
            path="/tmp",
            glob="*.py",
            case_sensitive=True,
            max_results=100
        )
        
        assert input_data.path == "/tmp"
        assert input_data.glob == "*.py"
        assert input_data.case_sensitive is True
        assert input_data.max_results == 100


class TestRipgrepOutput:
    """Tests for RipgrepOutput schema."""
    
    def test_output_creation(self):
        """Test creating output."""
        output = RipgrepOutput(
            pattern="test",
            matches=[],
            total_matches=0,
            files_searched=0,
            duration_ms=100.0
        )
        
        assert output.pattern == "test"
        assert output.duration_ms == 100.0
        assert output.truncated is False


class TestGlobalFunctions:
    """Tests for global functions."""
    
    def test_get_ripgrep_runner(self):
        """Test getting global runner."""
        runner1 = get_ripgrep_runner()
        runner2 = get_ripgrep_runner()
        assert runner1 is runner2
    
    @pytest.mark.asyncio
    async def test_ripgrep_call_permission_denied(self):
        """Test call with permission denied."""
        input_data = RipgrepInput(pattern="test", path=".")
        context = MagicMock()
        context.get_app_state.return_value = None
        
        async def deny_permission(*args, **kwargs):
            return {"behavior": "reject"}
        
        result = await ripgrep_call(
            input_data,
            context,
            deny_permission,
            None,
            lambda x: None
        )
        
        assert result.is_error
        assert "Permission denied" in result.error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
