"""Git Advanced Commands - Extended Git operations.

This module provides advanced Git commands:
- Branch operations (merge, rebase)
- Stash management
- Tag operations
- Remote synchronization (fetch, pull, push)
- GitHub integration commands (pr, issue)

All commands work with both local Git and GitHub integration.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Optional
from enum import Enum

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from pilotcode.types.command import CommandContext
from pilotcode.utils.git import git_exec, get_current_branch, get_repo_info
from pilotcode.commands.base import CommandHandler, register_command

console = Console()


class MergeStrategy(str, Enum):
    """Git merge strategy."""
    DEFAULT = "default"
    NO_FF = "no-ff"
    FF_ONLY = "ff-only"
    SQUASH = "squash"


class RebaseStrategy(str, Enum):
    """Git rebase strategy."""
    DEFAULT = "default"
    INTERACTIVE = "interactive"
    ONTO = "onto"


@dataclass
class StashInfo:
    """Git stash information."""
    index: int
    message: str
    branch: str
    hash: str


async def merge_command(args: list[str], context: CommandContext) -> str:
    """Merge a branch into the current branch.
    
    Usage: /merge <branch> [--strategy=<strategy>] [--message=<msg>]
    
    Strategies:
      default  - Standard merge
      no-ff    - Create merge commit even if fast-forward possible
      ff-only  - Only allow fast-forward merges
      squash   - Squash commits into one
    """
    if not args:
        return "[red]Usage: /merge <branch> [options][/red]\nUse [cyan]/help merge[/cyan] for more information"
    
    branch = args[0]
    if branch.startswith("-"):
        return "[red]Error: Branch name required[/red]"
    
    # Parse options
    strategy = MergeStrategy.DEFAULT
    message: Optional[str] = None
    
    for arg in args[1:]:
        if arg.startswith("--strategy="):
            strategy_str = arg.split("=", 1)[1]
            try:
                strategy = MergeStrategy(strategy_str)
            except ValueError:
                return f"[red]Unknown strategy: {strategy_str}[/red]"
        elif arg.startswith("--message="):
            message = arg.split("=", 1)[1]
    
    # Check if branch exists
    result = await git_exec(["show-ref", "--verify", f"refs/heads/{branch}"])
    if result.returncode != 0:
        # Try remote branch
        result = await git_exec(["show-ref", "--verify", f"refs/remotes/origin/{branch}"])
        if result.returncode != 0:
            return f"[red]Branch '{branch}' not found[/red]"
    
    current = await get_current_branch()
    
    # Build merge command
    cmd = ["merge"]
    
    if strategy == MergeStrategy.NO_FF:
        cmd.append("--no-ff")
    elif strategy == MergeStrategy.FF_ONLY:
        cmd.append("--ff-only")
    elif strategy == MergeStrategy.SQUASH:
        cmd.append("--squash")
    
    if message:
        cmd.extend(["-m", message])
    
    cmd.append(branch)
    
    # Execute merge
    result = await git_exec(cmd)
    
    if result.returncode == 0:
        success_msg = f"✓ Successfully merged '{branch}' into '{current}'"
        if strategy == MergeStrategy.SQUASH:
            success_msg += " (squashed)"
        output = [f"[green]{success_msg}[/green]"]
        if result.stdout:
            output.append(result.stdout)
        return "\n".join(output)
    else:
        return f"[red]Merge failed:[/red]\n{result.stderr}"


async def _rebase_abort() -> str:
    """Abort current rebase."""
    result = await git_exec(["rebase", "--abort"])
    
    if result.returncode == 0:
        return "[green]✓ Rebase aborted[/green]"
    else:
        return f"[red]Failed to abort rebase:[/red] {result.stderr}"


async def _rebase_continue() -> str:
    """Continue rebase after resolving conflicts."""
    result = await git_exec(["rebase", "--continue"])
    
    if result.returncode == 0:
        return "[green]✓ Rebase completed[/green]"
    else:
        return f"[red]Failed to continue rebase:[/red] {result.stderr}"


async def _rebase_skip() -> str:
    """Skip current commit and continue rebase."""
    result = await git_exec(["rebase", "--skip"])
    
    if result.returncode == 0:
        return "[green]✓ Commit skipped, rebase continued[/green]"
    else:
        return f"[red]Failed to skip commit:[/red] {result.stderr}"


async def _check_rebase_in_progress() -> bool:
    """Check if a rebase is in progress."""
    result = await git_exec(["rev-parse", "--git-path", "rebase-merge"])
    rebase_merge = result.stdout.strip()
    
    result = await git_exec(["rev-parse", "--git-path", "rebase-apply"])
    rebase_apply = result.stdout.strip()
    
    return os.path.exists(rebase_merge) or os.path.exists(rebase_apply)


async def rebase_command(args: list[str], context: CommandContext) -> str:
    """Rebase current branch onto another branch.
    
    Usage: /rebase <branch> [--interactive] [--onto=<newbase>]
    
    Use --abort, --continue, or --skip to manage in-progress rebases.
    """
    if not args:
        return "[red]Usage: /rebase <branch> [options][/red]"
    
    branch = args[0]
    
    # Handle special commands
    if branch == "--abort":
        return await _rebase_abort()
    elif branch == "--continue":
        return await _rebase_continue()
    elif branch == "--skip":
        return await _rebase_skip()
    
    if branch.startswith("-"):
        return "[red]Error: Branch name required[/red]"
    
    # Parse options
    interactive = False
    onto: Optional[str] = None
    
    for arg in args[1:]:
        if arg == "--interactive" or arg == "-i":
            interactive = True
        elif arg.startswith("--onto="):
            onto = arg.split("=", 1)[1]
    
    # Check for ongoing rebase
    is_rebasing = await _check_rebase_in_progress()
    if is_rebasing:
        return "[yellow]Rebase in progress. Use --continue, --abort, or --skip[/yellow]"
    
    # Build rebase command
    cmd = ["rebase"]
    
    if interactive:
        cmd.append("-i")
    
    if onto:
        cmd.extend(["--onto", onto])
    
    cmd.append(branch)
    
    current = await get_current_branch()
    
    # Execute rebase
    result = await git_exec(cmd)
    
    if result.returncode == 0:
        return f"[green]✓ Successfully rebased '{current}' onto '{branch}'[/green]"
    else:
        if "conflict" in result.stderr.lower():
            return "[yellow]Rebase paused due to conflicts[/yellow]\nResolve conflicts, then use [cyan]/rebase --continue[/cyan]"
        else:
            return f"[red]Rebase failed:[/red]\n{result.stderr}"


async def _stash_save(message: Optional[str] = None) -> str:
    """Save changes to stash."""
    cmd = ["stash", "push"]
    if message:
        cmd.extend(["-m", message])
    
    result = await git_exec(cmd)
    
    if result.returncode == 0:
        msg = message or "Changes"
        return f"[green]✓ Stashed: {msg}[/green]"
    else:
        return f"[red]Failed to stash:[/red] {result.stderr}"


async def _stash_list() -> str:
    """List all stashes."""
    result = await git_exec(["stash", "list", "--format=%gd|%h|%ar|%s"])
    
    if result.returncode != 0:
        return f"[red]Failed to list stashes:[/red] {result.stderr}"
    
    if not result.stdout.strip():
        return "[dim]No stashes found[/dim]"
    
    table = Table(title="Git Stashes", show_header=True)
    table.add_column("Index", style="cyan", width=12)
    table.add_column("Hash", style="dim", width=8)
    table.add_column("When", style="green", width=15)
    table.add_column("Message", style="white")
    
    for line in result.stdout.strip().split("\n"):
        parts = line.split("|", 3)
        if len(parts) == 4:
            table.add_row(parts[0], parts[1], parts[2], parts[3])
    
    console.print(table)
    return ""


async def _stash_pop(stash: str = "stash@{0}") -> str:
    """Apply and remove stash."""
    result = await git_exec(["stash", "pop", stash])
    
    if result.returncode == 0:
        return f"[green]✓ Applied and removed {stash}[/green]"
    else:
        return f"[red]Failed to pop stash:[/red] {result.stderr}"


async def _stash_apply(stash: str = "stash@{0}") -> str:
    """Apply stash without removing."""
    result = await git_exec(["stash", "apply", stash])
    
    if result.returncode == 0:
        return f"[green]✓ Applied {stash}[/green]"
    else:
        return f"[red]Failed to apply stash:[/red] {result.stderr}"


async def _stash_drop(stash: str = "stash@{0}") -> str:
    """Remove stash."""
    result = await git_exec(["stash", "drop", stash])
    
    if result.returncode == 0:
        return f"[green]✓ Dropped {stash}[/green]"
    else:
        return f"[red]Failed to drop stash:[/red] {result.stderr}"


async def _stash_clear() -> str:
    """Remove all stashes."""
    result = await git_exec(["stash", "clear"])
    
    if result.returncode == 0:
        return "[green]✓ All stashes cleared[/green]"
    else:
        return f"[red]Failed to clear stashes:[/red] {result.stderr}"


async def _stash_show(stash: str = "stash@{0}") -> str:
    """Show stash details."""
    result = await git_exec(["stash", "show", "-p", stash])
    
    if result.returncode == 0:
        return str(Panel(result.stdout, title=f"Stash: {stash}", border_style="blue"))
    else:
        return f"[red]Failed to show stash:[/red] {result.stderr}"


async def stash_command(args: list[str], context: CommandContext) -> str:
    """Manage Git stashes.
    
    Commands: save, list, show, pop, apply, drop, clear
    """
    if not args:
        # Default: save with default message
        return await _stash_save("WIP on " + await get_current_branch())
    
    command = args[0]
    
    if command == "list":
        return await _stash_list()
    elif command == "save":
        message = " ".join(args[1:]) if len(args) > 1 else None
        return await _stash_save(message)
    elif command == "pop":
        stash = args[1] if len(args) > 1 else "stash@{0}"
        return await _stash_pop(stash)
    elif command == "apply":
        stash = args[1] if len(args) > 1 else "stash@{0}"
        return await _stash_apply(stash)
    elif command == "drop":
        stash = args[1] if len(args) > 1 else "stash@{0}"
        return await _stash_drop(stash)
    elif command == "clear":
        return await _stash_clear()
    elif command == "show":
        stash = args[1] if len(args) > 1 else "stash@{0}"
        return await _stash_show(stash)
    else:
        # Treat as save message
        message = " ".join(args)
        return await _stash_save(message)


async def _tag_list(pattern: Optional[str] = None) -> str:
    """List tags."""
    cmd = ["tag", "-l", "-n1"]
    if pattern:
        cmd.append(pattern)
    
    result = await git_exec(cmd)
    
    if result.returncode != 0:
        return f"[red]Failed to list tags:[/red] {result.stderr}"
    
    if not result.stdout.strip():
        return "[dim]No tags found[/dim]"
    
    table = Table(title="Git Tags", show_header=True)
    table.add_column("Tag", style="cyan")
    table.add_column("Message", style="white")
    
    for line in result.stdout.strip().split("\n"):
        parts = line.split(None, 1)
        tag = parts[0]
        message = parts[1] if len(parts) > 1 else ""
        table.add_row(tag, message)
    
    console.print(table)
    return ""


async def _tag_create(name: str, message: str) -> str:
    """Create annotated tag."""
    result = await git_exec(["tag", "-a", name, "-m", message])
    
    if result.returncode == 0:
        return f"[green]✓ Created tag '{name}': {message}[/green]"
    else:
        return f"[red]Failed to create tag:[/red] {result.stderr}"


async def _tag_delete(name: str) -> str:
    """Delete tag."""
    result = await git_exec(["tag", "-d", name])
    
    if result.returncode == 0:
        return f"[green]✓ Deleted tag '{name}'[/green]"
    else:
        return f"[red]Failed to delete tag:[/red] {result.stderr}"


async def _tag_push(name: str, remote: str = "origin") -> str:
    """Push tag to remote."""
    result = await git_exec(["push", remote, name])
    
    if result.returncode == 0:
        return f"[green]✓ Pushed tag '{name}' to {remote}[/green]"
    else:
        return f"[red]Failed to push tag:[/red] {result.stderr}"


async def _tag_push_all(remote: str = "origin") -> str:
    """Push all tags to remote."""
    result = await git_exec(["push", remote, "--tags"])
    
    if result.returncode == 0:
        return f"[green]✓ Pushed all tags to {remote}[/green]"
    else:
        return f"[red]Failed to push tags:[/red] {result.stderr}"


async def tag_command(args: list[str], context: CommandContext) -> str:
    """Manage Git tags.
    
    Commands: list, create, delete, push, push-all
    """
    if not args:
        return await _tag_list()
    
    command = args[0]
    
    if command == "list":
        return await _tag_list()
    elif command == "create":
        if len(args) < 2:
            return "[red]Usage: /tag create <name> [message][/red]"
        name = args[1]
        message = " ".join(args[2:]) if len(args) > 2 else name
        return await _tag_create(name, message)
    elif command == "delete":
        if len(args) < 2:
            return "[red]Usage: /tag delete <name>[/red]"
        return await _tag_delete(args[1])
    elif command == "push":
        if len(args) < 2:
            return "[red]Usage: /tag push <name>[/red]"
        return await _tag_push(args[1])
    elif command == "push-all":
        return await _tag_push_all()
    else:
        # List tags matching pattern
        return await _tag_list(command)


async def fetch_command(args: list[str], context: CommandContext) -> str:
    """Fetch from remote repository."""
    remote = "origin"
    fetch_all = False
    prune = False
    
    for arg in args:
        if arg == "--all":
            fetch_all = True
        elif arg == "--prune":
            prune = True
        elif not arg.startswith("-"):
            remote = arg
    
    cmd = ["fetch"]
    
    if fetch_all:
        cmd.append("--all")
    if prune:
        cmd.append("--prune")
    
    if not fetch_all:
        cmd.append(remote)
    
    result = await git_exec(cmd)
    
    if result.returncode == 0:
        output = result.stderr.strip() or "Already up to date"
        return f"[green]✓ {output}[/green]"
    else:
        return f"[red]Fetch failed:[/red] {result.stderr}"


async def pull_command(args: list[str], context: CommandContext) -> str:
    """Pull changes from remote."""
    remote: Optional[str] = None
    branch: Optional[str] = None
    rebase = False
    
    for arg in args:
        if arg == "--rebase":
            rebase = True
        elif not arg.startswith("-"):
            if remote is None:
                remote = arg
            elif branch is None:
                branch = arg
    
    cmd = ["pull"]
    
    if rebase:
        cmd.append("--rebase")
    
    if remote:
        cmd.append(remote)
        if branch:
            cmd.append(branch)
    
    result = await git_exec(cmd)
    
    if result.returncode == 0:
        output = result.stdout.strip() or "Already up to date"
        return f"[green]✓ {output}[/green]"
    else:
        return f"[red]Pull failed:[/red] {result.stderr}"


async def push_command(args: list[str], context: CommandContext) -> str:
    """Push changes to remote."""
    remote: Optional[str] = None
    branch: Optional[str] = None
    force = False
    set_upstream = False
    
    for arg in args:
        if arg == "--force" or arg == "-f":
            force = True
        elif arg == "--set-upstream" or arg == "-u":
            set_upstream = True
        elif not arg.startswith("-"):
            if remote is None:
                remote = arg
            elif branch is None:
                branch = arg
    
    cmd = ["push"]
    
    if force:
        cmd.append("--force-with-lease")
    if set_upstream:
        cmd.append("--set-upstream")
    
    if remote:
        cmd.append(remote)
        if branch:
            cmd.append(branch)
    
    current = await get_current_branch()
    target = f"{remote or 'origin'} {branch or current}"
    
    result = await git_exec(cmd)
    
    if result.returncode == 0:
        output = [f"[green]✓ Pushed to {target}[/green]"]
        if result.stderr:
            output.append(f"[dim]{result.stderr}[/dim]")
        return "\n".join(output)
    else:
        return f"[red]Push failed:[/red] {result.stderr}"


# Import GitHub service for PR and issue commands
from pilotcode.services.github_service import (
    GitHubService,
    CreatePullRequestRequest,
    CreateIssueRequest,
    IssueState,
)


async def _pr_list() -> str:
    """List open PRs."""
    repo_info = await get_repo_info()
    if not repo_info or not repo_info.github_owner or not repo_info.github_repo:
        return "[red]Not a GitHub repository or remote not configured[/red]"
    
    try:
        async with GitHubService() as github:
            table = Table(title=f"Open Pull Requests: {repo_info.github_owner}/{repo_info.github_repo}", show_header=True)
            table.add_column("#", style="cyan", width=6)
            table.add_column("Title", style="white")
            table.add_column("Author", style="green", width=15)
            table.add_column("Branch", style="dim")
            table.add_column("Status", style="yellow")
            
            count = 0
            async for pr in github.list_pull_requests(repo_info.github_owner, repo_info.github_repo):
                status = "🟢 Open" if pr.state == IssueState.OPEN else "🔴 Closed"
                if pr.draft:
                    status = "⚪ Draft"
                if pr.merged:
                    status = "🟣 Merged"
                
                table.add_row(
                    str(pr.number),
                    pr.title[:50] + "..." if len(pr.title) > 50 else pr.title,
                    pr.user.login,
                    f"{pr.head.get('ref', '?')} → {pr.base.get('ref', '?')}",
                    status
                )
                count += 1
            
            if count == 0:
                return "[dim]No open pull requests[/dim]"
            else:
                console.print(table)
                return f"\n[dim]Showing {count} PR(s). Use '/pr view <number>' for details[/dim]"
    
    except Exception as e:
        return f"[red]Failed to list PRs:[/red] {e}"


async def _pr_create(title: Optional[str] = None) -> str:
    """Create a new PR."""
    repo_info = await get_repo_info()
    if not repo_info or not repo_info.github_owner or not repo_info.github_repo:
        return "[red]Not a GitHub repository or remote not configured[/red]"
    
    current = await get_current_branch()
    if current in ["main", "master"]:
        return "[yellow]Warning: Creating PR from main/master branch[/yellow]"
    
    # Get default title from recent commits if not provided
    if not title:
        result = await git_exec(["log", "--format=%s", "-1", f"origin/{repo_info.default_branch}..{current}"])
        title = result.stdout.strip() or f"Update from {current}"
    
    # Get PR body
    result = await git_exec(["log", "--format=%b", f"origin/{repo_info.default_branch}..{current}"])
    body = result.stdout.strip() or ""
    
    try:
        async with GitHubService() as github:
            request = CreatePullRequestRequest(
                title=title,
                head=current,
                base=repo_info.default_branch,
                body=body or None,
            )
            
            pr = await github.create_pull_request(
                repo_info.github_owner,
                repo_info.github_repo,
                request
            )
            
            output = [
                f"[green]✓ Created PR #{pr.number}: {pr.title}[/green]",
                f"[blue]{pr.html_url}[/blue]"
            ]
            return "\n".join(output)
    
    except Exception as e:
        return f"[red]Failed to create PR:[/red] {e}"


async def _pr_view(number: Optional[str] = None) -> str:
    """View PR details."""
    repo_info = await get_repo_info()
    if not repo_info or not repo_info.github_owner or not repo_info.github_repo:
        return "[red]Not a GitHub repository[/red]"
    
    try:
        async with GitHubService() as github:
            # If no number provided, try to find PR for current branch
            if not number:
                current = await get_current_branch()
                async for pr in github.list_pull_requests(
                    repo_info.github_owner,
                    repo_info.github_repo,
                    state=IssueState.ALL
                ):
                    if pr.head.get("ref") == current:
                        number = str(pr.number)
                        break
                
                if not number:
                    return f"[yellow]No PR found for branch '{current}'[/yellow]"
            
            pr = await github.get_pull_request(
                repo_info.github_owner,
                repo_info.github_repo,
                int(number)
            )
            
            # Display PR details
            status_color = "green" if pr.state == IssueState.OPEN else "red"
            status_text = "Open" if pr.state == IssueState.OPEN else "Closed"
            if pr.merged:
                status_text = "Merged"
                status_color = "purple"
            
            panel_content = f"""[bold]{pr.title}[/bold]

[dim]Author:[/dim] @{pr.user.login}
[dim]Branch:[/dim] {pr.head.get('ref', '?')} → {pr.base.get('ref', '?')}
[dim]Status:[/dim] [{status_color}]{status_text}[/{status_color}]
[dim]Created:[/dim] {pr.created_at.strftime('%Y-%m-%d') if pr.created_at else 'N/A'}

{pr.body or '[dim]No description[/dim]'}

[blue]{pr.html_url}[/blue]
"""
            console.print(Panel(panel_content, title=f"PR #{pr.number}", border_style="blue"))
            return ""
    
    except Exception as e:
        return f"[red]Failed to view PR:[/red] {e}"


async def _pr_checkout(number: str) -> str:
    """Checkout a PR branch."""
    repo_info = await get_repo_info()
    if not repo_info or not repo_info.github_owner or not repo_info.github_repo:
        return "[red]Not a GitHub repository[/red]"
    
    try:
        # Fetch PR refs
        await git_exec(["fetch", "origin", f"pull/{number}/head:pr-{number}"])
        
        # Checkout
        result = await git_exec(["checkout", f"pr-{number}"])
        
        if result.returncode == 0:
            return f"[green]✓ Checked out PR #{number} to branch 'pr-{number}'[/green]"
        else:
            # Try switching to existing branch
            result = await git_exec(["checkout", f"pr-{number}"])
            if result.returncode == 0:
                return f"[green]✓ Switched to existing branch 'pr-{number}'[/green]"
            else:
                return f"[red]Failed to checkout PR:[/red] {result.stderr}"
    
    except Exception as e:
        return f"[red]Failed to checkout PR:[/red] {e}"


async def _pr_merge(number: str) -> str:
    """Merge a PR."""
    repo_info = await get_repo_info()
    if not repo_info or not repo_info.github_owner or not repo_info.github_repo:
        return "[red]Not a GitHub repository[/red]"
    
    try:
        async with GitHubService() as github:
            # Get PR details first
            pr = await github.get_pull_request(
                repo_info.github_owner,
                repo_info.github_repo,
                int(number)
            )
            
            if pr.state != IssueState.OPEN:
                return f"[red]PR #{number} is not open[/red]"
            
            result = await github.merge_pull_request(
                repo_info.github_owner,
                repo_info.github_repo,
                int(number)
            )
            
            if result.get("merged"):
                return f"[green]✓ Successfully merged PR #{number}[/green]\nCommit: {result.get('sha', 'N/A')[:8]}"
            else:
                return f"[yellow]Merge result: {result.get('message', 'Unknown')}[/yellow]"
    
    except Exception as e:
        return f"[red]Failed to merge PR:[/red] {e}"


async def pr_command(args: list[str], context: CommandContext) -> str:
    """GitHub Pull Request operations.
    
    Commands: list, create, view, checkout, merge
    """
    if not args:
        return await _pr_list()
    
    command = args[0]
    
    if command == "list":
        return await _pr_list()
    elif command == "create":
        title = " ".join(args[1:]) if len(args) > 1 else None
        return await _pr_create(title)
    elif command == "view":
        number = args[1] if len(args) > 1 else None
        return await _pr_view(number)
    elif command == "checkout":
        if len(args) < 2:
            return "[red]Usage: /pr checkout <number>[/red]"
        return await _pr_checkout(args[1])
    elif command == "merge":
        if len(args) < 2:
            return "[red]Usage: /pr merge <number>[/red]"
        return await _pr_merge(args[1])
    else:
        return f"[red]Unknown command: {command}[/red]"


async def _issue_list() -> str:
    """List open issues."""
    repo_info = await get_repo_info()
    if not repo_info or not repo_info.github_owner or not repo_info.github_repo:
        return "[red]Not a GitHub repository or remote not configured[/red]"
    
    try:
        async with GitHubService() as github:
            table = Table(title=f"Open Issues: {repo_info.github_owner}/{repo_info.github_repo}", show_header=True)
            table.add_column("#", style="cyan", width=6)
            table.add_column("Title", style="white")
            table.add_column("Author", style="green", width=15)
            table.add_column("Labels", style="yellow")
            table.add_column("Comments", style="dim", width=10)
            
            count = 0
            async for issue in github.list_issues(repo_info.github_owner, repo_info.github_repo):
                labels = ", ".join([l.name for l in issue.labels[:3]])
                if len(issue.labels) > 3:
                    labels += "..."
                
                table.add_row(
                    str(issue.number),
                    issue.title[:50] + "..." if len(issue.title) > 50 else issue.title,
                    issue.user.login,
                    labels or "-",
                    str(issue.comments)
                )
                count += 1
            
            if count == 0:
                return "[dim]No open issues[/dim]"
            else:
                console.print(table)
                return f"\n[dim]Showing {count} issue(s). Use '/issue view <number>' for details[/dim]"
    
    except Exception as e:
        return f"[red]Failed to list issues:[/red] {e}"


async def _issue_create(title: Optional[str] = None) -> str:
    """Create a new issue."""
    repo_info = await get_repo_info()
    if not repo_info or not repo_info.github_owner or not repo_info.github_repo:
        return "[red]Not a GitHub repository or remote not configured[/red]"
    
    if not title:
        return "[red]Usage: /issue create <title>[/red]"
    
    try:
        async with GitHubService() as github:
            request = CreateIssueRequest(title=title)
            
            issue = await github.create_issue(
                repo_info.github_owner,
                repo_info.github_repo,
                request
            )
            
            output = [
                f"[green]✓ Created issue #{issue.number}: {issue.title}[/green]",
                f"[blue]{issue.html_url}[/blue]"
            ]
            return "\n".join(output)
    
    except Exception as e:
        return f"[red]Failed to create issue:[/red] {e}"


async def _issue_view(number: str) -> str:
    """View issue details."""
    repo_info = await get_repo_info()
    if not repo_info or not repo_info.github_owner or not repo_info.github_repo:
        return "[red]Not a GitHub repository[/red]"
    
    try:
        async with GitHubService() as github:
            issue = await github.get_issue(
                repo_info.github_owner,
                repo_info.github_repo,
                int(number)
            )
            
            status_color = "green" if issue.state == IssueState.OPEN else "red"
            status_text = "Open" if issue.state == IssueState.OPEN else "Closed"
            
            labels_text = ", ".join([f"[#{l.color}]{l.name}[/#{l.color}]" for l in issue.labels]) if issue.labels else "None"
            
            panel_content = f"""[bold]{issue.title}[/bold]

[dim]Author:[/dim] @{issue.user.login}
[dim]Status:[/dim] [{status_color}]{status_text}[/{status_color}]
[dim]Labels:[/dim] {labels_text}
[dim]Comments:[/dim] {issue.comments}
[dim]Created:[/dim] {issue.created_at.strftime('%Y-%m-%d') if issue.created_at else 'N/A'}

{issue.body or '[dim]No description[/dim]'}

[blue]{issue.html_url}[/blue]
"""
            console.print(Panel(panel_content, title=f"Issue #{issue.number}", border_style="blue"))
            return ""
    
    except Exception as e:
        return f"[red]Failed to view issue:[/red] {e}"


async def _issue_close(number: str) -> str:
    """Close an issue."""
    repo_info = await get_repo_info()
    if not repo_info or not repo_info.github_owner or not repo_info.github_repo:
        return "[red]Not a GitHub repository[/red]"
    
    try:
        async with GitHubService() as github:
            issue = await github.update_issue(
                repo_info.github_owner,
                repo_info.github_repo,
                int(number),
                state=IssueState.CLOSED
            )
            
            return f"[green]✓ Closed issue #{issue.number}[/green]"
    
    except Exception as e:
        return f"[red]Failed to close issue:[/red] {e}"


async def _issue_reopen(number: str) -> str:
    """Reopen an issue."""
    repo_info = await get_repo_info()
    if not repo_info or not repo_info.github_owner or not repo_info.github_repo:
        return "[red]Not a GitHub repository[/red]"
    
    try:
        async with GitHubService() as github:
            issue = await github.update_issue(
                repo_info.github_owner,
                repo_info.github_repo,
                int(number),
                state=IssueState.OPEN
            )
            
            return f"[green]✓ Reopened issue #{issue.number}[/green]"
    
    except Exception as e:
        return f"[red]Failed to reopen issue:[/red] {e}"


async def issue_command(args: list[str], context: CommandContext) -> str:
    """GitHub Issue operations.
    
    Commands: list, create, view, close, reopen
    """
    if not args:
        return await _issue_list()
    
    command = args[0]
    
    if command == "list":
        return await _issue_list()
    elif command == "create":
        title = " ".join(args[1:]) if len(args) > 1 else None
        return await _issue_create(title)
    elif command == "view":
        if len(args) < 2:
            return "[red]Usage: /issue view <number>[/red]"
        return await _issue_view(args[1])
    elif command == "close":
        if len(args) < 2:
            return "[red]Usage: /issue close <number>[/red]"
        return await _issue_close(args[1])
    elif command == "reopen":
        if len(args) < 2:
            return "[red]Usage: /issue reopen <number>[/red]"
        return await _issue_reopen(args[1])
    else:
        return f"[red]Unknown command: {command}[/red]"


# Register all commands
register_command(CommandHandler(
    name="merge",
    description="Merge a branch into the current branch",
    handler=merge_command,
    aliases=[],
))

register_command(CommandHandler(
    name="rebase",
    description="Rebase current branch onto another branch",
    handler=rebase_command,
    aliases=[],
))

register_command(CommandHandler(
    name="stash",
    description="Manage Git stashes",
    handler=stash_command,
    aliases=[],
))

register_command(CommandHandler(
    name="tag",
    description="Manage Git tags",
    handler=tag_command,
    aliases=[],
))

register_command(CommandHandler(
    name="fetch",
    description="Fetch from remote repository",
    handler=fetch_command,
    aliases=[],
))

register_command(CommandHandler(
    name="pull",
    description="Pull changes from remote",
    handler=pull_command,
    aliases=[],
))

register_command(CommandHandler(
    name="push",
    description="Push changes to remote",
    handler=push_command,
    aliases=[],
))

register_command(CommandHandler(
    name="pr",
    description="GitHub Pull Request operations",
    handler=pr_command,
    aliases=[],
))

register_command(CommandHandler(
    name="issue",
    description="GitHub Issue operations",
    handler=issue_command,
    aliases=[],
))
