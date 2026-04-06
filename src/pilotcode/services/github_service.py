"""GitHub Service - Full GitHub API integration.

This module provides:
1. Authentication (Token-based)
2. Repository operations
3. Issues management
4. Pull Request operations
5. Actions/CI workflow monitoring
6. Code review functionality
7. Release management

Features:
- Async GitHub API client using httpx
- Type-safe models with Pydantic
- Rate limit handling
- Pagination support
- Caching for read operations
- Webhook support for real-time updates
"""

from __future__ import annotations

import os
import time
from typing import Optional, Any, AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

import httpx
from pydantic import BaseModel, Field

# Constants
GITHUB_API_BASE = "https://api.github.com"
DEFAULT_TIMEOUT = 30.0
DEFAULT_PER_PAGE = 30
MAX_PER_PAGE = 100


class GitHubError(Exception):
    """Base GitHub API error."""

    def __init__(self, message: str, status_code: int = 0, response_body: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body or {}


class GitHubAuthError(GitHubError):
    """Authentication error."""

    pass


class GitHubRateLimitError(GitHubError):
    """Rate limit exceeded."""

    def __init__(self, message: str, reset_at: datetime, **kwargs):
        super().__init__(message, **kwargs)
        self.reset_at = reset_at


class GitHubNotFoundError(GitHubError):
    """Resource not found."""

    pass


class GitHubValidationError(GitHubError):
    """Validation failed."""

    pass


# Enums
class IssueState(str, Enum):
    """Issue/PR state."""

    OPEN = "open"
    CLOSED = "closed"
    ALL = "all"


class MergeMethod(str, Enum):
    """PR merge method."""

    MERGE = "merge"
    SQUASH = "squash"
    REBASE = "rebase"


class CheckStatus(str, Enum):
    """CI check status."""

    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class CheckConclusion(str, Enum):
    """CI check conclusion."""

    SUCCESS = "success"
    FAILURE = "failure"
    NEUTRAL = "neutral"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    ACTION_REQUIRED = "action_required"


# Pydantic Models
class User(BaseModel):
    """GitHub user."""

    login: str
    id: int
    avatar_url: str = ""
    html_url: str = ""
    type: str = "User"


class Label(BaseModel):
    """Issue/PR label."""

    name: str
    color: str = ""
    description: Optional[str] = None


class Milestone(BaseModel):
    """Issue/PR milestone."""

    number: int
    title: str
    state: str = "open"
    due_on: Optional[datetime] = None


class Repository(BaseModel):
    """GitHub repository."""

    id: int
    name: str
    full_name: str
    private: bool = False
    html_url: str = ""
    description: Optional[str] = None
    fork: bool = False
    url: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    pushed_at: Optional[datetime] = None
    homepage: Optional[str] = None
    size: int = 0
    stargazers_count: int = 0
    watchers_count: int = 0
    forks_count: int = 0
    open_issues_count: int = 0
    default_branch: str = "main"
    language: Optional[str] = None
    archived: bool = False
    disabled: bool = False
    topics: list[str] = Field(default_factory=list)
    owner: User = Field(default_factory=lambda: User(login="", id=0))


class Issue(BaseModel):
    """GitHub issue."""

    number: int
    title: str
    state: IssueState = IssueState.OPEN
    html_url: str = ""
    body: Optional[str] = None
    user: User = Field(default_factory=lambda: User(login="", id=0))
    labels: list[Label] = Field(default_factory=list)
    assignees: list[User] = Field(default_factory=list)
    milestone: Optional[Milestone] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    comments: int = 0


class PullRequest(BaseModel):
    """GitHub pull request."""

    number: int
    title: str
    state: IssueState = IssueState.OPEN
    html_url: str = ""
    body: Optional[str] = None
    user: User = Field(default_factory=lambda: User(login="", id=0))
    head: dict = Field(default_factory=dict)
    base: dict = Field(default_factory=dict)
    draft: bool = False
    merged: bool = False
    mergeable: Optional[bool] = None
    mergeable_state: str = ""
    merged_by: Optional[User] = None
    labels: list[Label] = Field(default_factory=list)
    assignees: list[User] = Field(default_factory=list)
    requested_reviewers: list[User] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    merged_at: Optional[datetime] = None
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0
    comments: int = 0
    review_comments: int = 0


class Comment(BaseModel):
    """Issue/PR comment."""

    id: int
    html_url: str = ""
    body: str = ""
    user: User = Field(default_factory=lambda: User(login="", id=0))
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Review(BaseModel):
    """Pull request review."""

    id: int
    html_url: str = ""
    state: str = ""  # APPROVED, CHANGES_REQUESTED, COMMENTED
    body: Optional[str] = None
    user: User = Field(default_factory=lambda: User(login="", id=0))
    submitted_at: Optional[datetime] = None


class CheckRun(BaseModel):
    """GitHub Actions check run."""

    id: int
    name: str
    head_sha: str = ""
    status: CheckStatus = CheckStatus.QUEUED
    conclusion: Optional[CheckConclusion] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    output: dict = Field(default_factory=dict)
    html_url: Optional[str] = None


class WorkflowRun(BaseModel):
    """GitHub Actions workflow run."""

    id: int
    name: str
    head_branch: str = ""
    head_sha: str = ""
    run_number: int = 0
    event: str = ""
    status: str = ""  # queued, in_progress, completed
    conclusion: Optional[str] = (
        None  # success, failure, neutral, cancelled, skipped, timed_out, action_required
    )
    workflow_id: int = 0
    html_url: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    run_started_at: Optional[datetime] = None
    jobs_url: str = ""


class Release(BaseModel):
    """GitHub release."""

    id: int
    tag_name: str
    name: Optional[str] = None
    body: Optional[str] = None
    draft: bool = False
    prerelease: bool = False
    created_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    html_url: str = ""
    author: User = Field(default_factory=lambda: User(login="", id=0))
    assets: list[dict] = Field(default_factory=list)


class RateLimit(BaseModel):
    """GitHub API rate limit status."""

    limit: int = 0
    remaining: int = 0
    reset_timestamp: int = 0
    used: int = 0

    @property
    def reset_at(self) -> datetime:
        return datetime.fromtimestamp(self.reset_timestamp)

    @property
    def is_exceeded(self) -> bool:
        return self.remaining <= 0


class FileChange(BaseModel):
    """File change in a PR."""

    filename: str
    status: str = ""  # added, removed, modified, renamed
    additions: int = 0
    deletions: int = 0
    changes: int = 0
    patch: Optional[str] = None
    previous_filename: Optional[str] = None


class CreateIssueRequest(BaseModel):
    """Request to create an issue."""

    title: str
    body: Optional[str] = None
    labels: Optional[list[str]] = None
    assignees: Optional[list[str]] = None
    milestone: Optional[int] = None


class CreatePullRequestRequest(BaseModel):
    """Request to create a PR."""

    title: str
    head: str  # Branch name
    base: str  # Branch name
    body: Optional[str] = None
    draft: bool = False
    maintainer_can_modify: bool = True


class CreateReviewRequest(BaseModel):
    """Request to create a review."""

    body: Optional[str] = None
    event: Optional[str] = None  # APPROVE, REQUEST_CHANGES, COMMENT
    comments: Optional[list[dict]] = None


class MergePullRequestRequest(BaseModel):
    """Request to merge a PR."""

    commit_title: Optional[str] = None
    commit_message: Optional[str] = None
    sha: Optional[str] = None  # Expected head SHA
    merge_method: MergeMethod = MergeMethod.MERGE


# Configuration
@dataclass
class GitHubConfig:
    """GitHub service configuration."""

    token: Optional[str] = None
    base_url: str = GITHUB_API_BASE
    timeout: float = DEFAULT_TIMEOUT
    per_page: int = DEFAULT_PER_PAGE
    max_retries: int = 3
    retry_delay: float = 1.0
    cache_ttl: float = 60.0  # Cache TTL in seconds


# Simple cache implementation
@dataclass
class CacheEntry:
    """Cache entry with TTL."""

    data: Any
    expires_at: float


class GitHubCache:
    """Simple in-memory cache for GitHub API responses."""

    def __init__(self, default_ttl: float = 60.0):
        self._cache: dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired."""
        entry = self._cache.get(key)
        if entry:
            if time.time() < entry.expires_at:
                return entry.data
            else:
                del self._cache[key]
        return None

    def set(self, key: str, data: Any, ttl: Optional[float] = None) -> None:
        """Cache data with TTL."""
        expires_at = time.time() + (ttl or self._default_ttl)
        self._cache[key] = CacheEntry(data=data, expires_at=expires_at)

    def clear(self) -> None:
        """Clear all cached data."""
        self._cache.clear()

    def delete(self, key: str) -> bool:
        """Delete a cache entry."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False


class GitHubService:
    """GitHub API service client.

    Usage:
        service = GitHubService(token="ghp_xxx")

        # Get repository
        repo = await service.get_repository("owner", "repo")

        # List issues
        async for issue in service.list_issues("owner", "repo"):
            print(issue.title)

        # Create issue
        issue = await service.create_issue(
            "owner", "repo",
            CreateIssueRequest(title="Bug", body="Description")
        )
    """

    def __init__(self, config: Optional[GitHubConfig] = None):
        self.config = config or GitHubConfig()
        self._client: Optional[httpx.AsyncClient] = None
        self._cache = GitHubCache(default_ttl=self.config.cache_ttl)
        self._rate_limit: Optional[RateLimit] = None

        # Use token from config or environment
        self._token = self.config.token or os.getenv("GITHUB_TOKEN")

    async def __aenter__(self) -> GitHubService:
        await self.connect()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def connect(self) -> None:
        """Initialize HTTP client."""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            headers=headers,
            timeout=self.config.timeout,
            follow_redirects=True,
        )

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure client is connected."""
        if not self._client:
            raise GitHubError("GitHub service not connected. Use 'async with' or call connect()")
        return self._client

    async def _request(
        self,
        method: str,
        path: str,
        json_data: Optional[dict] = None,
        params: Optional[dict] = None,
        use_cache: bool = False,
    ) -> Any:
        """Make API request with error handling and rate limit tracking."""
        client = self._ensure_client()

        # Check cache for GET requests
        cache_key = f"{method}:{path}:{hash(str(params))}"
        if use_cache and method == "GET":
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        # Make request with retries
        last_error = None
        for attempt in range(self.config.max_retries):
            try:
                response = await client.request(
                    method=method,
                    url=path,
                    json=json_data,
                    params=params,
                )

                # Update rate limit info
                self._update_rate_limit(response.headers)

                # Handle errors
                if response.status_code == 401:
                    raise GitHubAuthError("Invalid or missing authentication")
                elif response.status_code == 403:
                    if self._rate_limit and self._rate_limit.is_exceeded:
                        raise GitHubRateLimitError(
                            "Rate limit exceeded",
                            status_code=403,
                            reset_at=self._rate_limit.reset_at,
                        )
                    raise GitHubError("Forbidden", status_code=403)
                elif response.status_code == 404:
                    raise GitHubNotFoundError(f"Resource not found: {path}", status_code=404)
                elif response.status_code == 422:
                    body = response.json() if response.text else None
                    raise GitHubValidationError(
                        "Validation failed",
                        status_code=422,
                        response_body=body,
                    )
                elif response.status_code >= 500:
                    # Server error, retry
                    last_error = GitHubError(
                        f"Server error: {response.status_code}", status_code=response.status_code
                    )
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                    continue
                elif response.status_code >= 400:
                    raise GitHubError(
                        f"Request failed: {response.status_code}",
                        status_code=response.status_code,
                        response_body=response.json() if response.text else None,
                    )

                # Success
                if response.status_code == 204:  # No content
                    return None

                data = response.json() if response.text else None

                # Cache successful GET requests
                if use_cache and method == "GET" and data is not None:
                    self._cache.set(cache_key, data)

                return data

            except httpx.RequestError as e:
                last_error = GitHubError(f"Request failed: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                continue

        # All retries failed
        raise last_error or GitHubError("Max retries exceeded")

    def _update_rate_limit(self, headers: httpx.Headers) -> None:
        """Update rate limit info from response headers."""
        if "x-ratelimit-limit" in headers:
            self._rate_limit = RateLimit(
                limit=int(headers.get("x-ratelimit-limit", 0)),
                remaining=int(headers.get("x-ratelimit-remaining", 0)),
                reset_timestamp=int(headers.get("x-ratelimit-reset", 0)),
                used=int(headers.get("x-ratelimit-used", 0)),
            )

    async def _paginate(
        self,
        path: str,
        params: Optional[dict] = None,
        per_page: Optional[int] = None,
    ) -> AsyncIterator[dict]:
        """Paginate through API results."""
        params = params or {}
        params["per_page"] = per_page or self.config.per_page
        page = 1

        while True:
            params["page"] = page
            data = await self._request("GET", path, params=params)

            if not data or not isinstance(data, list):
                break

            for item in data:
                yield item

            if len(data) < params["per_page"]:
                break

            page += 1

    # Rate Limit

    async def get_rate_limit(self) -> RateLimit:
        """Get current rate limit status."""
        data = await self._request("GET", "/rate_limit")
        core = data.get("resources", {}).get("core", {})
        self._rate_limit = RateLimit(
            limit=core.get("limit", 0),
            remaining=core.get("remaining", 0),
            reset_timestamp=core.get("reset", 0),
            used=core.get("used", 0),
        )
        return self._rate_limit

    def get_cached_rate_limit(self) -> Optional[RateLimit]:
        """Get cached rate limit info."""
        return self._rate_limit

    # Repository Operations

    async def get_repository(self, owner: str, repo: str) -> Repository:
        """Get repository information."""
        data = await self._request("GET", f"/repos/{owner}/{repo}", use_cache=True)
        return Repository.model_validate(data)

    async def list_repositories(
        self,
        username: Optional[str] = None,
        type_filter: str = "owner",  # all, owner, member
        sort: str = "updated",  # created, updated, pushed, full_name
        direction: str = "desc",
    ) -> AsyncIterator[Repository]:
        """List repositories for user or authenticated user."""
        if username:
            path = f"/users/{username}/repos"
        else:
            path = "/user/repos"

        params = {
            "type": type_filter,
            "sort": sort,
            "direction": direction,
        }

        async for data in self._paginate(path, params):
            yield Repository.model_validate(data)

    async def list_org_repositories(
        self,
        org: str,
        type_filter: str = "all",  # all, public, private, forks, sources, member
    ) -> AsyncIterator[Repository]:
        """List organization repositories."""
        params = {"type": type_filter}

        async for data in self._paginate(f"/orgs/{org}/repos", params):
            yield Repository.model_validate(data)

    # Issue Operations

    async def get_issue(self, owner: str, repo: str, issue_number: int) -> Issue:
        """Get a specific issue."""
        data = await self._request(
            "GET", f"/repos/{owner}/{repo}/issues/{issue_number}", use_cache=True
        )
        return Issue.model_validate(data)

    async def list_issues(
        self,
        owner: str,
        repo: str,
        state: IssueState = IssueState.OPEN,
        labels: Optional[list[str]] = None,
        assignee: Optional[str] = None,
        creator: Optional[str] = None,
        sort: str = "created",  # created, updated, comments
        direction: str = "desc",
    ) -> AsyncIterator[Issue]:
        """List repository issues."""
        params: dict[str, Any] = {
            "state": state.value,
            "sort": sort,
            "direction": direction,
        }

        if labels:
            params["labels"] = ",".join(labels)
        if assignee:
            params["assignee"] = assignee
        if creator:
            params["creator"] = creator

        async for data in self._paginate(f"/repos/{owner}/{repo}/issues", params):
            # Skip pull requests (they're also returned in issues endpoint)
            if "pull_request" not in data:
                yield Issue.model_validate(data)

    async def create_issue(
        self,
        owner: str,
        repo: str,
        request: CreateIssueRequest,
    ) -> Issue:
        """Create a new issue."""
        data = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/issues",
            json_data=request.model_dump(exclude_none=True),
        )
        # Invalidate cache
        self._cache.delete(f"GET:/repos/{owner}/{repo}/issues:*")
        return Issue.model_validate(data)

    async def update_issue(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        state: Optional[IssueState] = None,
        labels: Optional[list[str]] = None,
        assignees: Optional[list[str]] = None,
    ) -> Issue:
        """Update an existing issue."""
        json_data: dict[str, Any] = {}
        if title is not None:
            json_data["title"] = title
        if body is not None:
            json_data["body"] = body
        if state is not None:
            json_data["state"] = state.value
        if labels is not None:
            json_data["labels"] = labels
        if assignees is not None:
            json_data["assignees"] = assignees

        data = await self._request(
            "PATCH",
            f"/repos/{owner}/{repo}/issues/{issue_number}",
            json_data=json_data,
        )
        # Invalidate cache
        self._cache.delete(f"GET:/repos/{owner}/{repo}/issues/{issue_number}:*")
        return Issue.model_validate(data)

    async def list_issue_comments(
        self,
        owner: str,
        repo: str,
        issue_number: int,
    ) -> AsyncIterator[Comment]:
        """List comments on an issue."""
        async for data in self._paginate(f"/repos/{owner}/{repo}/issues/{issue_number}/comments"):
            yield Comment.model_validate(data)

    async def create_issue_comment(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        body: str,
    ) -> Comment:
        """Create a comment on an issue."""
        data = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
            json_data={"body": body},
        )
        return Comment.model_validate(data)

    # Pull Request Operations

    async def get_pull_request(self, owner: str, repo: str, pr_number: int) -> PullRequest:
        """Get a specific pull request."""
        data = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/pulls/{pr_number}",
            use_cache=True,
        )
        return PullRequest.model_validate(data)

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        state: IssueState = IssueState.OPEN,
        sort: str = "created",  # created, updated, popularity, long-running
        direction: str = "desc",
    ) -> AsyncIterator[PullRequest]:
        """List repository pull requests."""
        params = {
            "state": state.value,
            "sort": sort,
            "direction": direction,
        }

        async for data in self._paginate(f"/repos/{owner}/{repo}/pulls", params):
            yield PullRequest.model_validate(data)

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        request: CreatePullRequestRequest,
    ) -> PullRequest:
        """Create a new pull request."""
        data = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/pulls",
            json_data=request.model_dump(exclude_none=True),
        )
        return PullRequest.model_validate(data)

    async def update_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        state: Optional[IssueState] = None,
        base: Optional[str] = None,
        maintainer_can_modify: Optional[bool] = None,
    ) -> PullRequest:
        """Update a pull request."""
        json_data: dict[str, Any] = {}
        if title is not None:
            json_data["title"] = title
        if body is not None:
            json_data["body"] = body
        if state is not None:
            json_data["state"] = state.value
        if base is not None:
            json_data["base"] = base
        if maintainer_can_modify is not None:
            json_data["maintainer_can_modify"] = maintainer_can_modify

        data = await self._request(
            "PATCH",
            f"/repos/{owner}/{repo}/pulls/{pr_number}",
            json_data=json_data,
        )
        self._cache.delete(f"GET:/repos/{owner}/{repo}/pulls/{pr_number}:*")
        return PullRequest.model_validate(data)

    async def merge_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        request: Optional[MergePullRequestRequest] = None,
    ) -> dict:
        """Merge a pull request."""
        request = request or MergePullRequestRequest()
        data = await self._request(
            "PUT",
            f"/repos/{owner}/{repo}/pulls/{pr_number}/merge",
            json_data=request.model_dump(exclude_none=True),
        )
        self._cache.delete(f"GET:/repos/{owner}/{repo}/pulls/{pr_number}:*")
        return data

    async def list_pull_request_files(
        self,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> AsyncIterator[FileChange]:
        """List files changed in a pull request."""
        async for data in self._paginate(f"/repos/{owner}/{repo}/pulls/{pr_number}/files"):
            yield FileChange.model_validate(data)

    async def list_reviews(
        self,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> AsyncIterator[Review]:
        """List reviews on a pull request."""
        async for data in self._paginate(f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews"):
            yield Review.model_validate(data)

    async def create_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        request: CreateReviewRequest,
    ) -> Review:
        """Create a review on a pull request."""
        data = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            json_data=request.model_dump(exclude_none=True),
        )
        return Review.model_validate(data)

    # Actions/CI Operations

    async def list_workflow_runs(
        self,
        owner: str,
        repo: str,
        workflow_id: Optional[str] = None,
        branch: Optional[str] = None,
        event: Optional[str] = None,
        status: Optional[str] = None,
    ) -> AsyncIterator[WorkflowRun]:
        """List workflow runs."""
        params: dict[str, Any] = {}
        if branch:
            params["branch"] = branch
        if event:
            params["event"] = event
        if status:
            params["status"] = status

        if workflow_id:
            path = f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs"
        else:
            path = f"/repos/{owner}/{repo}/actions/runs"

        async for data in self._paginate(path, params):
            yield WorkflowRun.model_validate(data)

    async def get_workflow_run(self, owner: str, repo: str, run_id: int) -> WorkflowRun:
        """Get a specific workflow run."""
        data = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/actions/runs/{run_id}",
            use_cache=True,
        )
        return WorkflowRun.model_validate(data)

    async def rerun_workflow(self, owner: str, repo: str, run_id: int) -> None:
        """Rerun a workflow."""
        await self._request(
            "POST",
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/rerun",
        )

    async def cancel_workflow(self, owner: str, repo: str, run_id: int) -> None:
        """Cancel a workflow run."""
        await self._request(
            "POST",
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/cancel",
        )

    async def list_check_runs(
        self,
        owner: str,
        repo: str,
        ref: str,
    ) -> AsyncIterator[CheckRun]:
        """List check runs for a ref."""
        params = {"ref": ref}

        async for data in self._paginate(
            f"/repos/{owner}/{repo}/commits/{ref}/check-runs",
            params,
        ):
            yield CheckRun.model_validate(data)

    # Release Operations

    async def list_releases(
        self,
        owner: str,
        repo: str,
    ) -> AsyncIterator[Release]:
        """List repository releases."""
        async for data in self._paginate(f"/repos/{owner}/{repo}/releases"):
            yield Release.model_validate(data)

    async def get_release(self, owner: str, repo: str, release_id: int) -> Release:
        """Get a specific release."""
        data = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/releases/{release_id}",
            use_cache=True,
        )
        return Release.model_validate(data)

    async def get_release_by_tag(self, owner: str, repo: str, tag: str) -> Release:
        """Get release by tag name."""
        data = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/releases/tags/{tag}",
            use_cache=True,
        )
        return Release.model_validate(data)

    async def create_release(
        self,
        owner: str,
        repo: str,
        tag_name: str,
        name: Optional[str] = None,
        body: Optional[str] = None,
        draft: bool = False,
        prerelease: bool = False,
        target_commitish: Optional[str] = None,
    ) -> Release:
        """Create a new release."""
        json_data: dict[str, Any] = {
            "tag_name": tag_name,
            "draft": draft,
            "prerelease": prerelease,
        }
        if name:
            json_data["name"] = name
        if body:
            json_data["body"] = body
        if target_commitish:
            json_data["target_commitish"] = target_commitish

        data = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/releases",
            json_data=json_data,
        )
        return Release.model_validate(data)

    # Search Operations

    async def search_repositories(
        self,
        query: str,
        sort: str = "updated",  # stars, forks, help-wanted-issues, updated
        order: str = "desc",
    ) -> AsyncIterator[Repository]:
        """Search repositories."""
        params = {
            "q": query,
            "sort": sort,
            "order": order,
        }

        page = 1
        while True:
            params["page"] = page
            data = await self._request("GET", "/search/repositories", params=params)

            items = data.get("items", [])
            if not items:
                break

            for item in items:
                yield Repository.model_validate(item)

            if len(items) < self.config.per_page:
                break

            page += 1

    async def search_issues(
        self,
        query: str,
        sort: str = "updated",  # comments, reactions, created, updated
        order: str = "desc",
    ) -> AsyncIterator[Issue]:
        """Search issues."""
        params = {
            "q": query,
            "sort": sort,
            "order": order,
        }

        page = 1
        while True:
            params["page"] = page
            data = await self._request("GET", "/search/issues", params=params)

            items = data.get("items", [])
            if not items:
                break

            for item in items:
                yield Issue.model_validate(item)

            if len(items) < self.config.per_page:
                break

            page += 1

    # Utility Methods

    def clear_cache(self) -> None:
        """Clear the response cache."""
        self._cache.clear()

    async def is_authenticated(self) -> bool:
        """Check if authenticated with GitHub."""
        if not self._token:
            return False
        try:
            await self._request("GET", "/user")
            return True
        except GitHubAuthError:
            return False


# Global instance management
_default_service: Optional[GitHubService] = None


def get_github_service(token: Optional[str] = None) -> GitHubService:
    """Get or create global GitHub service instance."""
    global _default_service
    if _default_service is None:
        config = GitHubConfig(token=token)
        _default_service = GitHubService(config)
    return _default_service


def clear_github_service() -> None:
    """Clear the global GitHub service instance."""
    global _default_service
    _default_service = None


# Import asyncio at the end to avoid circular issues
import asyncio
