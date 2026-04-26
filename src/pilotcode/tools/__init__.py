"""Tools module for PilotCode."""

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
from .bash_tool import BashTool  # noqa: F401
from .file_read_tool import FileReadTool  # noqa: F401
from .file_write_tool import FileWriteTool  # noqa: F401
from .file_edit_tool import FileEditTool  # noqa: F401
from .apply_patch_tool import ApplyPatchTool  # noqa: F401
from .glob_tool import GlobTool  # noqa: F401
from .grep_tool import GrepTool  # noqa: F401
from .ripgrep_tool import RipgrepTool  # noqa: F401
from .ask_user_tool import AskUserQuestionTool  # noqa: F401
from .todo_tool import TodoWriteTool  # noqa: F401
from .web_search_tool import WebSearchTool  # noqa: F401
from .web_fetch_tool import WebFetchTool  # noqa: F401
from .powershell_tool import PowerShellTool  # noqa: F401
from .agent_tool import AgentTool  # noqa: F401
from .task_tools import (  # noqa: F401
    TaskCreateTool,
    TaskGetTool,
    TaskListTool,
    TaskStopTool,
    TaskUpdateTool,
)
from .config_tool import ConfigTool  # noqa: F401
from .notebook_edit_tool import NotebookEditTool  # noqa: F401
from .lsptool import LSPTool  # noqa: F401
from .mcp_tools import ListMcpResourcesTool, ReadMcpResourceTool, MCPTool  # noqa: F401
from .plan_mode_tools import (  # noqa: F401
    EnterPlanModeTool,
    ExitPlanModeTool,
    UpdatePlanStepTool,
)
from .git_tools import GitStatusTool, GitDiffTool, GitLogTool, GitBranchTool  # noqa: F401
from .tool_search_tool import ToolSearchTool  # noqa: F401
from .brief_tool import BriefTool  # noqa: F401
from .cron_tools import (  # noqa: F401
    CronCreateTool,
    CronDeleteTool,
    CronListTool,
    CronUpdateTool,
)
from .worktree_tools import (  # noqa: F401
    EnterWorktreeTool,
    ExitWorktreeTool,
    ListWorktreesTool,
)
from .sleep_tool import SleepTool  # noqa: F401
from .team_tools import (  # noqa: F401
    TeamCreate,
    TeamDelete,
    AgentSpawn,
    TeamList,
    TeamStatus,
    AgentCancel,
    ShareContext,
)
from .skill_tool import SkillTool  # noqa: F401
from .web_browser_tool import WebBrowserTool  # noqa: F401
from .send_message_tool import SendMessageTool, ReceiveMessageTool  # noqa: F401
from .smart_edit_planner import SmartEditPlanner  # noqa: F401
from .repl_tool import REPLTool  # noqa: F401
from .task_output_tool import TaskOutputTool  # noqa: F401
from .synthetic_output_tool import SyntheticOutputTool  # noqa: F401
from .remote_trigger_tool import RemoteTriggerTool  # noqa: F401
from .code_index_tool import CodeIndexTool  # noqa: F401
from .code_search_tool import CodeSearchTool  # noqa: F401
from .code_context_tool import CodeContextTool  # noqa: F401

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
