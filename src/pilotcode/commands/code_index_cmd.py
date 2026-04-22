"""/index command - Manage codebase index for intelligent search.

Usage:
    /index              - Index the codebase incrementally
    /index full         - Full reindex
    /index stats        - Show index statistics
    /index clear        - Clear the index
    /index export       - Export index to file
    /index import       - Import index from file
"""

from pathlib import Path
from typing import Any

from .base import CommandHandler, register_command
from ..types.command import CommandContext
from ..services.codebase_indexer import get_codebase_indexer


async def index_command_handler(
    args: list[str],
    context: CommandContext,
) -> str:
    """Handle /index command."""

    indexer = get_codebase_indexer(context.cwd)

    # Parse arguments
    cmd = args[0] if args else "incremental"
    cmd = cmd.strip().lower()

    if cmd in ("", "incremental"):
        # Incremental indexing
        print(f"🗂️  Indexing codebase in: {context.cwd}")

        # First, find files without indexing to show what will be indexed
        files = indexer._find_source_files()
        print(f"📁 Found {len(files)} source files to index")

        if not files:
            return f"""No source files found in {context.cwd}

Supported extensions: {', '.join(sorted(indexer.SUPPORTED_EXTENSIONS))[:100]}...
Ignored directories: {', '.join(list(indexer.IGNORE_DIRS)[:5])}...

Try:
  1. Check you're in the right directory (/pwd)
  2. Use '/index full' for full reindex
  3. Check if files exist: /bash command="find . -name '*.py' | head"
"""

        print(f"⏳ Starting index...")
        stats = await indexer.index_codebase(incremental=True)

        # Format language stats
        lang_lines = []
        for lang, count in sorted(stats.languages.items(), key=lambda x: -x[1])[:5]:
            lang_lines.append(f"  {lang}: {count} files")

        message = f"""✅ Indexing complete!

📊 Statistics:
  Files indexed: {stats.total_files}
  Symbols: {stats.total_symbols}
  Snippets: {stats.total_snippets}

📝 Top Languages:
{chr(10).join(lang_lines)}
"""
        return message

    elif cmd == "full":
        # Full reindex
        print(f"🗂️  Performing full reindex in: {context.cwd}")

        # First, find files without indexing to show what will be indexed
        files = indexer._find_source_files()
        print(f"📁 Found {len(files)} source files to index")

        if not files:
            return f"""No source files found in {context.cwd}

Supported extensions: {', '.join(sorted(indexer.SUPPORTED_EXTENSIONS))}
Ignored directories: {', '.join(sorted(indexer.IGNORE_DIRS))}

Try:
  1. Check you're in the right directory (/pwd)
  2. Check if files exist: /bash command="find . -name '*.py' | head -5"
  3. List current directory: /ls
"""

        print(f"⏳ Starting full reindex...")
        indexer.clear_index()
        stats = await indexer.index_codebase(incremental=False)

        message = f"""✅ Full reindex complete!

📊 Statistics:
  Files indexed: {stats.total_files}
  Symbols: {stats.total_symbols}
  Snippets: {stats.total_snippets}
"""
        return message

    elif cmd == "stats":
        # Show stats
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

        message = f"""📊 Index Statistics

Files: {stats.total_files}
Symbols: {stats.total_symbols}
Snippets: {stats.total_snippets}
Last Indexed: {last_indexed}

Languages:
{chr(10).join(lang_lines) if lang_lines else "  (none)"}
"""
        return message

    elif cmd == "clear":
        # Clear index
        indexer.clear_index()
        return "✅ Index cleared successfully"

    elif cmd == "export":
        # Export index
        file_path = args[1] if len(args) > 1 else str(Path(context.cwd) / ".pilotcode_index.json")

        try:
            indexer.export_index(file_path)
            return f"✅ Index exported to {file_path}"
        except Exception as e:
            return f"❌ Export failed: {e}"

    elif cmd == "import":
        # Import index
        file_path = args[1] if len(args) > 1 else str(Path(context.cwd) / ".pilotcode_index.json")

        try:
            indexer.import_index(file_path)
            stats = indexer.get_stats()
            return f"✅ Index imported from {file_path}\nFiles: {stats.total_files}, Symbols: {stats.total_symbols}"
        except Exception as e:
            return f"❌ Import failed: {e}"

    else:
        return f"""Unknown subcommand: {cmd}

Usage:
  /index              - Incremental index
  /index full         - Full reindex
  /index stats        - Show statistics
  /index clear        - Clear index
  /index export       - Export to .pilotcode_index.json
  /index import       - Import from file
"""


# Register the command
register_command(
    CommandHandler(
        name="index",
        description="Manage codebase index for intelligent search",
        handler=index_command_handler,
        aliases=["idx", "reindex"],
    )
)
