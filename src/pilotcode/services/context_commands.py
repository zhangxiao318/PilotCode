"""Session memory and context retrieval commands.

Usage:
    /context list       — List archived context entries
    /context search kw  — Search archived context by keyword
    /context recall     — Show recent archived entries
    /memory             — Show current session memory summary
"""

from __future__ import annotations


from .context_archive import ContextArchive


def get_archive() -> ContextArchive:
    """Get or create context archive."""
    return ContextArchive()


async def cmd_context_list(args: str) -> str:
    """List all context archives."""
    archive = get_archive()
    archives = archive.list_archives()
    if not archives:
        return "No context archives found."
    lines = ["## Context Archives", ""]
    for a in archives[:10]:
        lines.append(
            f"- {a['archive_id']} ({a['timestamp'][:19]}): "
            f"{a['entry_count']} entries, {a.get('token_saved', 0):,} tokens saved"
        )
        if a.get("summary"):
            lines.append(f"  {a['summary'][:80]}")
    if len(archives) > 10:
        lines.append(f"\n... and {len(archives) - 10} more")
    lines.append(f"\nTotal tokens saved: {archive.get_total_tokens_saved():,}")
    return "\n".join(lines)


async def cmd_context_search(keyword: str) -> str:
    """Search archived context for a keyword."""
    if not keyword:
        return "Usage: /context search <keyword>"
    archive = get_archive()
    results = archive.query_context(keyword, max_results=10)
    if not results:
        return f"No archived context found matching '{keyword}'."
    lines = [f"## Context matching '{keyword}'", ""]
    for r in results:
        lines.append(f"- [{r.get('message_type', '?')}] {r.get('content', '')[:150]}")
    return "\n".join(lines)


async def cmd_context_recall(args: str) -> str:
    """Show recent archived entries."""
    archive = get_archive()
    entries = archive.get_recent_context(count=5)
    if not entries:
        return "No recent context found."
    lines = ["## Recent Archived Context", ""]
    for e in entries:
        lines.append(f"- [{e.get('message_type', '?')}] {e.get('content', '')[:200]}")
    return "\n".join(lines)


async def cmd_memory(args: str) -> str:
    """Show current session memory."""
    archive = get_archive()
    mem = archive.session_memory
    if not mem.primary_request and not mem.files_examined:
        return "No session memory recorded yet."
    return mem.to_prompt_section()
