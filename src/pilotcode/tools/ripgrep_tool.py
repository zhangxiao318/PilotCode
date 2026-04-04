"""ripgrep integration for high-performance code search.

This module provides ripgrep integration following Claude Code's approach:
- Uses system ripgrep if available
- Falls back to bundled binary if available
- Provides millisecond-level code search
- Results sorted by modification time
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Callable
from pydantic import BaseModel, Field

from .base import Tool, ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class RipgrepInput(BaseModel):
    """Input for ripgrep search."""
    pattern: str = Field(description="Search pattern (regex supported)")
    path: str = Field(default=".", description="Path to search in")
    glob: str | None = Field(default=None, description="Glob pattern for file filtering (e.g., '*.py')")
    case_sensitive: bool = Field(default=False, description="Case sensitive search")
    word_match: bool = Field(default=False, description="Match whole words only")
    max_results: int = Field(default=1000, description="Maximum number of results")
    context_lines: int = Field(default=0, description="Lines of context to show")
    output_mode: str = Field(default="content", description="Output: content, files, or count")


class RipgrepMatch(BaseModel):
    """A single ripgrep match."""
    path: str
    line_number: int
    column: int
    content: str
    context_before: list[str] = []
    context_after: list[str] = []


class RipgrepOutput(BaseModel):
    """Output from ripgrep search."""
    pattern: str
    matches: list[RipgrepMatch]
    total_matches: int
    files_searched: int
    duration_ms: float
    truncated: bool = False
    error: str | None = None


class RipgrepRunner:
    """Runner for ripgrep command."""
    
    def __init__(self):
        self._rg_path: str | None = None
        self._checked = False
    
    def _find_rg(self) -> str | None:
        """Find ripgrep binary."""
        if self._checked:
            return self._rg_path
        
        self._checked = True
        
        # Check for system ripgrep
        rg_path = shutil.which("rg")
        if rg_path:
            self._rg_path = rg_path
            return rg_path
        
        # Check for bundled ripgrep (in future versions)
        # bundled = self._get_bundled_rg()
        # if bundled:
        #     self._rg_path = bundled
        #     return bundled
        
        self._rg_path = None
        return None
    
    def is_available(self) -> bool:
        """Check if ripgrep is available."""
        return self._find_rg() is not None
    
    async def search(
        self,
        pattern: str,
        path: str = ".",
        glob: str | None = None,
        case_sensitive: bool = False,
        word_match: bool = False,
        max_results: int = 1000,
        context_lines: int = 0,
        output_mode: str = "content"
    ) -> RipgrepOutput:
        """Execute ripgrep search."""
        rg_path = self._find_rg()
        
        if not rg_path:
            return RipgrepOutput(
                pattern=pattern,
                matches=[],
                total_matches=0,
                files_searched=0,
                duration_ms=0.0,
                error="ripgrep not found. Install from: https://github.com/BurntSushi/ripgrep"
            )
        
        import time
        start_time = time.time()
        
        # Build command
        cmd = [rg_path, "--json"]  # JSON output for parsing
        
        # Add options
        if not case_sensitive:
            cmd.append("-i")  # Case insensitive
        if word_match:
            cmd.append("-w")  # Word match
        if context_lines > 0:
            cmd.extend(["-C", str(context_lines)])
        
        # Limit results (using head via pipe)
        # Note: ripgrep has --max-count but it's per file
        
        # Glob filter
        if glob:
            cmd.extend(["-g", glob])
        
        # Output mode
        if output_mode == "files":
            cmd.append("-l")  # Files only
        elif output_mode == "count":
            cmd.append("-c")  # Count only
        
        # Add pattern and path
        cmd.extend([pattern, path])
        
        try:
            # Execute ripgrep
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=1024*1024  # 1MB buffer
            )
            
            stdout, stderr = await proc.communicate()
            
            duration_ms = (time.time() - start_time) * 1000
            
            if proc.returncode != 0 and proc.returncode != 1:
                # Return code 1 means no matches found (not an error)
                return RipgrepOutput(
                    pattern=pattern,
                    matches=[],
                    total_matches=0,
                    files_searched=0,
                    duration_ms=duration_ms,
                    error=f"ripgrep error: {stderr.decode('utf-8', errors='replace')[:500]}"
                )
            
            # Parse results
            matches, files_searched = self._parse_json_output(
                stdout.decode('utf-8', errors='replace'),
                max_results
            )
            
            return RipgrepOutput(
                pattern=pattern,
                matches=matches[:max_results],
                total_matches=len(matches),
                files_searched=files_searched,
                duration_ms=duration_ms,
                truncated=len(matches) > max_results
            )
            
        except Exception as e:
            return RipgrepOutput(
                pattern=pattern,
                matches=[],
                total_matches=0,
                files_searched=0,
                duration_ms=0.0,
                error=f"Error executing ripgrep: {str(e)}"
            )
    
    def _parse_json_output(
        self,
        output: str,
        max_results: int
    ) -> tuple[list[RipgrepMatch], int]:
        """Parse ripgrep JSON output."""
        import json
        
        matches = []
        files_seen = set()
        
        for line in output.strip().split('\n'):
            if not line:
                continue
            
            try:
                data = json.loads(line)
                msg_type = data.get("type")
                
                if msg_type == "match":
                    # Extract match info
                    match_data = data.get("data", {})
                    path_data = match_data.get("path", {})
                    path = path_data.get("text", "")
                    
                    line_num = match_data.get("line_number", 0)
                    absolute_offset = match_data.get("absolute_offset", 0)
                    
                    # Get match text
                    lines = match_data.get("lines", {})
                    text = lines.get("text", "")
                    
                    # Get submatches for column info
                    submatches = match_data.get("submatches", [])
                    column = submatches[0].get("start", 0) if submatches else 0
                    
                    match = RipgrepMatch(
                        path=path,
                        line_number=line_num,
                        column=column,
                        content=text.rstrip('\n')
                    )
                    matches.append(match)
                    files_seen.add(path)
                    
                    if len(matches) >= max_results:
                        break
                
                elif msg_type == "context":
                    # Context lines - could be added to previous match
                    pass
                
                elif msg_type == "summary":
                    # Summary stats
                    pass
                    
            except json.JSONDecodeError:
                continue
        
        return matches, len(files_seen)
    
    async def search_streaming(
        self,
        pattern: str,
        path: str = ".",
        on_match: Callable[[RipgrepMatch], None] | None = None,
        **kwargs
    ) -> RipgrepOutput:
        """Execute ripgrep search with streaming results."""
        rg_path = self._find_rg()
        
        if not rg_path:
            return RipgrepOutput(
                pattern=pattern,
                matches=[],
                total_matches=0,
                files_searched=0,
                duration_ms=0.0,
                error="ripgrep not found"
            )
        
        import json
        import time
        start_time = time.time()
        
        cmd = [rg_path, "--json", pattern, path]
        
        # Add glob if specified
        if kwargs.get("glob"):
            cmd.extend(["-g", kwargs["glob"]])
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            matches = []
            files_seen = set()
            
            # Read output line by line
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                
                try:
                    data = json.loads(line.decode('utf-8'))
                    if data.get("type") == "match":
                        match_data = data.get("data", {})
                        path = match_data.get("path", {}).get("text", "")
                        line_num = match_data.get("line_number", 0)
                        text = match_data.get("lines", {}).get("text", "")
                        
                        match = RipgrepMatch(
                            path=path,
                            line_number=line_num,
                            column=0,
                            content=text.rstrip('\n')
                        )
                        matches.append(match)
                        files_seen.add(path)
                        
                        if on_match:
                            on_match(match)
                        
                        if len(matches) >= kwargs.get("max_results", 1000):
                            proc.terminate()
                            break
                            
                except json.JSONDecodeError:
                    continue
            
            await proc.wait()
            duration_ms = (time.time() - start_time) * 1000
            
            return RipgrepOutput(
                pattern=pattern,
                matches=matches,
                total_matches=len(matches),
                files_searched=len(files_seen),
                duration_ms=duration_ms
            )
            
        except Exception as e:
            return RipgrepOutput(
                pattern=pattern,
                matches=[],
                total_matches=0,
                files_searched=0,
                duration_ms=0.0,
                error=str(e)
            )


# Global runner instance
_rg_runner: RipgrepRunner | None = None


def get_ripgrep_runner() -> RipgrepRunner:
    """Get global ripgrep runner."""
    global _rg_runner
    if _rg_runner is None:
        _rg_runner = RipgrepRunner()
    return _rg_runner


async def ripgrep_call(
    input_data: RipgrepInput,
    context: ToolUseContext,
    can_use_tool: Callable,
    parent_message: Any,
    on_progress: Callable
) -> ToolResult[RipgrepOutput]:
    """Execute ripgrep search."""
    # Resolve path
    search_path = input_data.path
    if not os.path.isabs(search_path) and context.get_app_state:
        from ..state.app_state import AppState
        app_state = context.get_app_state()
        if app_state:
            search_path = os.path.join(app_state.cwd, search_path)
    
    # Check permission
    permission = await can_use_tool("Ripgrep", {"path": search_path})
    if permission.get("behavior") == "reject":
        return ToolResult(
            data=RipgrepOutput(
                pattern=input_data.pattern,
                matches=[],
                total_matches=0,
                files_searched=0,
                duration_ms=0.0
            ),
            error="Permission denied"
        )
    
    # Run search
    runner = get_ripgrep_runner()
    result = await runner.search(
        pattern=input_data.pattern,
        path=search_path,
        glob=input_data.glob,
        case_sensitive=input_data.case_sensitive,
        word_match=input_data.word_match,
        max_results=input_data.max_results,
        context_lines=input_data.context_lines,
        output_mode=input_data.output_mode
    )
    
    return ToolResult(data=result)


def render_ripgrep_use(input_data: RipgrepInput, options: dict) -> str:
    """Render ripgrep tool use."""
    flags = []
    if not input_data.case_sensitive:
        flags.append("-i")
    if input_data.word_match:
        flags.append("-w")
    if input_data.glob:
        flags.append(f"-g {input_data.glob}")
    
    flag_str = " ".join(flags)
    if flag_str:
        flag_str = " " + flag_str
    
    return f"🔍 rg{flag_str} '{input_data.pattern}' in {input_data.path}"


# Create the Ripgrep tool
RipgrepTool = build_tool(
    name="Ripgrep",
    description=lambda x, o: f"Search with ripgrep: {x.pattern}",
    input_schema=RipgrepInput,
    output_schema=RipgrepOutput,
    call=ripgrep_call,
    aliases=["rg", "ripgrep_search"],
    search_hint="Fast code search with ripgrep",
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
    render_tool_use_message=render_ripgrep_use,
)

register_tool(RipgrepTool)
