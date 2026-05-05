"""Plan mode decision logic — when to plan vs when to execute directly.

Reference: Claude Code EnterPlanModeTool/prompt.ts + coordinatorMode.ts

Design:
- Lightweight heuristics (no LLM call needed to decide)
- Rule-based: explicit keywords, complexity signals, request patterns
- Claude Code's guidance: plan for multi-file/architecture/ambiguous tasks,
  execute directly for single-edit/clear-fix/obvious tasks.
"""

from __future__ import annotations

import re
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Signals that favor planning
# ---------------------------------------------------------------------------

_PLAN_KEYWORDS = [
    "plan",
    "design",
    "architecture",
    "architecture",
    "strategy",
    "approach",
    "steps",
    "decompose",
    "break down",
    "规划",
    "计划",
    "设计",
    "架构",
    "方案",
    "步骤",
    "拆解",
]

_IMPLEMENT_KEYWORDS = [
    "implement",
    "create",
    "build",
    "add",
    "write",
    "develop",
    "实现",
    "创建",
    "构建",
    "添加",
    "写入",
    "开发",
]

_ANALYSIS_KEYWORDS = [
    "analyze",
    "review",
    "explain",
    "understand",
    "investigate",
    "分析",
    "审查",
    "解释",
    "理解",
    "调查",
]

_MULTI_FILE_INDICATORS = [
    r"\b(multi|several|multiple|various|all the)\s+(file|module|component)s?\b",
    r"\b(all|every)\s+(file|module|component|directory|folder)s?\b",
    r"\b(full|complete|entire)\s+(project|application|system|stack)\b",
    r"\b(across|throughout|through)\s+(the\s+)?(project|codebase|app)\b",
]

_DIRECT_EXECUTE_PATTERNS = [
    r"^(read|show|display|list|cat|head|tail|locate)\s",
    r"^(fix typo|fix the typo|correct typo)\s",
    r"^(how|where|who|when|which|why)\s",
    r"^(查看|显示|列出|读取|找到|搜索|什么是|怎么)\s",
    r"^(debug|fix)\s+(this|the)\s+(bug|error|issue|problem)\b",
    r"^change\s+(\w+\s+){0,3}(to|from|in)\s",
    r"^add\s+a\s+(parameter|argument|field|property|flag)\b",
    r"^rename\s+",
    r"^delete\s+",
    r"^remove\s+",
    r"^find\s+(the\s+)?(\w+\s+){0,3}(file|function|method|class|variable|definition)\b",
]

_SINGLE_FILE_CHANGE = re.compile(
    r"^(change|edit|update|modify|fix|add|remove|delete)\s+"
    r"(the\s+)?`?[\w/.-]+`?\s+(file|function|method|class|line|variable)\b",
    re.IGNORECASE,
)

_AMBIGUOUS_ARCHITECTURE = re.compile(
    r"\b(versus|vs\.?|tradeoffs?|pros? and cons?|compare)\b"
    r"|\b(or\s+(should|would|could|will|might|may|do|does|did|is|are|was|were))\b"
    r"|\b(\w+\s+or\s+\w+)\b",  # "WebSocket or SSE", "Redis or PostgreSQL"
    re.IGNORECASE,
)

_FULL_SCOPE_INDICATORS = re.compile(
    r"\b(full|complete|entire|comprehensive|end.to.end)\s+\w+" r"|\w*(完整|全部|整个|全面)\w*",
    re.IGNORECASE,
)


def get_project_file_count(project_root: str | None = None) -> int:
    """Roughly estimate the size of the project.

    Args:
        project_root: Project root directory. Defaults to cwd.

    Returns:
        Approximate file count.
    """
    root = project_root or os.getcwd()
    count = 0
    try:
        for _ in Path(root).rglob("*"):
            count += 1
            if count > 10000:
                return 10000
    except Exception:
        pass
    return count


def should_plan(
    user_request: str,
    project_root: str | None = None,
    force_plan: bool = False,
) -> str:
    """Decide whether to enter plan mode before execution.

    Args:
        user_request: The user's request text.
        project_root: Project root for file count heuristics.
        force_plan: If True (user typed /plan or similar), always plan.

    Returns:
        One of:
            "plan"       → Enter full plan mode with exploration
            "direct"     → Execute directly without planning
            "analyze"    → Analysis task, read-only
            "auto"       → Let the system decide at runtime
    """
    text = user_request.strip()

    # ------------------------------------------------------------------
    # Rule 1: User explicitly wants planning (force, plan keyword, plan verb)
    # ------------------------------------------------------------------
    if force_plan:
        return "plan"
    if _has_any(text, _PLAN_KEYWORDS):
        return "plan"
    if re.match(r"^(plan|design|architect)\b", text, re.IGNORECASE):
        return "plan"

    # ------------------------------------------------------------------
    # Rule 2: Obvious read-only operations → direct
    # ------------------------------------------------------------------
    if re.match(r"^(read|show|display|list|cat|head|tail)\s", text, re.IGNORECASE):
        return "direct"
    for pat in _DIRECT_EXECUTE_PATTERNS:
        if re.match(pat, text, re.IGNORECASE):
            return "direct"

    # ------------------------------------------------------------------
    # Rule 3: Pure analysis / investigation → analyze
    # ------------------------------------------------------------------
    if _has_any(text, _ANALYSIS_KEYWORDS):
        if not _has_any(text, _IMPLEMENT_KEYWORDS):
            return "analyze"
        # Mixed: analyze + implement → plan
        return "plan"

    # ------------------------------------------------------------------
    # Rule 4: Multi-file / broad scope indicators → plan
    # ------------------------------------------------------------------
    if _has_any_re(text, _MULTI_FILE_INDICATORS):
        return "plan"

    # ------------------------------------------------------------------
    # Rule 5: Full-scope indicators (complete auth system, etc.) → plan
    # ------------------------------------------------------------------
    if _FULL_SCOPE_INDICATORS.search(text):
        return "plan"

    # ------------------------------------------------------------------
    # Rule 6: Ambiguous / architectural decisions → plan
    # ------------------------------------------------------------------
    if _AMBIGUOUS_ARCHITECTURE.search(text):
        return "plan"

    # ------------------------------------------------------------------
    # Rule 7: Implementation keywords → plan (unless very short/simple)
    # ------------------------------------------------------------------
    if _has_any(text, _IMPLEMENT_KEYWORDS):
        # Very short implement requests are simple enough to do directly
        if len(text) < 40:
            return "direct"
        return "plan"

    # ------------------------------------------------------------------
    # Rule 8: Very short requests → direct
    # ------------------------------------------------------------------
    if len(text) < 80:
        return "direct"

    # ------------------------------------------------------------------
    # Rule 9: Single-file change → direct
    # ------------------------------------------------------------------
    if _SINGLE_FILE_CHANGE.match(text):
        return "direct"

    # ------------------------------------------------------------------
    # Rule 10: Project size heuristic → plan for large projects
    # ------------------------------------------------------------------
    file_count = get_project_file_count(project_root)
    if file_count > 500:
        return "plan"

    # ------------------------------------------------------------------
    # Default
    # ------------------------------------------------------------------
    return "auto"


def _has_any(text: str, keywords: list[str]) -> bool:
    """Check if text contains any of the keywords."""
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            return True
    return False


def _has_any_re(text: str, patterns: list[str]) -> bool:
    """Check if text matches any regex pattern."""
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return False
