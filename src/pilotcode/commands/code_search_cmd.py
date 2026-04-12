"""/search command - Search codebase using semantic and symbol search.

Usage:
    /search <query>              - Semantic search (default)
    /search -s <symbol>          - Symbol search
    /search -r <pattern>         - Regex search
    /search -f <file_pattern>    - File search
    /search -l <language>        - Filter by language
"""

import asyncio
from typing import Optional, Any

from .base import CommandHandler, register_command
from ..types.command import CommandContext
from ..services.codebase_indexer import get_codebase_indexer, SearchQuery


async def search_command_handler(
    args: list[str],
    context: CommandContext,
) -> str:
    """Handle /search command."""
    
    indexer = get_codebase_indexer(context.cwd)
    
    # Parse arguments
    search_type = "semantic"
    file_pattern = None
    language = None
    max_results = 10
    query_parts = []
    
    i = 0
    while i < len(args):
        token = args[i]
        
        if token in ("-s", "--symbol"):
            search_type = "symbol"
            i += 1
            if i < len(args):
                query_parts.append(args[i])
        elif token in ("-r", "--regex"):
            search_type = "regex"
            i += 1
            if i < len(args):
                query_parts.append(args[i])
        elif token in ("-f", "--file"):
            search_type = "file"
            i += 1
            if i < len(args):
                query_parts.append(args[i])
        elif token in ("-l", "--lang"):
            i += 1
            if i < len(args):
                language = args[i]
        elif token in ("-n", "--max"):
            i += 1
            if i < len(args):
                try:
                    max_results = int(args[i])
                except ValueError:
                    pass
        elif token.startswith("-"):
            # Unknown flag
            pass
        else:
            query_parts.append(token)
        
        i += 1
    
    query = " ".join(query_parts).strip()
    
    if not query:
        return f"""Usage: /search <query> [options]

Options:
  -s, --symbol <name>     Search by symbol name
  -r, --regex <pattern>   Search using regex
  -f, --file <pattern>    Search file names
  -l, --lang <language>   Filter by language
  -n, --max <number>      Max results (default: 10)

Examples:
  /search authentication logic
  /search -s UserModel
  /search -r "def.*auth"
  /search -f "*.py" -l python
"""
    
    # Check if index exists
    stats = indexer.get_stats()
    if stats.total_files == 0:
        return """No index found. Please run '/index' first to build the code index.

The index enables fast semantic and symbol-based code search.
"""
    
    # Perform search
    print(f"🔍 Searching for '{query}'...")
    
    search_query = SearchQuery(
        text=query,
        query_type=search_type,
        file_pattern=file_pattern,
        language=language,
        max_results=max_results,
    )
    
    try:
        results = await indexer.search(search_query)
    except Exception as e:
        return f"Search failed: {e}"
    
    if not results:
        return f"No results found for '{query}'"
    
    # Format results
    lines = [f"Found {len(results)} results for '{query}':\n"]
    
    for i, snippet in enumerate(results, 1):
        # Header
        symbol_info = f" ({snippet.symbol_type} {snippet.symbol_name})" if snippet.symbol_name else ""
        lines.append(f"{i}. {snippet.file_path}:{snippet.start_line}{symbol_info}")
        
        # Score
        lines.append(f"   Relevance: {snippet.relevance_score:.2f}")
        
        # Content preview
        content = snippet.content
        if len(content) > 300:
            content = content[:300] + "..."
        
        lines.append(f"   ```{snippet.language}")
        for line in content.split("\n")[:8]:  # Limit lines
            lines.append(f"   {line}")
        if len(content.split("\n")) > 8:
            lines.append("   ...")
        lines.append("   ```")
        lines.append("")
    
    return "\n".join(lines)


# Register the command
register_command(
    CommandHandler(
        name="search",
        description="Search codebase using semantic and symbol search",
        handler=search_command_handler,
        aliases=["find_code", "lookup"],
    )
)
