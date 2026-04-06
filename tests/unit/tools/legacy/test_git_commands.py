"""Tests for Git Advanced Commands."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from pilotcode.commands.git_commands import (
    MergeStrategy,
    StashInfo,
    _check_rebase_in_progress,
    merge_command,
    rebase_command,
    stash_command,
    tag_command,
    fetch_command,
    pull_command,
    push_command,
    pr_command,
    issue_command,
)


# Fixtures
@pytest.fixture
def mock_git_exec():
    """Mock git_exec function."""
    with patch("pilotcode.commands.git_commands.git_exec") as mock:
        yield mock


@pytest.fixture
def mock_console():
    """Mock rich console."""
    with patch("pilotcode.commands.git_commands.console") as mock:
        yield mock


@pytest.fixture
def mock_get_current_branch():
    """Mock get_current_branch function."""
    with patch("pilotcode.commands.git_commands.get_current_branch") as mock:
        mock.return_value = "feature-branch"
        yield mock


@pytest.fixture
def mock_get_repo_info():
    """Mock get_repo_info function."""
    with patch("pilotcode.commands.git_commands.get_repo_info") as mock:
        mock.return_value = MagicMock(
            is_git_repo=True,
            github_owner="testowner",
            github_repo="testrepo",
            default_branch="main",
        )
        yield mock


@pytest.fixture
def command_context():
    """Create a mock command context."""
    return MagicMock()


# Test Merge Strategy Enum
class TestMergeStrategy:
    """Test MergeStrategy enum."""
    
    def test_merge_strategy_values(self):
        """Test merge strategy enum values."""
        assert MergeStrategy.DEFAULT == "default"
        assert MergeStrategy.NO_FF == "no-ff"
        assert MergeStrategy.FF_ONLY == "ff-only"
        assert MergeStrategy.SQUASH == "squash"


# Test Rebase Helper Functions
class TestRebaseHelpers:
    """Test rebase helper functions."""
    
    @pytest.mark.asyncio
    async def test_check_rebase_in_progress_true(self):
        """Test checking rebase in progress - true case."""
        import os
        with patch("os.path.exists") as mock_exists:
            mock_exists.side_effect = lambda p: "rebase-merge" in p or "rebase-apply" in p
            result = await _check_rebase_in_progress()
            assert result is True
    
    @pytest.mark.asyncio
    async def test_check_rebase_in_progress_false(self):
        """Test checking rebase in progress - false case."""
        import os
        with patch("os.path.exists") as mock_exists:
            mock_exists.return_value = False
            result = await _check_rebase_in_progress()
            assert result is False


# Test StashInfo dataclass
class TestStashInfo:
    """Test StashInfo dataclass."""
    
    def test_stash_info_creation(self):
        """Test creating StashInfo."""
        info = StashInfo(
            index=0,
            message="WIP on feature",
            branch="feature-branch",
            hash="abc123"
        )
        assert info.index == 0
        assert info.message == "WIP on feature"
        assert info.branch == "feature-branch"
        assert info.hash == "abc123"


# Test command functions
class TestMergeCommand:
    """Test merge command."""
    
    @pytest.mark.asyncio
    async def test_merge_no_args(self, command_context):
        """Test merge command with no arguments."""
        result = await merge_command([], command_context)
        assert "Usage:" in result
    
    @pytest.mark.asyncio
    async def test_merge_missing_branch(self, command_context):
        """Test merge command with missing branch."""
        result = await merge_command(["--strategy=squash"], command_context)
        assert "Error: Branch name required" in result
    
    @pytest.mark.asyncio
    async def test_merge_branch_not_found(self, command_context, mock_git_exec):
        """Test merge with non-existent branch."""
        mock_git_exec.return_value = MagicMock(returncode=1, stderr="fatal: not a valid ref")
        
        result = await merge_command(["nonexistent"], command_context)
        assert "not found" in result
    
    @pytest.mark.asyncio
    async def test_merge_success(self, command_context, mock_git_exec, mock_get_current_branch):
        """Test successful merge."""
        mock_git_exec.side_effect = [
            MagicMock(returncode=0),  # Branch exists
            MagicMock(returncode=0, stdout="Merge successful"),  # Merge
        ]
        
        result = await merge_command(["feature-branch"], command_context)
        assert "Successfully merged" in result
    
    @pytest.mark.asyncio
    async def test_merge_squash(self, command_context, mock_git_exec, mock_get_current_branch):
        """Test squash merge."""
        mock_git_exec.side_effect = [
            MagicMock(returncode=0),  # Branch exists
            MagicMock(returncode=0, stdout="Squash merge"),  # Merge
        ]
        
        result = await merge_command(["feature-branch", "--strategy=squash"], command_context)
        assert "squashed" in result or "Successfully merged" in result


class TestRebaseCommand:
    """Test rebase command."""
    
    @pytest.mark.asyncio
    async def test_rebase_no_args(self, command_context):
        """Test rebase command with no arguments."""
        result = await rebase_command([], command_context)
        assert "Usage:" in result or "branch" in result.lower()
    
    @pytest.mark.asyncio
    async def test_rebase_abort(self, command_context, mock_git_exec):
        """Test rebase abort."""
        mock_git_exec.return_value = MagicMock(returncode=0)
        
        result = await rebase_command(["--abort"], command_context)
        assert "aborted" in result.lower()
    
    @pytest.mark.asyncio
    async def test_rebase_continue(self, command_context, mock_git_exec):
        """Test rebase continue."""
        mock_git_exec.return_value = MagicMock(returncode=0)
        
        result = await rebase_command(["--continue"], command_context)
        assert "completed" in result.lower() or "Rebase" in result
    
    @pytest.mark.asyncio
    async def test_rebase_skip(self, command_context, mock_git_exec):
        """Test rebase skip."""
        mock_git_exec.return_value = MagicMock(returncode=0)
        
        result = await rebase_command(["--skip"], command_context)
        assert "skipped" in result.lower() or "commit" in result.lower()
    
    @pytest.mark.asyncio
    async def test_rebase_success(self, command_context, mock_git_exec, mock_get_current_branch):
        """Test successful rebase."""
        mock_git_exec.return_value = MagicMock(returncode=0)
        
        with patch("pilotcode.commands.git_commands._check_rebase_in_progress") as mock_check:
            mock_check.return_value = False
            result = await rebase_command(["main"], command_context)
            assert "Successfully rebased" in result


class TestStashCommand:
    """Test stash command."""
    
    @pytest.mark.asyncio
    async def test_stash_save_default(self, command_context, mock_git_exec, mock_get_current_branch):
        """Test stash save with default message."""
        mock_git_exec.return_value = MagicMock(returncode=0)
        
        result = await stash_command([], command_context)
        assert "Stashed" in result
    
    @pytest.mark.asyncio
    async def test_stash_save_with_message(self, command_context, mock_git_exec):
        """Test stash save with custom message."""
        mock_git_exec.return_value = MagicMock(returncode=0)
        
        result = await stash_command(["save", "Work in progress"], command_context)
        assert "Stashed" in result
    
    @pytest.mark.asyncio
    async def test_stash_list(self, command_context, mock_git_exec):
        """Test stash list."""
        mock_git_exec.return_value = MagicMock(returncode=0, stdout="stash@{0}|abc123|2 hours ago|WIP")
        
        result = await stash_command(["list"], command_context)
        # Should return empty string as it prints table directly
        assert result == ""
    
    @pytest.mark.asyncio
    async def test_stash_pop(self, command_context, mock_git_exec):
        """Test stash pop."""
        mock_git_exec.return_value = MagicMock(returncode=0)
        
        result = await stash_command(["pop"], command_context)
        assert "Applied" in result and "removed" in result.lower()
    
    @pytest.mark.asyncio
    async def test_stash_apply(self, command_context, mock_git_exec):
        """Test stash apply."""
        mock_git_exec.return_value = MagicMock(returncode=0)
        
        result = await stash_command(["apply", "stash@{1}"], command_context)
        assert "Applied" in result
    
    @pytest.mark.asyncio
    async def test_stash_drop(self, command_context, mock_git_exec):
        """Test stash drop."""
        mock_git_exec.return_value = MagicMock(returncode=0)
        
        result = await stash_command(["drop", "stash@{0}"], command_context)
        assert "Dropped" in result
    
    @pytest.mark.asyncio
    async def test_stash_clear(self, command_context, mock_git_exec):
        """Test stash clear."""
        mock_git_exec.return_value = MagicMock(returncode=0)
        
        result = await stash_command(["clear"], command_context)
        assert "cleared" in result.lower()


class TestTagCommand:
    """Test tag command."""
    
    @pytest.mark.asyncio
    async def test_tag_list(self, command_context, mock_git_exec):
        """Test tag list."""
        mock_git_exec.return_value = MagicMock(returncode=0, stdout="v1.0.0 Version 1.0.0\nv1.1.0 Version 1.1.0")
        
        result = await tag_command(["list"], command_context)
        assert result == ""  # Prints table directly
    
    @pytest.mark.asyncio
    async def test_tag_create(self, command_context, mock_git_exec):
        """Test tag create."""
        mock_git_exec.return_value = MagicMock(returncode=0)
        
        result = await tag_command(["create", "v1.0.0", "Release version 1.0.0"], command_context)
        assert "Created tag" in result
    
    @pytest.mark.asyncio
    async def test_tag_delete(self, command_context, mock_git_exec):
        """Test tag delete."""
        mock_git_exec.return_value = MagicMock(returncode=0)
        
        result = await tag_command(["delete", "v1.0.0"], command_context)
        assert "Deleted tag" in result
    
    @pytest.mark.asyncio
    async def test_tag_push(self, command_context, mock_git_exec):
        """Test tag push."""
        mock_git_exec.return_value = MagicMock(returncode=0)
        
        result = await tag_command(["push", "v1.0.0"], command_context)
        assert "Pushed tag" in result
    
    @pytest.mark.asyncio
    async def test_tag_push_all(self, command_context, mock_git_exec):
        """Test tag push-all."""
        mock_git_exec.return_value = MagicMock(returncode=0)
        
        result = await tag_command(["push-all"], command_context)
        assert "Pushed all tags" in result


class TestFetchCommand:
    """Test fetch command."""
    
    @pytest.mark.asyncio
    async def test_fetch_default(self, command_context, mock_git_exec):
        """Test fetch default."""
        mock_git_exec.return_value = MagicMock(returncode=0, stderr="From github.com:owner/repo")
        
        result = await fetch_command([], command_context)
        assert "From github.com" in result or "up to date" in result.lower()
    
    @pytest.mark.asyncio
    async def test_fetch_with_remote(self, command_context, mock_git_exec):
        """Test fetch with specific remote."""
        mock_git_exec.return_value = MagicMock(returncode=0, stderr="From upstream")
        
        result = await fetch_command(["upstream"], command_context)
        assert "upstream" in result or "up to date" in result.lower()
    
    @pytest.mark.asyncio
    async def test_fetch_all(self, command_context, mock_git_exec):
        """Test fetch all remotes."""
        mock_git_exec.return_value = MagicMock(returncode=0)
        
        result = await fetch_command(["--all"], command_context)
        assert "up to date" in result.lower() or "✓" in result


class TestPullCommand:
    """Test pull command."""
    
    @pytest.mark.asyncio
    async def test_pull_default(self, command_context, mock_git_exec):
        """Test pull default."""
        mock_git_exec.return_value = MagicMock(returncode=0, stdout="Already up to date.")
        
        result = await pull_command([], command_context)
        assert "up to date" in result.lower()
    
    @pytest.mark.asyncio
    async def test_pull_with_remote_branch(self, command_context, mock_git_exec):
        """Test pull with remote and branch."""
        mock_git_exec.return_value = MagicMock(returncode=0, stdout="Updating files")
        
        result = await pull_command(["origin", "main"], command_context)
        assert "✓" in result or "updating" in result.lower()
    
    @pytest.mark.asyncio
    async def test_pull_rebase(self, command_context, mock_git_exec):
        """Test pull with rebase."""
        mock_git_exec.return_value = MagicMock(returncode=0)
        
        result = await pull_command(["--rebase"], command_context)
        assert "✓" in result or "up to date" in result.lower()


class TestPushCommand:
    """Test push command."""
    
    @pytest.mark.asyncio
    async def test_push_default(self, command_context, mock_git_exec, mock_get_current_branch):
        """Test push default."""
        mock_git_exec.return_value = MagicMock(returncode=0)
        
        result = await push_command([], command_context)
        assert "Pushed" in result
    
    @pytest.mark.asyncio
    async def test_push_with_remote_branch(self, command_context, mock_git_exec):
        """Test push with remote and branch."""
        mock_git_exec.return_value = MagicMock(returncode=0)
        
        result = await push_command(["origin", "feature-branch"], command_context)
        assert "Pushed" in result
    
    @pytest.mark.asyncio
    async def test_push_force(self, command_context, mock_git_exec):
        """Test push with force."""
        mock_git_exec.return_value = MagicMock(returncode=0)
        
        result = await push_command(["--force"], command_context)
        assert "Pushed" in result
    
    @pytest.mark.asyncio
    async def test_push_set_upstream(self, command_context, mock_git_exec):
        """Test push with set-upstream."""
        mock_git_exec.return_value = MagicMock(returncode=0)
        
        result = await push_command(["-u", "origin", "new-branch"], command_context)
        assert "Pushed" in result


class TestPRCommand:
    """Test PR command."""
    
    @pytest.mark.asyncio
    async def test_pr_no_github_repo(self, command_context, mock_get_repo_info):
        """Test PR command when not in GitHub repo."""
        mock_get_repo_info.return_value = MagicMock(
            is_git_repo=True,
            github_owner=None,
            github_repo=None,
        )
        
        result = await pr_command(["list"], command_context)
        assert "Not a GitHub repository" in result


class TestIssueCommand:
    """Test issue command."""
    
    @pytest.mark.asyncio
    async def test_issue_no_github_repo(self, command_context, mock_get_repo_info):
        """Test issue command when not in GitHub repo."""
        mock_get_repo_info.return_value = MagicMock(
            is_git_repo=True,
            github_owner=None,
            github_repo=None,
        )
        
        result = await issue_command(["list"], command_context)
        assert "Not a GitHub repository" in result


# Test git utilities
class TestGitUtils:
    """Test git utility functions."""
    
    @pytest.mark.asyncio
    async def test_git_exec_success(self):
        """Test successful git execution."""
        from pilotcode.utils.git import git_exec, GitExecResult
        
        with patch("pilotcode.utils.git.asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"output text", b"")
            mock_exec.return_value = mock_proc
            
            result = await git_exec(["status"])
            
            assert result.returncode == 0
            assert result.stdout == "output text"
            assert result.stderr == ""
    
    @pytest.mark.asyncio
    async def test_git_exec_failure(self):
        """Test failed git execution."""
        from pilotcode.utils.git import git_exec
        
        with patch("pilotcode.utils.git.asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 1
            mock_proc.communicate.return_value = (b"", b"error message")
            mock_exec.return_value = mock_proc
            
            result = await git_exec(["bad-command"])
            
            assert result.returncode == 1
            assert result.stderr == "error message"
    
    def test_parse_github_remote_https(self):
        """Test parsing HTTPS GitHub remote."""
        from pilotcode.utils.git import parse_github_remote
        
        owner, repo = parse_github_remote("https://github.com/owner/repo.git")
        assert owner == "owner"
        assert repo == "repo"
        
        # Without .git
        owner, repo = parse_github_remote("https://github.com/owner/repo")
        assert owner == "owner"
        assert repo == "repo"
    
    def test_parse_github_remote_ssh(self):
        """Test parsing SSH GitHub remote."""
        from pilotcode.utils.git import parse_github_remote
        
        owner, repo = parse_github_remote("git@github.com:owner/repo.git")
        assert owner == "owner"
        assert repo == "repo"
        
        # Without .git
        owner, repo = parse_github_remote("git@github.com:owner/repo")
        assert owner == "owner"
        assert repo == "repo"
    
    def test_parse_github_remote_invalid(self):
        """Test parsing invalid GitHub remote."""
        from pilotcode.utils.git import parse_github_remote
        
        owner, repo = parse_github_remote("not-a-github-url")
        assert owner is None
        assert repo is None
        
        owner, repo = parse_github_remote(None)
        assert owner is None
        assert repo is None
    
    @pytest.mark.asyncio
    async def test_get_current_branch(self):
        """Test getting current branch."""
        from pilotcode.utils.git import get_current_branch
        
        with patch("pilotcode.utils.git.git_exec") as mock_exec:
            mock_exec.return_value = MagicMock(returncode=0, stdout="feature-branch")
            
            branch = await get_current_branch()
            
            assert branch == "feature-branch"
    
    @pytest.mark.asyncio
    async def test_is_git_repository_true(self):
        """Test checking git repository - true."""
        from pilotcode.utils.git import is_git_repository
        
        with patch("pilotcode.utils.git.git_exec") as mock_exec:
            mock_exec.return_value = MagicMock(returncode=0)
            
            result = await is_git_repository()
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_is_git_repository_false(self):
        """Test checking git repository - false."""
        from pilotcode.utils.git import is_git_repository
        
        with patch("pilotcode.utils.git.git_exec") as mock_exec:
            mock_exec.return_value = MagicMock(returncode=1)
            
            result = await is_git_repository()
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_get_repo_root(self):
        """Test getting repository root."""
        from pilotcode.utils.git import get_repo_root
        
        with patch("pilotcode.utils.git.git_exec") as mock_exec:
            mock_exec.return_value = MagicMock(returncode=0, stdout="/path/to/repo")
            
            root = await get_repo_root()
            
            assert root == "/path/to/repo"
    
    @pytest.mark.asyncio
    async def test_get_remote_url(self):
        """Test getting remote URL."""
        from pilotcode.utils.git import get_remote_url
        
        with patch("pilotcode.utils.git.git_exec") as mock_exec:
            mock_exec.return_value = MagicMock(
                returncode=0,
                stdout="https://github.com/owner/repo.git"
            )
            
            url = await get_remote_url("origin")
            
            assert url == "https://github.com/owner/repo.git"
    
    @pytest.mark.asyncio
    async def test_get_repo_info(self):
        """Test getting repository info."""
        from pilotcode.utils.git import get_repo_info
        
        with patch("pilotcode.utils.git.get_repo_root") as mock_root:
            with patch("pilotcode.utils.git.get_current_branch") as mock_branch:
                with patch("pilotcode.utils.git.get_default_branch") as mock_default:
                    with patch("pilotcode.utils.git.get_remote_url") as mock_remote:
                        mock_root.return_value = "/path/to/repo"
                        mock_branch.return_value = "feature"
                        mock_default.return_value = "main"
                        mock_remote.return_value = "https://github.com/owner/repo.git"
                        
                        info = await get_repo_info()
                        
                        assert info.is_git_repo is True
                        assert info.root_path == "/path/to/repo"
                        assert info.current_branch == "feature"
                        assert info.default_branch == "main"
                        assert info.github_owner == "owner"
                        assert info.github_repo == "repo"
    
    @pytest.mark.asyncio
    async def test_get_repo_info_not_git(self):
        """Test getting repository info for non-git directory."""
        from pilotcode.utils.git import get_repo_info
        
        with patch("pilotcode.utils.git.get_repo_root") as mock_root:
            mock_root.return_value = None
            
            info = await get_repo_info()
            
            assert info.is_git_repo is False
    
    @pytest.mark.asyncio
    async def test_has_uncommitted_changes_true(self):
        """Test checking uncommitted changes - true."""
        from pilotcode.utils.git import has_uncommitted_changes
        
        with patch("pilotcode.utils.git.git_exec") as mock_exec:
            mock_exec.return_value = MagicMock(returncode=0, stdout=" M file.txt")
            
            result = await has_uncommitted_changes()
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_has_uncommitted_changes_false(self):
        """Test checking uncommitted changes - false."""
        from pilotcode.utils.git import has_uncommitted_changes
        
        with patch("pilotcode.utils.git.git_exec") as mock_exec:
            mock_exec.return_value = MagicMock(returncode=0, stdout="")
            
            result = await has_uncommitted_changes()
            
            assert result is False


# Test sync versions of git utils
class TestGitUtilsSync:
    """Test synchronous git utility functions."""
    
    def test_git_exec_sync_success(self):
        """Test successful synchronous git execution."""
        from pilotcode.utils.git import git_exec_sync
        
        with patch("pilotcode.utils.git.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="output text",
                stderr=""
            )
            
            result = git_exec_sync(["status"])
            
            assert result.returncode == 0
            assert result.stdout == "output text"
    
    def test_get_current_branch_sync(self):
        """Test getting current branch synchronously."""
        from pilotcode.utils.git import get_current_branch_sync
        
        with patch("pilotcode.utils.git.git_exec_sync") as mock_exec:
            mock_exec.return_value = MagicMock(returncode=0, stdout="main")
            
            branch = get_current_branch_sync()
            
            assert branch == "main"
    
    def test_is_git_repository_sync(self):
        """Test checking git repository synchronously."""
        from pilotcode.utils.git import is_git_repository_sync
        
        with patch("pilotcode.utils.git.git_exec_sync") as mock_exec:
            mock_exec.return_value = MagicMock(returncode=0)
            
            result = is_git_repository_sync()
            
            assert result is True
    
    def test_get_repo_info_sync(self):
        """Test getting repository info synchronously."""
        from pilotcode.utils.git import get_repo_info_sync
        
        with patch("pilotcode.utils.git.get_repo_root_sync") as mock_root:
            with patch("pilotcode.utils.git.get_current_branch_sync") as mock_branch:
                with patch("pilotcode.utils.git.git_exec_sync") as mock_exec:
                    with patch("pilotcode.utils.git.get_remote_url_sync") as mock_remote:
                        mock_root.return_value = "/repo"
                        mock_branch.return_value = "main"
                        mock_exec.return_value = MagicMock(returncode=1)  # main doesn't exist
                        mock_remote.return_value = "https://github.com/user/repo.git"
                        
                        info = get_repo_info_sync()
                        
                        assert info.is_git_repo is True
                        assert info.github_owner == "user"
                        assert info.github_repo == "repo"
