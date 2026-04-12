"""CodeSearch tool - Semantic and symbol-based code search.

Provides intelligent code retrieval capabilities:
- Semantic search using embeddings
- Symbol lookup (functions, classes, variables)
- File content search
- Context-aware results
"""

from typing import Any, Optional
from enum import Enum
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool
from ..services.codebase_indexer import (
    CodebaseIndexer,
    SearchQuery,
    get_codebase_indexer,
)


class SearchType(str, Enum):
    """Type of code search."""
    
    SEMANTIC = "semantic"  # Natural language semantic search
    SYMBOL = "symbol"      # Symbol name search
    REGEX = "regex"        # Regex pattern search
    FILE = "file"          # File name search


class CodeSearchInput(BaseModel):
    """Input for CodeSearch tool."""
    
    query: str = Field(
        description="Search query (natural language, symbol name, regex pattern, or file pattern)"
    )
    search_type: SearchType = Field(
        default=SearchType.SEMANTIC,
        description="Type of search to perform"
    )
    file_pattern: Optional[str] = Field(
        default=None,
        description="Filter by file pattern (e.g., '*.py', 'src/**/*.js')"
    )
    language: Optional[str] = Field(
        default=None,
        description="Filter by programming language (e.g., 'python', 'javascript')"
    )
    max_results: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of results to return"
    )
    include_content: bool = Field(
        default=True,
        description="Include full content in results"
    )
    context_lines: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Number of context lines to include around matches"
    )


class CodeSearchMatch(BaseModel):
    """A single code search match."""
    
    file_path: str
    start_line: int
    end_line: int
    content: str
    language: str
    symbol_name: Optional[str] = None
    symbol_type: Optional[str] = None
    relevance_score: float = 0.0


class CodeSearchOutput(BaseModel):
    """Output from CodeSearch tool."""
    
    matches: list[CodeSearchMatch]
    total_found: int
    search_type: str
    query: str
    truncated: bool = False


async def code_search_call(
    input_data: CodeSearchInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[CodeSearchOutput]:
    """Execute code search."""
    
    # Get codebase indexer
    indexer = get_codebase_indexer()
    
    # Build search query
    search_query = SearchQuery(
        text=input_data.query,
        query_type=input_data.search_type.value,
        file_pattern=input_data.file_pattern,
        language=input_data.language,
        max_results=input_data.max_results,
        include_content=input_data.include_content,
    )
    
    # Perform search
    try:
        results = await indexer.search(search_query)
    except Exception as e:
        return ToolResult(
            data=CodeSearchOutput(
                matches=[],
                total_found=0,
                search_type=input_data.search_type.value,
                query=input_data.query,
            ),
            error=f"Search failed: {e}"
        )
    
    # Convert to output format
    matches = []
    for snippet in results:
        match = CodeSearchMatch(
            file_path=snippet.file_path,
            start_line=snippet.start_line,
            end_line=snippet.end_line,
            content=snippet.content,
            language=snippet.language,
            symbol_name=snippet.symbol_name,
            symbol_type=snippet.symbol_type,
            relevance_score=snippet.relevance_score,
        )
        matches.append(match)
    
    output = CodeSearchOutput(
        matches=matches,
        total_found=len(matches),
        search_type=input_data.search_type.value,
        query=input_data.query,
        truncated=len(results) >= input_data.max_results,
    )
    
    return ToolResult(data=output)


def code_search_description(input_data: CodeSearchInput, options: dict[str, Any]) -> str:
    """Get description for code search."""
    type_desc = {
        SearchType.SEMANTIC: "semantic code search",
        SearchType.SYMBOL: "symbol lookup",
        SearchType.REGEX: "regex pattern search",
        SearchType.FILE: "file search",
    }
    return f"Performing {type_desc.get(input_data.search_type, 'code search')} for '{input_data.query}'"


def render_code_search_use(input_data: CodeSearchInput, options: dict[str, Any]) -> str:
    """Render code search tool use message."""
    icon = {
        SearchType.SEMANTIC: "🔍",
        SearchType.SYMBOL: "⚡",
        SearchType.REGEX: "📝",
        SearchType.FILE: "📄",
    }.get(input_data.search_type, "🔍")
    
    return f"{icon} CodeSearch: '{input_data.query}' ({input_data.search_type.value})"


# Create the CodeSearch tool
CodeSearchTool = build_tool(
    name="CodeSearch",
    description=code_search_description,
    input_schema=CodeSearchInput,
    output_schema=CodeSearchOutput,
    call=code_search_call,
    aliases=["code_search", "search_code", "cs"],
    search_hint="Search code using semantic, symbol, or regex search",
    max_result_size_chars=50000,
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
    render_tool_use_message=render_code_search_use,
)

# Register the tool
register_tool(CodeSearchTool)
