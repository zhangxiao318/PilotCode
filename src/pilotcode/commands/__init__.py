"""Commands module for PilotCode."""

from .base import (
    CommandHandler,
    CommandRegistry,
    get_command_registry,
    register_command,
    get_all_commands,
    get_command_by_name,
    process_user_input,
)

# Import all commands to register them
from . import config_cmd  # noqa: F401
from . import alias_cmd  # noqa: F401
from . import init_cmd  # noqa: F401
from . import session_cmd  # noqa: F401
from . import cost_cmd  # noqa: F401
from . import tasks_cmd  # noqa: F401
from . import agents_cmd  # noqa: F401
from . import tools_cmd  # noqa: F401
from . import git_cmd  # noqa: F401
from . import git_commands  # noqa: F401
from . import memory_cmd  # noqa: F401
from . import theme_cmd  # noqa: F401
from . import model_cmd  # noqa: F401
from . import status_cmd  # noqa: F401
from . import export_cmd  # noqa: F401
from . import cron_cmd  # noqa: F401
from . import plan_cmd  # noqa: F401
from . import env_cmd  # noqa: F401
from . import compact_cmd  # noqa: F401
from . import version_cmd  # noqa: F401
from . import find_cmd  # noqa: F401
from . import review_cmd  # noqa: F401
from . import doctor_cmd  # noqa: F401
from . import rename_cmd  # noqa: F401
from . import share_cmd  # noqa: F401
from . import skill_cmd  # noqa: F401
from . import mcp_cmd  # noqa: F401
from . import lsp_cmd  # noqa: F401
from . import debug_cmd  # noqa: F401
from . import ls_cmd  # noqa: F401
from . import edit_cmd  # noqa: F401
from . import test_cmd  # noqa: F401
from . import coverage_cmd  # noqa: F401
from . import format_cmd  # noqa: F401
from . import lint_cmd  # noqa: F401
from . import symbols_cmd  # noqa: F401
from . import references_cmd  # noqa: F401
from . import workflow_cmd  # noqa: F401
from . import quest_cmd  # noqa: F401
from . import code_index_cmd  # noqa: F401
from . import code_search_cmd  # noqa: F401

__all__ = [
    "CommandHandler",
    "CommandRegistry",
    "get_command_registry",
    "register_command",
    "get_all_commands",
    "get_command_by_name",
    "process_user_input",
]
