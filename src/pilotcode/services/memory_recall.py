"""Memory recall for query-time retrieval of relevant memories.

Scans the memory directory and returns topic files relevant to the current query.
Uses lightweight keyword matching (no LLM call) for fast, deterministic recall.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .memory_dir import scan_memory_files

MAX_RECALL_FILES = 5
MAX_MEMORY_LINES = 100
MAX_MEMORY_BYTES = 10_000


def find_relevant_memories(
    query: str,
    cwd: str | Path,
    top_k: int = 3,
) -> list[dict[str, str]]:
    """Find memory files relevant to a query using keyword overlap scoring.

    Args:
        query: User's input query.
        cwd: Project working directory (memory dir is derived from it).
        top_k: Maximum number of memories to return.

    Returns:
        List of memory metadata dicts with keys: filename, path, description,
        type, tags. Sorted by relevance (best first).
    """
    memories = scan_memory_files(cwd)
    if not memories:
        return []

    query_words = set(re.findall(r"[a-zA-Z0-9_\u4e00-\u9fff]+", query.lower()))
    if not query_words:
        return []

    scored: list[tuple[float, dict[str, str]]] = []
    for m in memories:
        text = " ".join(
            [
                str(m.get("description", "")).lower(),
                str(m.get("filename", "")).lower(),
                " ".join(str(t).lower() for t in m.get("tags", [])),
                str(m.get("type", "")).lower(),
            ]
        )
        text_words = set(re.findall(r"[a-zA-Z0-9_\u4e00-\u9fff]+", text))
        overlap = query_words & text_words
        if overlap:
            score = len(overlap) / len(query_words)
            scored.append((score, m))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for s, m in scored[:top_k] if s > 0]


def load_memory_content(path: str) -> Optional[str]:
    """Read a memory file with line/byte limits for safe injection.

    Args:
        path: Absolute path to the memory file.

    Returns:
        Truncated file content, or None if unreadable.
    """
    p = Path(path)
    if not p.exists():
        return None
    try:
        raw = p.read_text(encoding="utf-8")
        lines = raw.splitlines()
        if len(lines) > MAX_MEMORY_LINES:
            lines = lines[:MAX_MEMORY_LINES]
            lines.append("> (content truncated due to line limit)")
        content = "\n".join(lines)
        if len(content) > MAX_MEMORY_BYTES:
            cut = content.rfind("\n", 0, MAX_MEMORY_BYTES)
            content = content[: cut if cut > 0 else MAX_MEMORY_BYTES]
            content += "\n\n> (content truncated due to size limit)"
        return content
    except Exception:
        return None


def format_memory_attachment(memories: list[dict[str, str]]) -> str:
    """Format relevant memories into a single prompt section for injection.

    Args:
        memories: Output from find_relevant_memories().

    Returns:
        Markdown string ready to be injected as a system message.
    """
    if not memories:
        return ""

    parts = ["## Relevant Memories", ""]
    for m in memories:
        content = load_memory_content(m.get("path", ""))
        if content:
            parts.append(f"### {m.get('filename', 'memory')}")
            parts.append(content)
            parts.append("")

    return "\n".join(parts)
