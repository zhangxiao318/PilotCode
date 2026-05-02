"""Tests for Git tools."""

import subprocess

import pytest

from tests.conftest import run_tool_test


class TestGitStatus:
    """Tests for Git status action."""

    @pytest.mark.asyncio
    async def test_status_clean_repo(self, temp_git_repo, allow_callback):
        """Test status in clean repository."""
        result = await run_tool_test(
            "Git", {"action": "status", "path": str(temp_git_repo)}, None, allow_callback
        )

        assert not result.is_error
        assert result.data.result.get("branch") in ["master", "main"]
        assert result.data.result.get("is_clean") is True

    @pytest.mark.asyncio
    async def test_status_with_untracked(self, temp_git_repo, allow_callback):
        """Test status with untracked files."""
        # Create untracked file
        (temp_git_repo / "new_file.txt").write_text("new content")

        result = await run_tool_test(
            "Git", {"action": "status", "path": str(temp_git_repo)}, None, allow_callback
        )

        assert not result.is_error
        assert result.data.result.get("is_clean") is False
        assert "new_file.txt" in result.data.result.get("untracked", [])

    @pytest.mark.asyncio
    async def test_status_with_modified(self, temp_git_repo, allow_callback):
        """Test status with modified files."""
        # Modify existing file
        (temp_git_repo / "README.md").write_text("Modified content")

        result = await run_tool_test(
            "Git", {"action": "status", "path": str(temp_git_repo)}, None, allow_callback
        )

        assert not result.is_error
        assert result.data.result.get("is_clean") is False
        assert len(result.data.result.get("modified", [])) > 0


class TestGitLog:
    """Tests for Git log action."""

    @pytest.mark.asyncio
    async def test_log_basic(self, temp_git_repo, allow_callback):
        """Test basic log output."""
        result = await run_tool_test(
            "Git",
            {"action": "log", "path": str(temp_git_repo), "max_count": 5},
            None,
            allow_callback,
        )

        assert not result.is_error
        assert len(result.data.result.get("commits", [])) >= 1

        # Check commit structure
        first_commit = result.data.result.get("commits", [])[0]
        assert first_commit.get("hash")
        assert first_commit.get("message")
        assert first_commit.get("author")

    @pytest.mark.asyncio
    async def test_log_limit(self, temp_git_repo, allow_callback):
        """Test log with commit limit."""
        # Add more commits
        for i in range(3):
            (temp_git_repo / f"file_{i}.txt").write_text(f"content {i}")
            subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True, check=True)
            subprocess.run(
                ["git", "commit", "-m", f"Commit {i}"],
                cwd=temp_git_repo,
                capture_output=True,
                check=True,
            )

        result = await run_tool_test(
            "Git",
            {"action": "log", "path": str(temp_git_repo), "max_count": 2},
            None,
            allow_callback,
        )

        assert not result.is_error
        assert len(result.data.result.get("commits", [])) <= 2


class TestGitDiff:
    """Tests for Git diff action."""

    @pytest.mark.asyncio
    async def test_diff_no_changes(self, temp_git_repo, allow_callback):
        """Test diff with no changes."""
        result = await run_tool_test(
            "Git", {"action": "diff", "path": str(temp_git_repo)}, None, allow_callback
        )

        assert not result.is_error
        # May be empty or show no changes

    @pytest.mark.asyncio
    async def test_diff_with_changes(self, temp_git_repo, allow_callback):
        """Test diff with uncommitted changes."""
        # Modify file
        (temp_git_repo / "README.md").write_text("Modified README")

        result = await run_tool_test(
            "Git", {"action": "diff", "path": str(temp_git_repo)}, None, allow_callback
        )

        assert not result.is_error
        assert result.data.result.get("diff") or result.data.result.get("file_count", 0) > 0


class TestGitBranch:
    """Tests for Git branch action."""

    @pytest.mark.asyncio
    async def test_branch_list(self, temp_git_repo, allow_callback):
        """Test listing branches."""
        result = await run_tool_test(
            "Git",
            {"action": "branch", "path": str(temp_git_repo), "branch_action": "list"},
            None,
            allow_callback,
        )

        assert not result.is_error
        assert len(result.data.result.get("branches", [])) >= 1
        assert result.data.result.get("current") in result.data.result.get("branches", [])

    @pytest.mark.asyncio
    async def test_branch_create(self, temp_git_repo, allow_callback):
        """Test creating a branch."""
        result = await run_tool_test(
            "Git",
            {
                "action": "branch",
                "path": str(temp_git_repo),
                "branch_action": "create",
                "branch_name": "test-branch",
            },
            None,
            allow_callback,
        )

        assert not result.is_error

        # Verify branch was created
        result2 = await run_tool_test(
            "Git",
            {"action": "branch", "path": str(temp_git_repo), "branch_action": "list"},
            None,
            allow_callback,
        )
        assert "test-branch" in result2.data.result.get("branches", [])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
