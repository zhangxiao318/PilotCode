"""GitHub source for downloading plugins."""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .base import PluginSource, DownloadResult, SourceError


class GitHubSource(PluginSource):
    """Download plugins from GitHub repositories."""

    def can_handle(self, source_type: str) -> bool:
        return source_type in ("github", "git")

    async def download(
        self, source_config: dict, target_path: Path, force: bool = False
    ) -> DownloadResult:
        """Download from GitHub or generic git repo.

        Args:
            source_config: Must contain either:
                - 'repo': GitHub repo in format "owner/repo"
                - 'url': Full git URL
                And optionally:
                - 'ref': Branch or tag (defaults to default branch)
                - 'path': Subdirectory to checkout
        """
        source_type = source_config.get("source", "github")

        # Build git URL
        if source_type == "github":
            repo = source_config.get("repo")
            if not repo:
                raise SourceError("GitHub source requires 'repo' field")
            git_url = f"https://github.com/{repo}.git"
        else:
            git_url = source_config.get("url")
            if not git_url:
                raise SourceError("Git source requires 'url' field")

        ref = source_config.get("ref")
        subdir = source_config.get("path", ".claude-plugin")

        # Remove existing if force
        if target_path.exists() and force:
            shutil.rmtree(target_path)

        # Create parent directory
        target_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Check if git is available
            git_exe = self._find_git()
            if not git_exe:
                raise SourceError("Git is not installed or not in PATH")

            # Clone repository
            temp_clone_path = target_path.with_suffix(".tmp")
            if temp_clone_path.exists():
                shutil.rmtree(temp_clone_path)

            # Perform shallow clone
            clone_cmd = [git_exe, "clone", "--depth", "1"]
            if ref:
                clone_cmd.extend(["--branch", ref])
            clone_cmd.extend([git_url, str(temp_clone_path)])

            result = subprocess.run(
                clone_cmd, capture_output=True, text=True, timeout=120  # 2 minute timeout
            )

            if result.returncode != 0:
                raise SourceError(f"Git clone failed: {result.stderr}")

            # Get the commit SHA for versioning
            sha_result = subprocess.run(
                [git_exe, "-C", str(temp_clone_path), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
            )
            version = sha_result.stdout.strip() if sha_result.returncode == 0 else None

            # If subdir specified, move only that directory
            source_path = temp_clone_path / subdir if subdir != "." else temp_clone_path

            if not source_path.exists():
                # Try without the subdirectory
                source_path = temp_clone_path

            # Move to final location
            if target_path.exists():
                shutil.rmtree(target_path)

            # If we need only a subdirectory
            if subdir and (temp_clone_path / subdir).exists():
                shutil.move(str(temp_clone_path / subdir), str(target_path))
                shutil.rmtree(temp_clone_path)
            else:
                shutil.move(str(temp_clone_path), str(target_path))

            # Remove .git directory to save space (optional)
            git_dir = target_path / ".git"
            if git_dir.exists():
                shutil.rmtree(git_dir)

            return DownloadResult(path=target_path, version=version, success=True)

        except subprocess.TimeoutExpired:
            raise SourceError("Git clone timed out after 120 seconds")
        except Exception as e:
            # Cleanup on error
            if target_path.exists():
                shutil.rmtree(target_path)
            temp_clone = target_path.with_suffix(".tmp")
            if temp_clone.exists():
                shutil.rmtree(temp_clone)
            raise SourceError(f"Failed to download: {e}")

    def _find_git(self) -> Optional[str]:
        """Find git executable."""
        git_exe = shutil.which("git")
        if git_exe:
            return git_exe

        # Try common locations on Windows
        if os.name == "nt":
            for path in [
                r"C:\Program Files\Git\bin\git.exe",
                r"C:\Program Files (x86)\Git\bin\git.exe",
            ]:
                if os.path.exists(path):
                    return path

        return None

    async def get_latest_commit(self, repo: str, ref: Optional[str] = None) -> Optional[str]:
        """Get latest commit SHA from GitHub API (no auth required for public repos).

        This is used to check for updates without cloning.
        """
        import aiohttp

        ref = ref or "HEAD"
        api_url = f"https://api.github.com/repos/{repo}/commits/{ref}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("sha")
        except Exception:
            pass

        return None
