"""Agent system for sub-agent orchestration.

Supports:
- Agent lifecycle management with persistence
- Multi-agent workflows (sequential, parallel, map-reduce, supervisor)
- Background/fork execution
- Agent teams and communication via mailbox protocol
- Worktree isolation for safe concurrent execution
- Agent memory persistence (user/project/local scope)
"""

from .agent_manager import (
    AgentManager,
    get_agent_manager,
    SubAgent,
    AgentDefinition,
    AgentStatus,
    AgentMessage,
    AgentWorkflow,
    ENHANCED_AGENT_DEFINITIONS,
)
from .agent_orchestrator import (
    AgentOrchestrator,
    WorkflowStep,
    WorkflowType,
    get_orchestrator,
)
from .agent_hooks import AgentHooks, HookManager, get_hook_manager
from .agent_memory import (
    get_agent_memory_dir,
    load_agent_memory_prompt,
    save_agent_memory,
    clear_agent_memory,
    has_agent_memory,
    is_agent_memory_path,
    check_agent_memory_snapshot,
    initialize_from_snapshot,
)
from .agent_mailbox import (
    write_to_mailbox,
    read_unread_messages,
    broadcast_to_team,
    get_team_info,
    create_team,
    delete_team,
)
from .agent_worktree import (
    create_agent_worktree,
    remove_agent_worktree,
    has_worktree_changes,
    cleanup_stale_agent_worktrees,
    is_git_repo,
    build_worktree_notice,
)

__all__ = [
    # Agent Manager
    "AgentManager",
    "get_agent_manager",
    "SubAgent",
    "AgentDefinition",
    "AgentStatus",
    "AgentMessage",
    "AgentWorkflow",
    "ENHANCED_AGENT_DEFINITIONS",
    # Orchestrator
    "AgentOrchestrator",
    "WorkflowStep",
    "WorkflowType",
    "get_orchestrator",
    # Hooks
    "AgentHooks",
    "HookManager",
    "get_hook_manager",
    # Memory
    "get_agent_memory_dir",
    "load_agent_memory_prompt",
    "save_agent_memory",
    "clear_agent_memory",
    "has_agent_memory",
    "is_agent_memory_path",
    "check_agent_memory_snapshot",
    "initialize_from_snapshot",
    # Mailbox
    "write_to_mailbox",
    "read_unread_messages",
    "broadcast_to_team",
    "get_team_info",
    "create_team",
    "delete_team",
    # Worktree
    "create_agent_worktree",
    "remove_agent_worktree",
    "has_worktree_changes",
    "cleanup_stale_agent_worktrees",
    "is_git_repo",
    "build_worktree_notice",
]
