"""Tests for result truncation service."""

import pytest

from pilotcode.services.result_truncation import (
    TruncatedResult,
    TruncationConfig,
    truncate_file_list,
    truncate_text_content,
    truncate_search_results,
    truncate_directory_listing,
    format_truncated_output,
    get_truncation_message,
)


class TestTruncationConfig:
    """Tests for TruncationConfig."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = TruncationConfig()
        assert config.max_files == TruncationConfig.DEFAULT_MAX_FILES
        assert config.max_lines == TruncationConfig.DEFAULT_MAX_LINES
        assert config.max_chars == TruncationConfig.DEFAULT_MAX_CHARS
    
    def test_custom_values(self):
        """Test custom configuration values."""
        config = TruncationConfig(
            max_files=100,
            max_lines=500,
            max_chars=1000
        )
        assert config.max_files == 100
        assert config.max_lines == 500
        assert config.max_chars == 1000


class TestTruncateFileList:
    """Tests for truncate_file_list."""
    
    def test_no_truncation_needed(self):
        """Test when file count is within limit."""
        files = ["file1.txt", "file2.txt", "file3.txt"]
        result = truncate_file_list(files, max_files=10)
        
        assert not result.is_truncated
        assert result.data == files
        assert result.original_count == 3
        assert result.truncated_count == 0
    
    def test_truncation_occurs(self):
        """Test when file count exceeds limit."""
        files = [f"file{i}.txt" for i in range(100)]
        result = truncate_file_list(files, max_files=50)
        
        assert result.is_truncated
        assert len(result.data) == 50
        assert result.original_count == 100
        assert result.truncated_count == 50
        assert result.truncation_message is not None
    
    def test_truncation_message_content(self):
        """Test that truncation message is informative."""
        files = [f"file{i}.txt" for i in range(100)]
        result = truncate_file_list(files, max_files=50)
        
        message = result.truncation_message
        assert "100" in message  # Total count
        assert "50" in message   # Shown count
        assert "truncated" in message.lower()
    
    def test_sample_in_message(self):
        """Test that sample files are included in message."""
        files = [f"file{i}.txt" for i in range(100)]
        result = truncate_file_list(files, max_files=50, show_sample=True)
        
        message = result.truncation_message
        assert "file50" in message or "file51" in message


class TestTruncateTextContent:
    """Tests for truncate_text_content."""
    
    def test_no_truncation_needed(self):
        """Test when content is within limits."""
        content = "Line 1\nLine 2\nLine 3"
        result = truncate_text_content(content, max_lines=10, max_chars=1000)
        
        assert not result.is_truncated
        assert result.data == content
    
    def test_line_truncation(self):
        """Test truncation by line count."""
        content = "\n".join([f"Line {i}" for i in range(100)])
        result = truncate_text_content(content, max_lines=50)
        
        assert result.is_truncated
        assert len(result.data.split('\n')) == 50
        assert result.truncated_count == 50
    
    def test_character_truncation(self):
        """Test truncation by character count."""
        content = "a" * 1000
        result = truncate_text_content(content, max_chars=100)
        
        assert result.is_truncated
        assert len(result.data) == 100
    
    def test_from_end_truncation(self):
        """Test truncation from end instead of start."""
        content = "\n".join([f"Line {i}" for i in range(10)])
        result = truncate_text_content(content, max_lines=5, from_start=False)
        
        lines = result.data.split('\n')
        assert lines[0] == "Line 5"
        assert lines[-1] == "Line 9"
    
    def test_truncation_message(self):
        """Test that truncation message is generated."""
        content = "\n".join([f"Line {i}" for i in range(100)])
        result = truncate_text_content(content, max_lines=50)
        
        assert result.truncation_message is not None
        assert "lines" in result.truncation_message


class TestTruncateSearchResults:
    """Tests for truncate_search_results."""
    
    def test_no_truncation(self):
        """Test when results are within limit."""
        results = [{"file": f"file{i}.txt"} for i in range(10)]
        result = truncate_search_results(results, max_results=20)
        
        assert not result.is_truncated
        assert len(result.data) == 10
    
    def test_truncation(self):
        """Test when results exceed limit."""
        results = [{"file": f"file{i}.txt"} for i in range(100)]
        result = truncate_search_results(results, max_results=50)
        
        assert result.is_truncated
        assert len(result.data) == 50
        assert result.original_count == 100
    
    def test_custom_result_type(self):
        """Test with custom result type in message."""
        results = [{"match": f"match{i}"} for i in range(100)]
        result = truncate_search_results(
            results,
            max_results=50,
            result_type="grep matches"
        )
        
        assert "grep matches" in result.truncation_message


class TestTruncateDirectoryListing:
    """Tests for truncate_directory_listing."""
    
    def test_no_truncation(self):
        """Test when entries are within limit."""
        entries = [{"name": f"entry{i}"} for i in range(10)]
        result = truncate_directory_listing(entries, max_entries=20)
        
        assert not result.is_truncated
    
    def test_with_directory_path(self):
        """Test with directory path in message."""
        entries = [{"name": f"entry{i}"} for i in range(100)]
        result = truncate_directory_listing(
            entries,
            max_entries=50,
            directory_path="/home/user"
        )
        
        assert result.is_truncated
        assert "/home/user" in result.truncation_message


class TestFormatTruncatedOutput:
    """Tests for format_truncated_output."""
    
    def test_non_truncated_format(self):
        """Test formatting non-truncated result."""
        result = TruncatedResult(
            data="content",
            original_count=10,
            truncated_count=0,
            is_truncated=False
        )
        
        output = format_truncated_output(result)
        
        assert output["data"] == "content"
        assert output["truncated"] is False
        assert output["total"] == 10
        assert output["shown"] == 10
        assert "truncated_count" not in output
    
    def test_truncated_format(self):
        """Test formatting truncated result."""
        result = TruncatedResult(
            data="partial content",
            original_count=100,
            truncated_count=50,
            is_truncated=True,
            truncation_message="50 items truncated"
        )
        
        output = format_truncated_output(result)
        
        assert output["truncated"] is True
        assert output["total"] == 100
        assert output["shown"] == 50
        assert output["truncated_count"] == 50
        assert output["message"] == "50 items truncated"
    
    def test_with_format_fn(self):
        """Test with custom format function."""
        result = TruncatedResult(
            data=["a", "b", "c"],
            original_count=10,
            truncated_count=7,
            is_truncated=True,
            truncation_message="truncated"
        )
        
        output = format_truncated_output(result, format_fn=lambda x: ",".join(x))
        
        assert output["data"] == "a,b,c"


class TestGetTruncationMessage:
    """Tests for get_truncation_message."""
    
    def test_glob_message(self):
        """Test glob-specific message."""
        message = get_truncation_message("glob", total=1000, limit=100)
        
        assert message is not None
        assert "1000" in message
        assert "100" in message
        assert "LS tool" in message
    
    def test_ls_message(self):
        """Test ls-specific message."""
        message = get_truncation_message("ls", total=500, limit=100)
        
        assert message is not None
        assert "Bash tool" in message
    
    def test_unknown_tool(self):
        """Test message for unknown tool."""
        message = get_truncation_message("unknown_tool", total=100, limit=50)
        
        assert message is None


class TestTruncationMessages:
    """Tests for Claude Code-style truncation messages."""
    
    def test_message_includes_total(self):
        """Test that message includes total count."""
        files = [f"file{i}.txt" for i in range(200)]
        result = truncate_file_list(files, max_files=100)
        
        assert "200" in result.truncation_message
    
    def test_message_includes_suggestion(self):
        """Test that message includes helpful suggestion."""
        files = [f"file{i}.txt" for i in range(200)]
        result = truncate_file_list(files, max_files=100)
        
        assert "patterns" in result.truncation_message.lower() or \
               "explore" in result.truncation_message.lower()


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_empty_list(self):
        """Test truncating empty list."""
        result = truncate_file_list([])
        
        assert not result.is_truncated
        assert result.data == []
    
    def test_empty_string(self):
        """Test truncating empty string."""
        result = truncate_text_content("")
        
        assert not result.is_truncated
        assert result.data == ""
    
    def test_exact_limit(self):
        """Test when count equals limit exactly."""
        files = [f"file{i}.txt" for i in range(100)]
        result = truncate_file_list(files, max_files=100)
        
        assert not result.is_truncated
        assert len(result.data) == 100
    
    def test_limit_plus_one(self):
        """Test when count is exactly one over limit."""
        files = [f"file{i}.txt" for i in range(101)]
        result = truncate_file_list(files, max_files=100)
        
        assert result.is_truncated
        assert len(result.data) == 100
        assert result.truncated_count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
