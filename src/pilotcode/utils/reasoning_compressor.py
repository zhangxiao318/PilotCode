"""Reasoning content compression utility.

Extracts key decision sentences from model reasoning/thinking content
to reduce context window pressure during compaction.
"""

from __future__ import annotations

# Keywords that indicate a decision or key insight in reasoning content
_REASONING_KEYWORDS = [
    "decide",
    "choose",
    "because",
    "conclusion",
    "therefore",
    "thus",
    "因此",
    "决定",
    "选择",
    "问题在",
    "根因",
    "结论",
    "所以",
    "原因是",
    "plan",
    "approach",
    "strategy",
    "方案",
    "计划",
    "策略",
]


def compress_reasoning(reasoning: str | None, max_length: int = 300) -> str | None:
    """Compress reasoning content by extracting key decision sentences.

    If the reasoning is short enough, return as-is.
    Otherwise extract sentences containing decision keywords and join them.

    Args:
        reasoning: Raw reasoning content from the model.
        max_length: Length threshold below which no compression is applied.

    Returns:
        Compressed reasoning or original if short enough.
    """
    if not reasoning or len(reasoning) <= max_length:
        return reasoning

    lines = reasoning.split("\n")
    key_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if any(kw in lower for kw in _REASONING_KEYWORDS):
            key_lines.append(stripped)

    if key_lines:
        summary = " | ".join(key_lines[:5])
        return f"[Thinking summary] {summary}"

    # No key lines found — fall back to head truncation
    return reasoning[:max_length] + "..."
