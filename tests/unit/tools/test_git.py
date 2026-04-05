"""Tests for Git tools."""

import subprocess

import pytest

from pilotcode.tools.registry import get_tool_by_name
from tests.conftest import run_tool_test


class TestGitStatusTool:
    """Tests for GitStatus tool."""
    
    @pytest.mark.asyncio
    async def test_status_clean_repo(self, temp_git_repo, tool_context, allow_callback):
        """Test status in clean repository."""
        result = await run_tool_test(
            "GitStatus",
            {},
            tool_context,
            allow_callback
        )
        
        assert not result.is_error
        assert result.data.branch == "master" or result.data.branch == "main"
        assert result.data.is_clean is True
    
    @pytest.mark.asyncio
    async def test_status_with_untracked(self, temp_git_repo, tool_context, allow_callback):
        """Test status with untracked files."""
        # Create untracked file
        (temp_git_repo / "new_file.txt").write_text("new content")
        
        result = await run_tool_test(
            "GitStatus",
            {},
            tool_context,
            allow_callback
        )
        
        assert not result.is_error
        assert result.data.is_clean is False
        assert "new_file.txt" in result.data.untracked
    
    @pytest.mark.asyncio
    async def test_status_with_modified(self, temp_git_repo, tool_context, allow_callback):
        """Test status with modified files."""
        # Modify existing file
        (temp_git_repo / "README.md").write_text("Modified content")
        
        result = await run_tool_test(
            "GitStatus",
            {},
            tool_context,
            allow_callback
        )
        
        assert not result.is_error
        assert result.data.is_clean is False
        assert len(result.data.modified) > 0


class TestGitLogTool:
    """Tests for GitLog tool."""
    
    @pytest.mark.asyncio
    async def test_log_basic(self, temp_git_repo, tool_context, allow_callback):
        """Test basic log output."""
        result = await run_tool_test(
            "GitLog",
            {"max_count": 5},
            tool_context,
            allow_callback
        )
        
        assert not result.is_error
        assert len(result.data.commits) >= 1
        
        # Check commit structure
        first_commit = result.data.commits[0]
        assert first_commit.hash
        assert first_commit.message
        assert first_commit.author
    
    @pytest.mark.asyncio
    async def test_log_limit(self, temp_git_repo, tool_context, allow_callback):
        """Test log with commit limit."""
        # Add more commits
        for i in range(3):
            (temp_git_repo / f"file_{i}.txt").write_text(f"content {i}")
            subprocess.run(
                ["git", "add", "."],
                cwd=temp_git_repo, capture_output=True, check=True
            )
            subprocess.run(
                ["git", "commit", "-m", f"Commit {i}"],
                cwd=temp_git_repo, capture_output=True, check=True
            )
        
        result = await run_tool_test(
            "GitLog",
            {"max_count": 2},
            tool_context,
            allow_callback
        )
        
        assert not result.is_error
        assert len(result.data.commits) <= 2


class TestGitDiffTool:
    """Tests for GitDiff tool."""
    
    @pytest.mark.asyncio
    async def test_diff_no_changes(self, temp_git_repo, tool_context, allow_callback):
        """Test diff with no changes."""
        result = await run_tool_test(
            "GitDiff",
            {},
            tool_context,
            allow_callback
        )
        
        assert not result.is_error
        # May be empty or show no changes
    
    @pytest.mark.asyncio
    async def test_diff_with_changes(self, temp_git_repo, tool_context, allow_callback):
        """Test diff with uncommitted changes."""
        # Modify file
        (temp_git_repo / "README.md").write_text("Modified README")
        
        result = await run_tool_test(
            "GitDiff",
            {},
            tool_context,
            allow_callback
        )
        
        assert not result.is_error
        assert result.data.diff or result.data.file_count > 0


class TestGitBranchTool:
    """Tests for GitBranch tool."""
    
    @pytest.mark.asyncio
    async def test_branch_list(self, temp_git_repo, tool_context, allow_callback):
        """Test listing branches."""
        result = await run_tool_test(
            "GitBranch",
            {"action": "list"},
            tool_context,
            allow_callback
        )
        
        assert not result.is_error
        assert len(result.data.branches) >= 1
        assert result.data.current in result.data.branches
    
    @pytest.mark.asyncio
    async def test_branch_create(self, temp_git_repo, tool_context, allow_callback):
        """Test creating a branch."""
        result = await run_tool_test(
            "GitBranch",
            {"action": "create", "branch_name": "test-branch"},
            tool_context,
            allow_callback
        )
        
        assert not result.is_error
        
        # Verify branch was created
        result2 = await run_tool_test(
            "GitBranch",
            {"action": "list"},
            tool_context,
            allow_callback
        )
        assert "test-branch" in result2.data.branches
