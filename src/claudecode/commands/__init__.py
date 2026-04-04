"""Commands module for ClaudeDecode."""

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
from . import config_cmd
from . import session_cmd
from . import cost_cmd
from . import tasks_cmd
from . import agents_cmd
from . import tools_cmd
from . import git_cmd
from . import memory_cmd
from . import theme_cmd
from . import model_cmd
from . import diff_cmd
from . import branch_cmd
from . import commit_cmd
from . import history_cmd
from . import status_cmd
from . import export_cmd
from . import cron_cmd
from . import plan_cmd
from . import env_cmd
from . import compact_cmd
from . import version_cmd
from . import find_cmd
from . import review_cmd
from . import doctor_cmd
from . import rename_cmd
from . import share_cmd
from . import skill_cmd
from . import mcp_cmd
from . import lsp_cmd
from . import debug_cmd
from . import cat_cmd
from . import ls_cmd
from . import edit_cmd
from . import mkdir_cmd
from . import rm_cmd
from . import pwd_cmd
from . import cd_cmd
from . import cp_cmd
from . import mv_cmd
from . import touch_cmd
from . import head_cmd
from . import tail_cmd
from . import wc_cmd
from . import stash_cmd
from . import tag_cmd
from . import remote_cmd
from . import merge_cmd
from . import rebase_cmd
from . import test_cmd
from . import coverage_cmd
from . import format_cmd
from . import lint_cmd
from . import symbols_cmd
from . import references_cmd
from . import blame_cmd
from . import cherrypick_cmd
from . import reset_cmd
from . import clean_cmd
from . import bisect_cmd
from . import switch_cmd
from . import revert_cmd

__all__ = [
    "CommandHandler",
    "CommandRegistry",
    "get_command_registry",
    "register_command",
    "get_all_commands",
    "get_command_by_name",
    "process_user_input",
]
