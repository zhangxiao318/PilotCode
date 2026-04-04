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

__all__ = [
    "CommandHandler",
    "CommandRegistry",
    "get_command_registry",
    "register_command",
    "get_all_commands",
    "get_command_by_name",
    "process_user_input",
]
