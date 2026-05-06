"""Environment detector — centralized environment detection at startup.

Detects:
- OS type, version, architecture
- Available shell (bash/zsh/pwsh/cmd)
- Available compilers (gcc/g++/rustc/go/javac/tsc/node)
- Available test frameworks (pytest/cargo test/go test/npm test)
- Build systems (make/cmake/npm/cargo/go mod/meson)
- Package managers (apt/yum/pacman/brew)
- Git availability and version
- Project-level language detection (which languages are used)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# =============================================================================
# Core detection
# =============================================================================


def detect_platform_family() -> str:
    """Map sys.platform to a package-manager family.

    Returns: 'debian', 'rhel', 'arch', 'darwin', 'windows', or 'unknown'
    """
    plat = sys.platform
    if plat.startswith("linux"):
        if os.path.exists("/etc/debian_version"):
            return "debian"
        if os.path.exists("/etc/arch-release"):
            return "arch"
        if os.path.exists("/etc/redhat-release") or os.path.exists("/etc/fedora-release"):
            return "rhel"
        return "linux"
    if plat == "darwin":
        return "darwin"
    if plat == "win32":
        return "windows"
    return "unknown"


def detect_shell() -> dict[str, Any]:
    """Detect the default shell and its capabilities.

    Returns:
        Dict with: name, path, is_windows, is_posix
    """
    is_win = sys.platform == "win32"
    if is_win:
        shell = os.environ.get("COMSPEC", "cmd.exe")
        shell_name = "cmd"
        # Check if PowerShell is available
        if shutil.which("pwsh"):
            shell_name = "pwsh"
        elif shutil.which("powershell"):
            shell_name = "powershell"
    else:
        shell = os.environ.get("SHELL", "/bin/bash")
        shell_name = os.path.basename(shell)

    return {
        "name": shell_name,
        "path": shell,
        "is_windows": is_win,
        "is_posix": not is_win,
    }


def detect_compilers() -> dict[str, str | None]:
    """Detect available compilers/interpreters.

    Returns:
        Dict mapping tool name to path (or None if not found).
    """
    tools = [
        "gcc",
        "g++",
        "clang",
        "clang++",
        "python3",
        "python",
        "node",
        "deno",
        "rustc",
        "cargo",
        "go",
        "javac",
        "java",
        "tsc",
        "dotnet",
    ]
    result: dict[str, str | None] = {}
    for tool in tools:
        path = shutil.which(tool)
        result[tool] = path
        # Also get version if available
        if path:
            try:
                proc = subprocess.run(
                    [tool, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                first_line = proc.stdout.split("\n")[0].strip()
                result[f"{tool}_version"] = first_line
            except Exception:
                result[f"{tool}_version"] = None
    return result


def detect_test_frameworks() -> dict[str, str | None]:
    """Detect available test frameworks.

    Returns:
        Dict: framework name -> tool path or None
    """
    # Quick checks
    frameworks: dict[str, str | None] = {
        "pytest": shutil.which("pytest"),
        "unittest": shutil.which("python"),
        "cargo_test": shutil.which("cargo"),
        "go_test": shutil.which("go"),
        "npm": shutil.which("npm"),
        "jest": shutil.which("jest"),
        "mocha": shutil.which("mocha"),
        "rtest": shutil.which("R") or shutil.which("Rscript"),
    }

    # Verify pytest is actually importable
    if frameworks["pytest"]:
        try:
            subprocess.run(
                [sys.executable, "-c", "import pytest"],
                capture_output=True,
                timeout=5,
            )
        except Exception:
            frameworks["pytest"] = None

    return frameworks


def detect_build_systems(cwd: str | None = None) -> list[dict[str, Any]]:
    """Detect build systems present in the project.

    Args:
        cwd: Project root directory (defaults to cwd).

    Returns:
        List of detected build system info dicts.
    """
    root = Path(cwd or os.getcwd())
    detected: list[dict[str, Any]] = []

    checks = [
        ("cmake", root / "CMakeLists.txt", "cmake"),
        ("make", root / "Makefile", "make"),
        ("make", root / "makefile", "make"),
        ("cargo", root / "Cargo.toml", "cargo"),
        ("npm", root / "package.json", "npm"),
        ("go_mod", root / "go.mod", "go"),
        ("meson", root / "meson.build", "meson"),
        ("bazel", root / "BUILD.bazel", "bazel"),
        ("gradle", root / "build.gradle", "gradle"),
        ("gradle", root / "build.gradle.kts", "gradle"),
        ("maven", root / "pom.xml", "maven"),
        ("scons", root / "SConstruct", "scons"),
    ]

    for name, marker, builder in checks:
        if marker.exists():
            tool_path = shutil.which(builder)
            detected.append(
                {
                    "name": name,
                    "builder": builder,
                    "available": tool_path is not None,
                    "tool_path": tool_path,
                }
            )

    return detected


def detect_git() -> dict[str, Any]:
    """Detect git availability and repo state."""
    git_path = shutil.which("git")
    if not git_path:
        return {"available": False}

    info: dict[str, Any] = {"available": True, "path": git_path}
    try:
        # Check if in a git repo
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            info["in_repo"] = True
            info["root"] = proc.stdout.strip()

            # Get branch
            proc = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            info["branch"] = proc.stdout.strip()

            # Get version
            proc = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            info["version"] = proc.stdout.strip()
        else:
            info["in_repo"] = False
    except Exception:
        info["in_repo"] = False

    return info


def detect_project_languages(cwd: str | None = None) -> list[str]:
    """Detect programming languages used in the project.

    Scans file extensions in the project to determine which
    languages are in use.

    Args:
        cwd: Project root (defaults to cwd).

    Returns:
        Sorted list of language names.
    """
    root = Path(cwd or os.getcwd())
    ext_count: dict[str, int] = {}

    try:
        for f in root.rglob("*"):
            if f.is_file() and f.suffix:
                ext = f.suffix.lower()
                ext_count[ext] = ext_count.get(ext, 0) + 1
                if len(ext_count) > 20:
                    break
    except Exception:
        pass

    # Only keep extensions with enough files
    lang_map = {
        ".py": "python",
        ".c": "c",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".rs": "rust",
        ".go": "go",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".java": "java",
        ".kt": "kotlin",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "swift",
        ".sh": "shell",
        ".bash": "shell",
        ".zsh": "shell",
        ".r": "r",
    }

    detected = set()
    for ext, count in ext_count.items():
        lang = lang_map.get(ext)
        if lang and count >= 2:  # At least 2 files to consider it "in use"
            detected.add(lang)
        elif lang and count == 1 and len(ext_count) <= 5:
            # Single file but small project
            detected.add(lang)

    return sorted(detected)


# =============================================================================
# Environment profile
# =============================================================================


class EnvironmentProfile:
    """Complete environment profile, detected at startup."""

    def __init__(self, cwd: str | None = None):
        self.cwd = cwd or os.getcwd()
        self.os_name = platform_system()
        self.os_version = platform_release()
        self.platform_family = detect_platform_family()
        self.shell = detect_shell()
        self.compilers = detect_compilers()
        self.test_frameworks = detect_test_frameworks()
        self.build_systems = detect_build_systems(self.cwd)
        self.git = detect_git()
        self.project_languages = detect_project_languages(self.cwd)
        self.detected_at = __import__("datetime").datetime.now().isoformat()

    def has_compiler(self, name: str) -> bool:
        """Check if a specific compiler is available."""
        return self.compilers.get(name) is not None

    def has_test_framework(self, name: str) -> bool:
        """Check if a test framework is available."""
        return self.test_frameworks.get(name) is not None

    def has_build_system(self, name: str) -> bool:
        """Check if a build system is available."""
        return any(bs["name"] == name and bs["available"] for bs in self.build_systems)

    def to_prompt_section(self) -> str:
        """Format environment info as a system prompt section."""
        parts = ["## Environment"]
        parts.append(f"- **OS**: {self.os_name} {self.os_version}")
        parts.append(f"- **Platform**: {self.platform_family}")
        parts.append(f"- **Shell**: {self.shell['name']}")
        parts.append(f"- **Working Directory**: {self.cwd}")

        # Available compilers
        compilers_available = {
            k: v for k, v in self.compilers.items() if v and not k.endswith("_version")
        }
        if compilers_available:
            comp_list = ", ".join(sorted(compilers_available.keys()))
            parts.append(f"- **Available**: {comp_list}")

        # Git
        if self.git.get("available") and self.git.get("in_repo"):
            branch = self.git.get("branch", "unknown")
            parts.append(f"- **Git Branch**: {branch}")

        # Project languages
        if self.project_languages:
            lang_list = ", ".join(self.project_languages)
            parts.append(f"- **Languages**: {lang_list}")

        return "\n".join(parts)

    def suggest_test_command(self, lang: str) -> str | None:
        """Suggest the best test command for a language based on available tools.

        Args:
            lang: Language name ('python', 'c', 'rust', etc.)

        Returns:
            Test command string, or None if no test tool is available.
        """
        suggestions = {
            "python": ["pytest", "python -m pytest", "python -m unittest discover"],
            "rust": ["cargo test"],
            "go": ["go test ./..."],
            "javascript": ["npm test", "npx jest", "npx mocha"],
            "typescript": ["npm test", "npx jest", "npx ts-mocha"],
            "java": ["mvn test", "gradle test"],
            "c": ["make test", "cmake --build . && ctest"],
            "cpp": ["make test", "cmake --build . && ctest"],
        }

        cmds = suggestions.get(lang, [])
        for cmd in cmds:
            tool = cmd.split()[0]
            if shutil.which(tool):
                return cmd

        # Fallback: try project build system
        for bs in self.build_systems:
            if bs["available"]:
                if lang == "rust" and bs["name"] == "cargo":
                    return "cargo test"
                if lang == "go" and bs["name"] == "go_mod":
                    return "go test ./..."

        return None


# Cache global environment profile
_env_profile: EnvironmentProfile | None = None


def get_environment_profile(cwd: str | None = None) -> EnvironmentProfile:
    """Get the cached environment profile, detecting on first call."""
    global _env_profile
    if _env_profile is None:
        _env_profile = EnvironmentProfile(cwd)
    return _env_profile


def platform_system():
    """Get OS name (cached import)."""
    import platform

    return platform.system()


def platform_release():
    """Get OS version (cached import)."""
    import platform

    return platform.release()
