"""Tools module for ClaudeDecode."""

from .base import (
    Tool,
    ToolResult,
    ToolProgressData,
    ToolInput,
    ToolOutput,
    ToolUseContext,
    build_tool,
    tool_matches_name,
)
from .registry import (
    ToolRegistry,
    get_tool_registry,
    register_tool,
    get_all_tools,
    get_tool_by_name,
    assemble_tool_pool,
)

# Import all tools to register them
from .bash_tool import BashTool
from .file_read_tool import FileReadTool
from .file_write_tool import FileWriteTool
from .file_edit_tool import FileEditTool
from .glob_tool import GlobTool
from .grep_tool import GrepTool
from .ask_user_tool import AskUserQuestionTool
from .todo_tool import TodoWriteTool
from .web_search_tool import WebSearchTool
from .web_fetch_tool import WebFetchTool
from .powershell_tool import PowerShellTool
from .agent_tool import AgentTool
from .task_tools import TaskCreateTool, TaskGetTool, TaskListTool, TaskStopTool, TaskUpdateTool
from .config_tool import ConfigTool
from .notebook_edit_tool import NotebookEditTool
from .lsptool import LSPTool
from .mcp_tools import ListMcpResourcesTool, ReadMcpResourceTool, MCPTool
from .plan_mode_tools import EnterPlanModeTool, ExitPlanModeTool, UpdatePlanStepTool
from .git_tools import GitStatusTool, GitDiffTool, GitLogTool, GitBranchTool
from .tool_search_tool import ToolSearchTool
from .brief_tool import BriefTool
from .cron_tools import CronCreateTool, CronDeleteTool, CronListTool, CronUpdateTool

__all__ = [
    "Tool",
    "ToolResult",
    "ToolProgressData",
    "ToolInput",
    "ToolOutput",
    "ToolUseContext",
    "build_tool",
    "tool_matches_name",
    "ToolRegistry",
    "get_tool_registry",
    "register_tool",
    "get_all_tools",
    "get_tool_by_name",
    "assemble_tool_pool",
]
