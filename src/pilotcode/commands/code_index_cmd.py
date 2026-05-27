"""/index command - Manage codebase index for intelligent search.

Usage:
    /index              - Index the codebase incrementally
    /index full         - Full reindex
    /index stats        - Show index statistics
    /index clear        - Clear the index
    /index export       - Export index to file
    /index import       - Import index from file
"""

import asyncio
import time
from pathlib import Path

from .base import CommandHandler, register_command
from ..types.command import CommandContext
from ..services.codebase_indexer import get_codebase_indexer


def _parse_index_args(args: list[str]) -> tuple[str, int | None]:
    """Parse /index arguments, extracting subcommand and --batch-size.

    Returns (subcommand, batch_size).
    """
    cmd = "incremental"
    batch_size = None

    i = 0
    while i < len(args):
        a = args[i].strip().lower()
        if a in ("", "incremental", "full", "stats", "clear", "export", "import"):
            cmd = a if a else "incremental"
        elif a in ("--batch-size", "-b") and i + 1 < len(args):
            try:
                batch_size = int(args[i + 1])
            except ValueError:
                pass
            i += 1
        i += 1

    return cmd, batch_size


def _report_progress(context: CommandContext, msg: str) -> None:
    """Send progress to UI if a callback is registered, else print."""
    if context.progress_callback:
        context.progress_callback(msg)
    else:
        print(msg)


async def index_command_handler(
    args: list[str],
    context: CommandContext,
) -> str:
    """Handle /index command."""

    cmd, batch_size = _parse_index_args(args)

    # Re-create indexer with optional larger batch size for big codebases
    if batch_size:
        from ..services.codebase_indexer import CodebaseIndexer

        indexer = CodebaseIndexer(context.cwd, batch_size=batch_size)
    else:
        indexer = get_codebase_indexer(context.cwd)

    if cmd in ("", "incremental"):
        _report_progress(context, f"🗂️  Indexing codebase in: {context.cwd}")

        files = await asyncio.to_thread(indexer._find_source_files)
        _report_progress(context, f"📁 Found {len(files)} source files to index")

        if not files:
            return (
                f"No source files found in {context.cwd}\n\n"
                f"Supported extensions: {', '.join(sorted(indexer.SUPPORTED_EXTENSIONS))[:100]}...\n"
                f"Ignored directories: {', '.join(list(indexer.IGNORE_DIRS)[:5])}...\n\n"
                "Try:\n"
                "  1. Check you're in the right directory (/pwd)\n"
                "  2. Use '/index full' for full reindex\n"
                "  3. Check if files exist: /bash command='find . -name '*.py' | head'\n"
            )

        _report_progress(context, "⏳ Starting index...")
        start_time = time.time()

        def _on_progress(file_path: str, current: int, total: int) -> None:
            pct = current / total * 100 if total else 0
            elapsed = time.time() - start_time
            remaining = (elapsed / current) * (total - current) if current else 0
            _report_progress(
                context,
                f"[CodeIndex] {current}/{total} ({pct:.0f}%) ~{remaining:.0f}s remaining",
            )

        indexer.set_progress_callback(_on_progress)
        stats = await indexer.index_codebase(incremental=True)
        indexer.set_progress_callback(None)

        lang_lines = []
        for lang, count in sorted(stats.languages.items(), key=lambda x: -x[1])[:5]:
            lang_lines.append(f"  {lang}: {count} files")

        return (
            "✅ Indexing complete!\n\n"
            f"📊 Statistics:\n"
            f"  Files indexed: {stats.total_files}\n"
            f"  Symbols: {stats.total_symbols}\n"
            f"  Snippets: {stats.total_snippets}\n\n"
            f"📝 Top Languages:\n"
            f"{chr(10).join(lang_lines)}\n"
        )

    elif cmd == "full":
        _report_progress(context, f"🗂️  Performing full reindex in: {context.cwd}")

        files = await asyncio.to_thread(indexer._find_source_files)
        _report_progress(context, f"📁 Found {len(files)} source files to index")

        if not files:
            return (
                f"No source files found in {context.cwd}\n\n"
                f"Supported extensions: {', '.join(sorted(indexer.SUPPORTED_EXTENSIONS))}\n"
                f"Ignored directories: {', '.join(sorted(indexer.IGNORE_DIRS))}\n\n"
                "Try:\n"
                "  1. Check you're in the right directory (/pwd)\n"
                "  2. Check if files exist: /bash command='find . -name '*.py' | head -5'\n"
                "  3. List current directory: /ls\n"
            )

        _report_progress(context, "⏳ Starting full reindex...")
        start_time = time.time()

        def _on_progress(file_path: str, current: int, total: int) -> None:
            pct = current / total * 100 if total else 0
            elapsed = time.time() - start_time
            remaining = (elapsed / current) * (total - current) if current else 0
            _report_progress(
                context,
                f"[CodeIndex] {current}/{total} ({pct:.0f}%) ~{remaining:.0f}s remaining",
            )

        indexer.clear_index()
        indexer.set_progress_callback(_on_progress)
        stats = await indexer.index_codebase(incremental=False)
        indexer.set_progress_callback(None)

        return (
            "✅ Full reindex complete!\n\n"
            f"📊 Statistics:\n"
            f"  Files indexed: {stats.total_files}\n"
            f"  Symbols: {stats.total_symbols}\n"
            f"  Snippets: {stats.total_snippets}\n"
        )

    elif cmd == "stats":
        stats = indexer.get_stats()

        from datetime import datetime

        last_indexed = (
            datetime.fromtimestamp(stats.last_indexed).strftime("%Y-%m-%d %H:%M:%S")
            if stats.last_indexed
            else "Never"
        )

        lang_lines = []
        for lang, count in sorted(stats.languages.items(), key=lambda x: -x[1]):
            lang_lines.append(f"  {lang}: {count} files")

        return (
            "📊 Index Statistics\n\n"
            f"Files: {stats.total_files}\n"
            f"Symbols: {stats.total_symbols}\n"
            f"Snippets: {stats.total_snippets}\n"
            f"Last Indexed: {last_indexed}\n\n"
            f"Languages:\n"
            f"{chr(10).join(lang_lines) if lang_lines else '  (none)'}\n"
        )

    elif cmd == "clear":
        indexer.clear_index()
        return "✅ Index cleared successfully"

    elif cmd == "export":
        file_path = args[1] if len(args) > 1 else str(Path(context.cwd) / ".pilotcode_index.json")

        try:
            indexer.export_index(file_path)
            return f"✅ Index exported to {file_path}"
        except Exception as e:
            return f"❌ Export failed: {e}"

    elif cmd == "import":
        file_path = args[1] if len(args) > 1 else str(Path(context.cwd) / ".pilotcode_index.json")

        try:
            indexer.import_index(file_path)
            stats = indexer.get_stats()
            return f"✅ Index imported from {file_path}\nFiles: {stats.total_files}, Symbols: {stats.total_symbols}"
        except Exception as e:
            return f"❌ Import failed: {e}"

    else:
        return (
            f"Unknown subcommand: {cmd}\n\n"
            "Usage:\n"
            "  /index              - Incremental index\n"
            "  /index full         - Full reindex\n"
            "  /index stats        - Show statistics\n"
            "  /index clear        - Clear index\n"
            "  /index export       - Export to .pilotcode_index.json\n"
            "  /index import       - Import from file\n"
        )


# Register the command
register_command(
    CommandHandler(
        name="index",
        description="Manage codebase index for intelligent search",
        handler=index_command_handler,
        aliases=["idx", "reindex"],
    )
)
