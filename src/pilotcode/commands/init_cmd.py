"""Init command — auto-analyze project and generate KnowHow.md."""

from __future__ import annotations

import os
from pathlib import Path

from .base import CommandHandler, register_command, CommandContext

# ------------------------------------------------------------------
# Project detectors
# ------------------------------------------------------------------

_TECH_STACK_FILES: dict[str, str] = {
    "package.json": "Node.js / JavaScript",
    "pyproject.toml": "Python",
    "setup.py": "Python",
    "setup.cfg": "Python",
    "requirements.txt": "Python",
    "Pipfile": "Python (Pipenv)",
    "poetry.lock": "Python (Poetry)",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "pom.xml": "Java (Maven)",
    "build.gradle": "Java (Gradle)",
    "build.gradle.kts": "Java (Gradle Kotlin)",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
    "mix.exs": "Elixir",
    "rebar.config": "Erlang",
    "Package.swift": "Swift",
    "CMakeLists.txt": "C/C++ (CMake)",
    "Makefile": "C/C++ / Make",
    "Dockerfile": "Docker",
    "docker-compose.yml": "Docker Compose",
    "docker-compose.yaml": "Docker Compose",
}

_README_FILES = ["README.md", "README.rst", "README.txt", "README"]

_ENTRY_PATTERNS: dict[str, list[str]] = {
    "Node.js / JavaScript": ["index.js", "main.js", "app.js", "server.js", "src/index.js"],
    "Python": ["main.py", "app.py", "manage.py", "src/__main__.py", "__main__.py"],
    "Rust": ["src/main.rs", "src/lib.rs"],
    "Go": ["main.go", "cmd/"],
    "Java (Maven)": ["src/main/java/"],
    "Java (Gradle)": ["src/main/java/"],
}

_TEST_DIR_PATTERNS = ["tests", "test", "spec", "__tests__", "src/test"]

_CI_FILES = [
    ".github/workflows",
    ".gitlab-ci.yml",
    "Jenkinsfile",
    ".circleci",
    "azure-pipelines.yml",
]

_LICENCE_FILES = ["LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "LICENCE.md"]


def _detect_tech_stack(root: Path) -> list[str]:
    """Detect technology stack from configuration files."""
    stacks: list[str] = []
    for filename, stack in _TECH_STACK_FILES.items():
        if (root / filename).exists() and stack not in stacks:
            stacks.append(stack)
    return stacks


def _detect_language_breakdown(root: Path) -> dict[str, int]:
    """Rough language breakdown by file extension count."""
    ext_counts: dict[str, int] = {}
    max_walk = 200
    walked = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        # Skip common non-source directories
        parts = Path(dirpath).relative_to(root).parts
        if any(
            p.startswith(
                (
                    ".",
                    "node_modules",
                    "vendor",
                    "target",
                    "dist",
                    "build",
                    "__pycache__",
                    ".venv",
                    "venv",
                )
            )
            for p in parts
        ):
            continue
        for fn in filenames:
            walked += 1
            if walked > max_walk:
                break
            ext = Path(fn).suffix.lower()
            if ext in (".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".lock", ".gitignore"):
                continue
            if ext:
                ext_counts[ext] = ext_counts.get(ext, 0) + 1
        if walked > max_walk:
            break
    return dict(sorted(ext_counts.items(), key=lambda x: -x[1])[:5])


def _detect_entry_points(root: Path, stacks: list[str]) -> list[str]:
    """Guess main entry points."""
    entries: list[str] = []
    for stack in stacks:
        for pattern in _ENTRY_PATTERNS.get(stack, []):
            path = root / pattern
            if path.is_file():
                entries.append(pattern)
            elif path.is_dir():
                entries.append(pattern)
    # Fallback: look for common entry names
    for name in ["main", "index", "app", "server"]:
        for ext in [".py", ".js", ".ts", ".go", ".rs", ".java"]:
            p = root / f"{name}{ext}"
            if p.exists() and str(p.relative_to(root)) not in entries:
                entries.append(str(p.relative_to(root)))
    return entries[:5]


def _detect_test_dirs(root: Path) -> list[str]:
    """Find test directories."""
    found: list[str] = []
    for pattern in _TEST_DIR_PATTERNS:
        p = root / pattern
        if p.is_dir():
            found.append(pattern)
    return found


def _detect_ci(root: Path) -> list[str]:
    """Find CI/CD configuration."""
    found: list[str] = []
    for pattern in _CI_FILES:
        p = root / pattern
        if p.exists():
            found.append(pattern)
    return found


def _read_readme_summary(root: Path) -> str:
    """Extract first paragraph from README."""
    for name in _README_FILES:
        p = root / name
        if p.exists():
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
                lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                # Skip title line
                if lines and lines[0].startswith("#"):
                    lines = lines[1:]
                # Take first meaningful paragraph (up to 3 lines)
                summary_lines: list[str] = []
                for ln in lines:
                    if ln.startswith("#") or ln.startswith("["):
                        continue
                    summary_lines.append(ln)
                    if len(summary_lines) >= 3:
                        break
                return " ".join(summary_lines)
            except Exception:
                pass
    return ""


def _generate_knowhow(root: Path) -> str:
    """Analyze project and generate KnowHow.md content."""
    stacks = _detect_tech_stack(root)
    lang_breakdown = _detect_language_breakdown(root)
    entries = _detect_entry_points(root, stacks)
    test_dirs = _detect_test_dirs(root)
    ci = _detect_ci(root)
    readme_summary = _read_readme_summary(root)
    has_license = any((root / name).exists() for name in _LICENCE_FILES)

    lines: list[str] = [
        "# KnowHow — 项目知识库",
        "",
        "这个文件给 PilotCode（AI 助手）提供项目特定的规范和上下文。",
        "放在 `.pilotcode/` 下，可以随代码库一起版本控制，团队成员共享。",
        "",
    ]

    # Auto-generated section
    lines.append("## 项目概览")
    lines.append("")
    if stacks:
        lines.append(f"- **技术栈**: {', '.join(stacks)}")
    if lang_breakdown:
        top_langs = []
        for ext, count in lang_breakdown.items():
            lang_map = {
                ".py": "Python",
                ".js": "JavaScript",
                ".ts": "TypeScript",
                ".tsx": "TSX",
                ".jsx": "JSX",
                ".rs": "Rust",
                ".go": "Go",
                ".java": "Java",
                ".kt": "Kotlin",
                ".swift": "Swift",
                ".c": "C",
                ".cpp": "C++",
                ".h": "C/C++ Header",
                ".rb": "Ruby",
                ".php": "PHP",
                ".ex": "Elixir",
                ".erl": "Erlang",
                ".scala": "Scala",
            }
            top_langs.append(f"{lang_map.get(ext, ext)} ({count})")
        lines.append(f"- **主要语言**: {', '.join(top_langs)}")
    if entries:
        lines.append(f"- **入口文件**: {', '.join(entries)}")
    if test_dirs:
        lines.append(f"- **测试目录**: {', '.join(test_dirs)}")
    if ci:
        lines.append(f"- **CI/CD**: {', '.join(ci)}")
    if has_license:
        lines.append("- **License**: 已包含")
    if readme_summary:
        lines.append("")
        lines.append(f"> {readme_summary}")
    lines.append("")

    # Guidelines
    lines.extend(
        [
            "## 怎么写",
            "",
            "- 文件顶部写**全局规则**（所有目录都适用）",
            "- 用 `## [相对路径]` 写**目录级规则**（仅在对应目录下生效）",
            "- 路径从项目根目录开始，如 `[src/auth/]`、`[tests/integration/]`",
            "",
            "## 示例",
            "",
            "```",
            "技术栈：Python 3.12 + FastAPI，包管理用 poetry。",
            "",
            "## [src/auth/]",
            "JWT 密钥从环境变量读取，不要硬编码。",
            "修改认证逻辑后，必须跑 `pytest tests/auth/`。",
            "",
            "## [src/payment/]",
            "所有金额计算用 Decimal，禁止 float。",
            "涉及退款必须记录 audit_log。",
            "```",
            "",
            "---",
            "",
        ]
    )

    return "\n".join(lines)


# ------------------------------------------------------------------
# Command
# ------------------------------------------------------------------


async def init_command(args: list[str], context: CommandContext) -> str:
    """Handle /init command.

    Usage:
      /init           - Analyze project and generate/update KnowHow.md
      /init --force   - Overwrite existing KnowHow.md
    """
    cwd = Path(context.cwd) if context.cwd else Path.cwd()
    pilotcode_dir = cwd / ".pilotcode"
    knowhow_path = pilotcode_dir / "KnowHow.md"

    force = "--force" in args or "-f" in args

    if knowhow_path.exists() and not force:
        return (
            f"KnowHow.md already exists at: {knowhow_path}\n"
            "Use `/init --force` to regenerate it."
        )

    # Generate content
    content = _generate_knowhow(cwd)

    # Ensure directory exists
    pilotcode_dir.mkdir(parents=True, exist_ok=True)

    # Write file
    try:
        knowhow_path.write_text(content, encoding="utf-8")
    except Exception as e:
        return f"Failed to write KnowHow.md: {e}"

    # Count sections
    section_count = content.count("## [")
    lines_count = len(content.splitlines())

    return (
        f"✅ Generated KnowHow.md ({lines_count} lines, {section_count} directory sections)\n"
        f"   Path: {knowhow_path}\n"
        f"\n"
        f"Detected:\n" + _format_detected_summary(cwd)
    )


def _format_detected_summary(root: Path) -> str:
    """Format a brief detection summary for the command output."""
    stacks = _detect_tech_stack(root)
    entries = _detect_entry_points(root, stacks)
    test_dirs = _detect_test_dirs(root)

    parts: list[str] = []
    if stacks:
        parts.append(f"  • Tech stack: {', '.join(stacks)}")
    if entries:
        parts.append(f"  • Entry points: {', '.join(entries)}")
    if test_dirs:
        parts.append(f"  • Test dirs: {', '.join(test_dirs)}")
    if not parts:
        parts.append("  • (No strong signals detected — please edit KnowHow.md manually)")
    return "\n".join(parts)


register_command(
    CommandHandler(
        name="init",
        description="Initialize project KnowHow.md by auto-analyzing the codebase",
        handler=init_command,
    )
)
