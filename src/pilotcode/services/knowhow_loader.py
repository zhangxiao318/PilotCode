"""KnowHow.md loader for project-specific AI instructions.

Dynamically loads rules relevant to the current working directory
from a single `.pilotcode/KnowHow.md` file.
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path
from typing import NamedTuple


class KnowHowSection(NamedTuple):
    """A parsed section from KnowHow.md."""

    path: str  # "" = global, "src/auth/" = directory-level
    content: str


class KnowHowLoader:
    """Load KnowHow.md instructions, dynamically returning rules
    relevant to the current working directory.
    """

    # KnowHow.md lives inside .pilotcode/ at project root
    RELATIVE_PATH = ".pilotcode/KnowHow.md"
    TEMPLATE_PATH = ".pilotcode/KnowHow.template.md"

    # Strip HTML-style comments before parsing (<!-- ... --> including multiline)
    COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)

    SECTION_PATTERN = re.compile(
        r"^##\s+\[(?P<path>[^\]]+)\]\s*$",  # ## [src/auth/]
        re.MULTILINE,
    )

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()
        self.knowhow_path = self.project_root / self.RELATIVE_PATH

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, cwd: str | Path | None = None) -> str:
        """Return global rules + rules for *cwd* (and its parents).

        Example:
            cwd = src/auth/
            Returns: global rules + src/ rules + src/auth/ rules
        """
        if not self.knowhow_path.exists():
            self._create_template()
            return ""

        sections = self._parse()
        target = Path(cwd).resolve() if cwd else self.project_root
        rel = self._relative(target)

        parts: list[str] = []

        # 1. Global rules (path == "")
        for sec in sections:
            if sec.path == "" and sec.content.strip():
                parts.append(sec.content.strip())
                break

        # 2. From root to target directory, load matching rules
        segments = rel.strip("/").split("/") if rel else []
        accumulated = ""
        for seg in segments:
            accumulated = f"{accumulated}{seg}/"
            for sec in sections:
                if sec.path == accumulated and sec.content.strip():
                    parts.append(sec.content.strip())
                    break

        return "\n\n".join(parts)

    def raw(self) -> str:
        """Return the raw file content (for editing)."""
        if not self.knowhow_path.exists():
            self._create_template()
        return self.knowhow_path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse(self) -> list[KnowHowSection]:
        """Split KnowHow.md into global + directory-level sections."""
        text = self.knowhow_path.read_text(encoding="utf-8")
        # Remove HTML-style comments so they never reach the LLM
        text = self.COMMENT_PATTERN.sub("", text)

        matches = list(self.SECTION_PATTERN.finditer(text))
        if not matches:
            return [KnowHowSection("", text)]

        sections: list[KnowHowSection] = []

        # Global content (before first section)
        first_start = matches[0].start()
        if first_start > 0:
            sections.append(KnowHowSection("", text[:first_start]))

        # Directory-level sections
        for i, match in enumerate(matches):
            path = match.group("path").strip().rstrip("/") + "/"
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            sections.append(KnowHowSection(path, text[start:end]))

        return sections

    def _relative(self, target: Path) -> str:
        """Return relative path from project root to target."""
        try:
            return str(target.relative_to(self.project_root)).replace("\\", "/") + "/"
        except ValueError:
            return ""

    def _create_template(self) -> None:
        """Create KnowHow.md (for LLM) and KnowHow.template.md (human guide)."""
        self.knowhow_path.parent.mkdir(parents=True, exist_ok=True)

        # Human-readable guide — never sent to LLM
        guide = textwrap.dedent("""\
            # KnowHow.template.md — 使用指南（仅人类参考）

            `KnowHow.md` 给 PilotCode（AI 助手）提供项目特定规范。
            本文件是模板说明，**不会**发给 LLM，可以安全地留在这里供团队参考。

            ## 怎么写

            - 文件顶部写**全局规则**（所有目录都适用）
            - 用 `## [相对路径]` 写**目录级规则**（仅在对应目录下生效）
            - 路径从项目根目录开始，如 `[src/auth/]`、`[tests/integration/]`
            - 用 HTML 注释 `<!-- 这是注释 -->` 写备注，会被自动过滤，不发给 LLM

            ## 示例

            ```markdown
            技术栈：Python 3.12 + FastAPI，包管理用 poetry。

            <!-- 以下规则仅在 src/auth/ 目录下生效 -->
            ## [src/auth/]
            JWT 密钥从环境变量读取，不要硬编码。
            修改认证逻辑后，必须跑 `pytest tests/auth/`。

            ## [src/payment/]
            所有金额计算用 Decimal，禁止 float。
            涉及退款必须记录 audit_log。
            ```
            """)

        (self.project_root / self.TEMPLATE_PATH).write_text(guide, encoding="utf-8")

        # Minimal KnowHow.md — only content that reaches the LLM
        minimal = textwrap.dedent("""\
            <!-- 本文件内容会被发给 LLM。HTML 注释会被自动过滤。 -->
            <!-- 详细使用指南见同目录下的 KnowHow.template.md -->

            # KnowHow — 项目知识库

            技术栈：Python 3.12 + FastAPI，包管理用 poetry。

            ## [src/auth/]
            JWT 密钥从环境变量读取，不要硬编码。
            修改认证逻辑后，必须跑 `pytest tests/auth/`。

            ## [src/payment/]
            所有金额计算用 Decimal，禁止 float。
            涉及退款必须记录 audit_log。
            """)

        self.knowhow_path.write_text(minimal, encoding="utf-8")
