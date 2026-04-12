"""CodeIndex tool - Index and manage codebase for intelligent search.

Provides commands to:
- Index the codebase (full or incremental)
- Get indexing statistics
- Export/import index
- Clear index
"""

import asyncio
from typing import Any, Optional
from enum import Enum
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool
from ..services.codebase_indexer import get_codebase_indexer, CodebaseStats


class IndexAction(str, Enum):
    """Action to perform on the code index."""

    INDEX = "index"  # Index or reindex
    STATS = "stats"  # Get statistics
    CLEAR = "clear"  # Clear index
    EXPORT = "export"  # Export to file
    IMPORT = "import"  # Import from file


class CodeIndexInput(BaseModel):
    """Input for CodeIndex tool."""

    action: IndexAction = Field(default=IndexAction.INDEX, description="Action to perform")
    incremental: bool = Field(
        default=True, description="For 'index' action: only index changed files"
    )
    max_files: Optional[int] = Field(
        default=None, description="For 'index' action: limit number of files"
    )
    file_path: Optional[str] = Field(
        default=None, description="For 'export'/'import': path to index file"
    )


class LanguageStats(BaseModel):
    """Statistics for a language."""

    language: str
    file_count: int


class CodeIndexOutput(BaseModel):
    """Output from CodeIndex tool."""

    success: bool
    message: str
    stats: Optional[CodebaseStats] = None
    languages: list[LanguageStats] = []
    indexed_files: Optional[int] = None
    elapsed_seconds: Optional[float] = None


async def code_index_call(
    input_data: CodeIndexInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[CodeIndexOutput]:
    """Execute code index operation."""

    indexer = get_codebase_indexer()

    if input_data.action == IndexAction.INDEX:
        # Index the codebase
        import time

        start_time = time.time()

        try:
            stats = await indexer.index_codebase(
                incremental=input_data.incremental,
                max_files=input_data.max_files,
            )
            elapsed = time.time() - start_time

            languages = [
                LanguageStats(language=lang, file_count=count)
                for lang, count in stats.languages.items()
            ]
            languages.sort(key=lambda x: x.file_count, reverse=True)

            message = f"Indexed {stats.total_files} files ({stats.total_symbols} symbols, {stats.total_snippets} snippets) in {elapsed:.1f}s"

            output = CodeIndexOutput(
                success=True,
                message=message,
                stats=stats,
                languages=languages,
                indexed_files=stats.total_files,
                elapsed_seconds=elapsed,
            )

        except Exception as e:
            output = CodeIndexOutput(
                success=False,
                message=f"Indexing failed: {e}",
            )

    elif input_data.action == IndexAction.STATS:
        # Get statistics
        stats = indexer.get_stats()

        languages = [
            LanguageStats(language=lang, file_count=count)
            for lang, count in stats.languages.items()
        ]
        languages.sort(key=lambda x: x.file_count, reverse=True)

        from datetime import datetime

        last_indexed = (
            datetime.fromtimestamp(stats.last_indexed).strftime("%Y-%m-%d %H:%M:%S")
            if stats.last_indexed
            else "Never"
        )

        message = f"Codebase: {stats.total_files} files, {stats.total_symbols} symbols, last indexed: {last_indexed}"

        output = CodeIndexOutput(
            success=True,
            message=message,
            stats=stats,
            languages=languages,
        )

    elif input_data.action == IndexAction.CLEAR:
        # Clear index
        indexer.clear_index()
        output = CodeIndexOutput(
            success=True,
            message="Index cleared successfully",
        )

    elif input_data.action == IndexAction.EXPORT:
        # Export index
        if not input_data.file_path:
            output = CodeIndexOutput(
                success=False,
                message="file_path is required for export",
            )
        else:
            try:
                indexer.export_index(input_data.file_path)
                output = CodeIndexOutput(
                    success=True,
                    message=f"Index exported to {input_data.file_path}",
                )
            except Exception as e:
                output = CodeIndexOutput(
                    success=False,
                    message=f"Export failed: {e}",
                )

    elif input_data.action == IndexAction.IMPORT:
        # Import index
        if not input_data.file_path:
            output = CodeIndexOutput(
                success=False,
                message="file_path is required for import",
            )
        else:
            try:
                indexer.import_index(input_data.file_path)
                stats = indexer.get_stats()
                output = CodeIndexOutput(
                    success=True,
                    message=f"Index imported from {input_data.file_path}",
                    stats=stats,
                )
            except Exception as e:
                output = CodeIndexOutput(
                    success=False,
                    message=f"Import failed: {e}",
                )

    else:
        output = CodeIndexOutput(
            success=False,
            message=f"Unknown action: {input_data.action}",
        )

    return ToolResult(data=output)


def code_index_description(input_data: CodeIndexInput, options: dict[str, Any]) -> str:
    """Get description for code index."""
    descriptions = {
        IndexAction.INDEX: "Indexing codebase",
        IndexAction.STATS: "Getting index statistics",
        IndexAction.CLEAR: "Clearing index",
        IndexAction.EXPORT: "Exporting index",
        IndexAction.IMPORT: "Importing index",
    }
    return descriptions.get(input_data.action, "Managing code index")


def render_code_index_use(input_data: CodeIndexInput, options: dict[str, Any]) -> str:
    """Render code index tool use message."""
    icons = {
        IndexAction.INDEX: "🗂️",
        IndexAction.STATS: "📊",
        IndexAction.CLEAR: "🗑️",
        IndexAction.EXPORT: "📤",
        IndexAction.IMPORT: "📥",
    }
    icon = icons.get(input_data.action, "🗂️")
    return f"{icon} CodeIndex: {input_data.action.value}"


# Create the CodeIndex tool
CodeIndexTool = build_tool(
    name="CodeIndex",
    description=code_index_description,
    input_schema=CodeIndexInput,
    output_schema=CodeIndexOutput,
    call=code_index_call,
    aliases=["code_index", "index_code", "idx"],
    search_hint="Index and manage codebase for intelligent search",
    max_result_size_chars=10000,
    is_read_only=lambda input_data: input_data.action not in [IndexAction.INDEX, IndexAction.CLEAR],
    is_concurrency_safe=lambda _: False,  # Indexing should not run concurrently
    render_tool_use_message=render_code_index_use,
)

# Register the tool
register_tool(CodeIndexTool)
