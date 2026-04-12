"""CodeContext tool - Build code context for LLM from queries.

This tool enables RAG (Retrieval Augmented Generation) by:
1. Understanding the user's query
2. Retrieving relevant code snippets
3. Building a context window within token limits
4. Including related symbols and dependencies
"""

from typing import Any, Optional
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool
from ..services.codebase_indexer import get_codebase_indexer


class CodeContextInput(BaseModel):
    """Input for CodeContext tool."""

    query: str = Field(
        description="The query or topic to build context for (e.g., 'authentication logic', 'database models')"
    )
    max_tokens: int = Field(
        default=4000, ge=500, le=8000, description="Maximum tokens for context window"
    )
    include_related: bool = Field(
        default=True, description="Include related symbols (same file, call graph)"
    )
    file_pattern: Optional[str] = Field(
        default=None, description="Restrict to files matching pattern"
    )
    language: Optional[str] = Field(default=None, description="Restrict to specific language")


class CodeSnippetInfo(BaseModel):
    """Information about a code snippet."""

    file_path: str
    start_line: int
    end_line: int
    content: str
    language: str
    symbol_name: Optional[str] = None
    symbol_type: Optional[str] = None
    relevance: str = "semantic"  # semantic, symbol, related


class CodeContextOutput(BaseModel):
    """Output from CodeContext tool."""

    context: str  # Formatted context for LLM
    snippets: list[CodeSnippetInfo]
    source_files: list[str]
    total_tokens: int
    total_chars: int
    coverage_summary: str


def _format_snippet(snippet: Any) -> str:
    """Format a single snippet for context."""
    lines = []

    # Header with file location
    symbol_info = f" ({snippet.symbol_type} {snippet.symbol_name})" if snippet.symbol_name else ""
    lines.append(f"### {snippet.file_path}:{snippet.start_line}{symbol_info}")
    lines.append("")

    # Content
    lines.append(f"```{snippet.language}")
    lines.append(snippet.content)
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def _generate_coverage_summary(snippets: list[Any], query: str) -> str:
    """Generate a summary of context coverage."""
    if not snippets:
        return "No relevant code found for the query."

    # Group by file
    files = {}
    for s in snippets:
        if s.file_path not in files:
            files[s.file_path] = []
        files[s.file_path].append(s)

    lines = [f"Context covers {len(files)} files:"]
    for file_path, file_snippets in files.items():
        symbols = [s.symbol_name for s in file_snippets if s.symbol_name]
        if symbols:
            lines.append(f"  - {file_path}: {', '.join(symbols[:3])}")
        else:
            lines.append(f"  - {file_path}")

    return "\n".join(lines)


async def code_context_call(
    input_data: CodeContextInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[CodeContextOutput]:
    """Build code context for a query."""

    # Get codebase indexer
    indexer = get_codebase_indexer()

    # Build context
    try:
        context_window = await indexer.build_context(
            query=input_data.query,
            max_tokens=input_data.max_tokens,
            include_related=input_data.include_related,
        )
    except Exception as e:
        return ToolResult(
            data=CodeContextOutput(
                context="",
                snippets=[],
                source_files=[],
                total_tokens=0,
                total_chars=0,
                coverage_summary=f"Error building context: {e}",
            ),
            error=f"Failed to build context: {e}",
        )

    # Filter by file pattern if specified
    snippets = context_window.snippets
    if input_data.file_pattern:
        import fnmatch

        snippets = [s for s in snippets if fnmatch.fnmatch(s.file_path, input_data.file_pattern)]

    if input_data.language:
        snippets = [s for s in snippets if s.language == input_data.language]

    # Format context
    context_parts = []
    context_parts.append(f"# Code Context for: {input_data.query}")
    context_parts.append("")
    context_parts.append("## Retrieved Code Snippets")
    context_parts.append("")

    for snippet in snippets:
        context_parts.append(_format_snippet(snippet))

    formatted_context = "\n".join(context_parts)

    # Build snippet info
    snippet_infos = [
        CodeSnippetInfo(
            file_path=s.file_path,
            start_line=s.start_line,
            end_line=s.end_line,
            content=s.content,
            language=s.language,
            symbol_name=s.symbol_name,
            symbol_type=s.symbol_type,
        )
        for s in snippets
    ]

    coverage_summary = _generate_coverage_summary(snippets, input_data.query)

    output = CodeContextOutput(
        context=formatted_context,
        snippets=snippet_infos,
        source_files=context_window.source_files,
        total_tokens=context_window.total_tokens,
        total_chars=context_window.total_chars,
        coverage_summary=coverage_summary,
    )

    return ToolResult(data=output)


def code_context_description(input_data: CodeContextInput, options: dict[str, Any]) -> str:
    """Get description for code context."""
    return f"Building code context for '{input_data.query}'"


def render_code_context_use(input_data: CodeContextInput, options: dict[str, Any]) -> str:
    """Render code context tool use message."""
    return f"📚 CodeContext: '{input_data.query}'"


# Create the CodeContext tool
CodeContextTool = build_tool(
    name="CodeContext",
    description=code_context_description,
    input_schema=CodeContextInput,
    output_schema=CodeContextOutput,
    call=code_context_call,
    aliases=["code_context", "context", "rag"],
    search_hint="Build code context for a query using RAG",
    max_result_size_chars=100000,
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
    render_tool_use_message=render_code_context_use,
)

# Register the tool
register_tool(CodeContextTool)
