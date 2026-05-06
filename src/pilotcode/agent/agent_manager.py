"""Enhanced agent manager with full agent lifecycle management.

Reference: Claude Code src/tools/AgentTool/AgentTool.tsx + runAgent.ts

Supports:
- Full agent lifecycle: create → run → pause → resume → complete
- Background/Fork execution
- Teams via mailbox communication
- Persistent state to disk
- Parent/child agent tree relationships
"""

import uuid
import json
import asyncio
from enum import Enum
from pathlib import Path
from typing import Any, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from pilotcode.services import prompts as prompt_service

# =============================================================================
# Enums & Core Types
# =============================================================================


class AgentStatus(Enum):
    """Agent execution status."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentDefinition:
    """Agent definition/configuration."""

    name: str
    description: str
    system_prompt: str
    allowed_tools: list[str] = field(default_factory=list)
    model: str | None = None
    max_turns: int = 10
    color: str = "blue"
    icon: str = "🤖"

    # Advanced settings
    temperature: float = 0.7
    auto_execute_tools: bool = True
    require_confirmation: list[str] = field(default_factory=list)
    background: bool = False  # Run as background task by default
    memory_scope: str | None = None  # 'user', 'project', 'local', or None to disable
    isolation: str | None = None  # 'worktree' or None


@dataclass
class AgentMessage:
    """Message in agent conversation."""

    role: str  # system, user, assistant, tool
    content: str
    tool_calls: list[dict] | None = None
    tool_results: list[dict] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())


@dataclass
class SubAgent:
    """Sub-agent instance with full state and persistence."""

    agent_id: str
    definition: AgentDefinition
    status: AgentStatus = field(default_factory=lambda: AgentStatus.PENDING)
    messages: list[AgentMessage] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    turns: int = 0
    max_turns: int = 10
    output: str = ""
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    parent_id: str | None = None
    child_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Team support
    team_name: str | None = None
    inbox: list[dict] = field(default_factory=list)

    # Background/fork support
    is_background: bool = False
    worktree_path: str | None = None
    worktree_branch: str | None = None

    # Lifecycle: ephemeral agents are single-use PLAN-mode workers.
    # They are deleted immediately after task completion and skipped on restart.
    is_ephemeral: bool = False

    # Memory paths (transcript, state file)
    transcript_path: str | None = None
    state_path: str | None = None

    # Async task handle for background agents
    _task: asyncio.Task | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "agent_id": self.agent_id,
            "definition": asdict(self.definition),
            "status": self.status.value,
            "messages": [asdict(m) for m in self.messages],
            "tools_used": self.tools_used,
            "turns": self.turns,
            "max_turns": self.max_turns,
            "output": self.output,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "parent_id": self.parent_id,
            "child_ids": self.child_ids,
            "metadata": self.metadata,
            "team_name": self.team_name,
            "is_background": self.is_background,
            "worktree_path": self.worktree_path,
            "worktree_branch": self.worktree_branch,
            "is_ephemeral": self.is_ephemeral,
            "transcript_path": self.transcript_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SubAgent":
        """Create from dictionary."""
        definition = AgentDefinition(**data["definition"])
        agent = cls(
            agent_id=data["agent_id"],
            definition=definition,
            status=AgentStatus(data["status"]),
            messages=[AgentMessage(**m) for m in data.get("messages", [])],
            tools_used=data.get("tools_used", []),
            turns=data.get("turns", 0),
            max_turns=data.get("max_turns", 10),
            output=data.get("output", ""),
            error=data.get("error"),
            created_at=data.get("created_at", datetime.now(tz=timezone.utc).isoformat()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            parent_id=data.get("parent_id"),
            child_ids=data.get("child_ids", []),
            metadata=data.get("metadata", {}),
            team_name=data.get("team_name"),
            is_background=data.get("is_background", False),
            worktree_path=data.get("worktree_path"),
            worktree_branch=data.get("worktree_branch"),
            is_ephemeral=data.get("is_ephemeral", False),
            transcript_path=data.get("transcript_path"),
        )
        return agent


@dataclass
class AgentWorkflow:
    """Multi-agent workflow definition."""

    workflow_id: str
    name: str
    description: str
    agent_ids: list[str] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    status: AgentStatus = field(default_factory=lambda: AgentStatus.PENDING)
    team_name: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "agent_ids": self.agent_ids,
            "steps": self.steps,
            "status": self.status.value,
            "team_name": self.team_name,
            "created_at": self.created_at,
        }


# =============================================================================
# Agent Definitions Registry
# =============================================================================


ENHANCED_AGENT_DEFINITIONS = {
    "coder": AgentDefinition(
        name="coder",
        description="Specialized in writing and editing code",
        system_prompt=prompt_service.get_coder_prompt(),
        allowed_tools=["Bash", "FileRead", "FileWrite", "FileEdit", "Glob", "Grep", "TodoWrite"],
        color="blue",
        icon="💻",
        memory_scope="project",
    ),
    "debugger": AgentDefinition(
        name="debugger",
        description="Specialized in debugging and finding issues",
        system_prompt=prompt_service.get_debugger_prompt(),
        allowed_tools=["Bash", "FileRead", "Grep", "Glob", "TodoWrite"],
        color="red",
        icon="🐛",
        memory_scope="project",
    ),
    "explainer": AgentDefinition(
        name="explainer",
        description="Specialized in explaining code and concepts",
        system_prompt=prompt_service.get_explainer_prompt(),
        allowed_tools=["FileRead", "Grep", "WebSearch"],
        color="green",
        icon="📚",
    ),
    "tester": AgentDefinition(
        name="tester",
        description="Specialized in writing tests",
        system_prompt=prompt_service.get_tester_prompt(),
        allowed_tools=["Bash", "FileRead", "FileWrite", "FileEdit", "TodoWrite"],
        color="yellow",
        icon="🧪",
        memory_scope="project",
    ),
    "reviewer": AgentDefinition(
        name="reviewer",
        description="Specialized in code review",
        system_prompt=prompt_service.get_reviewer_prompt(),
        allowed_tools=["FileRead", "Grep", "Glob"],
        color="purple",
        icon="👁️",
    ),
    "planner": AgentDefinition(
        name="planner",
        description="Software architect for designing implementation plans. Read-only.",
        system_prompt=prompt_service.get_planner_prompt(),
        allowed_tools=["FileRead", "Grep", "Glob", "CodeSearch", "Bash", "Git"],
        color="cyan",
        icon="📋",
        max_turns=15,
    ),
    "explorer": AgentDefinition(
        name="explorer",
        description="Fast codebase exploration agent. Read-only.",
        system_prompt=prompt_service.get_explorer_prompt(),
        allowed_tools=["FileRead", "Grep", "Glob", "CodeSearch", "Bash", "Git"],
        color="magenta",
        icon="🔍",
        max_turns=12,
    ),
    "verifier": AgentDefinition(
        name="verifier",
        description="Verification specialist. Read-only adversarial testing.",
        system_prompt=prompt_service.get_verifier_agent_prompt(),
        allowed_tools=["FileRead", "Grep", "Bash", "Git"],
        color="red",
        icon="✅",
        max_turns=20,
        memory_scope="project",
    ),
}


# =============================================================================
# AgentManager - Full lifecycle management
# =============================================================================


class AgentManager:
    """Manager for sub-agents with persistence, teams, and background execution.

    Reference: Claude Code AgentTool.tsx + runAgent.ts + resumeAgent.ts
    """

    def __init__(self, storage_dir: str | None = None):
        self.agents: dict[str, SubAgent] = {}
        self.workflows: dict[str, AgentWorkflow] = {}
        self.teams: dict[str, list[str]] = {}  # team_name -> [agent_id]
        self._callbacks: list[Callable[[str, SubAgent], None]] = []

        # Set up storage
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            from pilotcode.utils.paths import get_agents_dir

            self.storage_dir = get_agents_dir()

        self.transcripts_dir = self.storage_dir / "transcripts"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)

        # Load persisted agents
        self._load_all()

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    def _agent_path(self, agent_id: str) -> Path:
        return self.storage_dir / f"{agent_id}.json"

    def _transcript_path(self, agent_id: str) -> Path:
        return self.transcripts_dir / f"{agent_id}.jsonl"

    def _workflow_path(self, workflow_id: str) -> Path:
        return self.storage_dir / f"workflow_{workflow_id}.json"

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_agent(self, agent: SubAgent):
        """Save agent state to disk."""
        path = self._agent_path(agent.agent_id)
        with open(path, "w") as f:
            json.dump(agent.to_dict(), f, indent=2, default=str)

        # Persist transcript for resumability
        if hasattr(agent, "_task") and agent._task and not agent._task.done():
            self._save_transcript(agent)

    def _save_transcript(self, agent: SubAgent):
        """Save agent conversation transcript for resumability."""
        if not agent.messages:
            return
        path = self._transcript_path(agent.agent_id)
        with open(path, "a") as f:
            for msg in agent.messages[-5:]:  # Save recent messages
                f.write(json.dumps(asdict(msg), default=str) + "\n")

    def _load_all(self):
        """Load persisted agents with lifecycle-aware cleanup.

        Rules:
        - Ephemeral (PLAN-mode worker) agents: auto-delete if completed/failed,
          regardless of age. They are single-use and should never survive restart.
        - Persistent (user-created / background) agents: keep for 30 days,
          then delete if completed/failed.
        """
        # Always start from clean memory state so restarts don't accumulate
        self.agents.clear()
        self.workflows.clear()
        self.teams.clear()

        if not self.storage_dir.exists():
            return

        from datetime import datetime, timezone, timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        for path in self.storage_dir.glob("*.json"):
            if path.name.startswith("workflow_"):
                continue
            try:
                data = json.loads(path.read_text())
                agent = SubAgent.from_dict(data)
                status = getattr(agent, "status", None)
                is_ephemeral = getattr(agent, "is_ephemeral", None)

                # Rule 1: ephemeral / legacy single-use workers.
                # Legacy agents (pre-is_ephemeral) default to cleanup.
                if is_ephemeral is not False:
                    # Completed/failed/cancelled → delete immediately
                    if status in (
                        AgentStatus.COMPLETED,
                        AgentStatus.FAILED,
                        AgentStatus.CANCELLED,
                    ):
                        path.unlink(missing_ok=True)
                        continue
                    # Pending but file untouched for >1h → dead worker from crash
                    if status == AgentStatus.PENDING:
                        try:
                            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                            if mtime < datetime.now(timezone.utc) - timedelta(hours=1):
                                path.unlink(missing_ok=True)
                                continue
                        except Exception:
                            pass

                # Rule 2: persistent agents get a 30-day grace period.
                if status in (AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.CANCELLED):
                    try:
                        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                        if mtime < cutoff:
                            path.unlink(missing_ok=True)
                            continue
                    except Exception:
                        pass

                self.agents[agent.agent_id] = agent
            except Exception:
                pass

    def _load_transcript(self, agent_id: str) -> list[AgentMessage]:
        """Load agent transcript from disk."""
        path = self._transcript_path(agent_id)
        if not path.exists():
            return []

        messages = []
        try:
            for line in path.read_text().strip().split("\n"):
                if line:
                    data = json.loads(line)
                    messages.append(AgentMessage(**data))
        except Exception:
            pass
        return messages

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def register_callback(self, callback: Callable[[str, SubAgent], None]):
        """Register status change callback."""
        self._callbacks.append(callback)

    def _notify(self, event: str, agent: SubAgent):
        """Notify callbacks."""
        for callback in self._callbacks:
            try:
                callback(event, agent)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Agent CRUD
    # ------------------------------------------------------------------

    def create_agent(
        self,
        agent_type: str | None = None,
        name: str | None = None,
        parent_id: str | None = None,
        is_background: bool = False,
        team_name: str | None = None,
        is_ephemeral: bool = False,
    ) -> SubAgent:
        """Create a new sub-agent.

        Args:
            agent_type: Type from ENHANCED_AGENT_DEFINITIONS
            name: Custom name override
            parent_id: Parent agent ID for tree tracking
            is_background: Whether this agent runs in background
            team_name: Team name for group execution
            is_ephemeral: If True, agent is a single-use worker and will be
                auto-deleted after completion. PLAN-mode agents set this.

        Returns:
            Created SubAgent
        """
        agent_id = str(uuid.uuid4())[:8]

        if agent_type and agent_type in ENHANCED_AGENT_DEFINITIONS:
            definition = AgentDefinition(**asdict(ENHANCED_AGENT_DEFINITIONS[agent_type]))
        else:
            definition = AgentDefinition(**asdict(ENHANCED_AGENT_DEFINITIONS["coder"]))

        # Override name if provided
        if name:
            definition.name = name

        agent = SubAgent(
            agent_id=agent_id,
            definition=definition,
            max_turns=definition.max_turns,
            parent_id=parent_id,
            is_background=is_background or definition.background,
            is_ephemeral=is_ephemeral,
            team_name=team_name,
            state_path=str(self._agent_path(agent_id)),
            transcript_path=str(self._transcript_path(agent_id)),
        )

        self.agents[agent_id] = agent
        self._save_agent(agent)

        # Register with parent
        if parent_id and parent_id in self.agents:
            self.agents[parent_id].child_ids.append(agent_id)
            self._save_agent(self.agents[parent_id])

        # Register with team
        if team_name:
            if team_name not in self.teams:
                self.teams[team_name] = []
            self.teams[team_name].append(agent_id)

        self._notify("created", agent)
        return agent

    def get_agent(self, agent_id: str) -> SubAgent | None:
        """Get agent by ID."""
        return self.agents.get(agent_id)

    def list_agents(
        self,
        status: AgentStatus | None = None,
        agent_type: str | None = None,
        team_name: str | None = None,
        background_only: bool = False,
    ) -> list[SubAgent]:
        """List agents with optional filtering.

        Args:
            status: Filter by status
            agent_type: Filter by agent type name
            team_name: Filter by team
            background_only: Only background agents
        """
        agents = list(self.agents.values())

        if status:
            agents = [a for a in agents if a.status == status]

        if agent_type:
            agents = [a for a in agents if a.definition.name == agent_type]

        if team_name:
            team_ids = set(self.teams.get(team_name, []))
            agents = [a for a in agents if a.agent_id in team_ids]

        if background_only:
            agents = [a for a in agents if a.is_background]

        return agents

    def update_agent(self, agent: SubAgent):
        """Update agent state and persist."""
        self.agents[agent.agent_id] = agent
        self._save_agent(agent)
        self._notify("updated", agent)

    def set_agent_status(self, agent_id: str, status: AgentStatus):
        """Set agent status."""
        if agent_id in self.agents:
            agent = self.agents[agent_id]
            agent.status = status

            if status == AgentStatus.RUNNING and not agent.started_at:
                agent.started_at = datetime.now(tz=timezone.utc).isoformat()

            if status in (AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.CANCELLED):
                agent.completed_at = datetime.now(tz=timezone.utc).isoformat()

            self._save_agent(agent)
            self._notify(f"status:{status.value}", agent)

    def delete_agent(self, agent_id: str, cleanup_worktree: bool = True) -> bool:
        """Delete an agent and optionally clean up its worktree.

        Args:
            agent_id: Agent ID to delete
            cleanup_worktree: Whether to remove associated worktree

        Returns:
            True if deleted
        """
        if agent_id not in self.agents:
            return False

        agent = self.agents.pop(agent_id)

        # Cancel background task if running
        if agent._task and not agent._task.done():
            agent._task.cancel()

        # Clean up worktree
        if cleanup_worktree and agent.worktree_path:
            from .agent_worktree import remove_agent_worktree

            slug = Path(agent.worktree_path).name
            remove_agent_worktree(slug)

        # Delete storage
        path = self._agent_path(agent_id)
        if path.exists():
            path.unlink()

        # Delete transcript
        transcript_path = self._transcript_path(agent_id)
        if transcript_path.exists():
            transcript_path.unlink()

        # Remove from parent's children
        if agent.parent_id and agent.parent_id in self.agents:
            parent = self.agents[agent.parent_id]
            if agent_id in parent.child_ids:
                parent.child_ids.remove(agent_id)
                self._save_agent(parent)

        # Remove from team
        if agent.team_name and agent.team_name in self.teams:
            if agent_id in self.teams[agent.team_name]:
                self.teams[agent.team_name].remove(agent_id)

        self._notify("deleted", agent)
        return True

    # ------------------------------------------------------------------
    # Background / Fork execution
    # ------------------------------------------------------------------

    def run_agent_background(
        self,
        agent_id: str,
        coro: Callable[[], Any],
    ) -> asyncio.Task | None:
        """Run an agent in the background.

        Args:
            agent_id: Agent ID
            coro: Async callable that executes the agent

        Returns:
            asyncio.Task handle
        """
        agent = self.agents.get(agent_id)
        if not agent:
            return None

        agent.status = AgentStatus.RUNNING
        agent.started_at = datetime.now(tz=timezone.utc).isoformat()
        agent.is_background = True
        self._save_agent(agent)

        async def _run_wrapper():
            try:
                agent._task = asyncio.current_task()
                result = await coro()
                agent.output = str(result) if result else ""
                agent.status = AgentStatus.COMPLETED
            except asyncio.CancelledError:
                agent.status = AgentStatus.CANCELLED
            except Exception as e:
                agent.error = str(e)
                agent.status = AgentStatus.FAILED
            finally:
                agent.completed_at = datetime.now(tz=timezone.utc).isoformat()
                self._save_agent(agent)
                self._notify("completed", agent)

        task = asyncio.create_task(_run_wrapper())
        agent._task = task
        return task

    def fork_agent(
        self,
        parent_id: str,
        directive: str,
        agent_type: str | None = None,
        isolation: str | None = None,
    ) -> SubAgent | None:
        """Fork a child agent from a parent.

        The child inherits parent context and runs independently.

        Args:
            parent_id: Parent agent ID
            directive: Task directive for the fork
            agent_type: Type override (defaults to parent type)
            isolation: Worktree isolation mode

        Returns:
            Forked SubAgent, or None
        """
        parent = self.agents.get(parent_id)
        if not parent:
            return None

        child = self.create_agent(
            agent_type=agent_type or parent.definition.name,
            parent_id=parent_id,
            is_background=True,
        )

        # Inherit parent context
        inherit_fields = ["cwd", "team_name"]
        for fld in inherit_fields:
            if fld in parent.metadata:
                child.metadata[fld] = parent.metadata[fld]

        child.metadata["fork_directive"] = directive
        child.metadata["parent_type"] = parent.definition.name

        # Worktree isolation
        if isolation == "worktree":
            from .agent_worktree import create_agent_worktree

            slug = f"fork-{child.agent_id}"
            worktree = create_agent_worktree(slug)
            if worktree:
                child.worktree_path = worktree["worktree_path"]
                child.worktree_branch = worktree["branch"]

        self._save_agent(child)
        return child

    # ------------------------------------------------------------------
    # Teams
    # ------------------------------------------------------------------

    def create_team(self, team_name: str, agent_ids: list[str]) -> bool:
        """Create an agent team.

        Args:
            team_name: Team name
            agent_ids: Agent IDs to include

        Returns:
            True if created
        """
        if team_name in self.teams:
            return False

        self.teams[team_name] = list(agent_ids)
        for aid in agent_ids:
            if aid in self.agents:
                self.agents[aid].team_name = team_name
                self._save_agent(self.agents[aid])

        # Create team file
        teams_dir = self.storage_dir / "teams"
        teams_dir.mkdir(parents=True, exist_ok=True)

        team_file = teams_dir / f"{team_name}.json"
        team_data = {
            "name": team_name,
            "agent_ids": agent_ids,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        team_file.write_text(json.dumps(team_data, indent=2))
        return True

    def get_team(self, team_name: str) -> list[SubAgent] | None:
        """Get all agents in a team."""
        agent_ids = self.teams.get(team_name)
        if not agent_ids:
            return None
        return [self.agents[aid] for aid in agent_ids if aid in self.agents]

    def delete_team(self, team_name: str) -> bool:
        """Delete a team."""
        if team_name not in self.teams:
            return False

        for aid in self.teams[team_name]:
            if aid in self.agents:
                self.agents[aid].team_name = None
                self._save_agent(self.agents[aid])

        del self.teams[team_name]

        team_file = self.storage_dir / "teams" / f"{team_name}.json"
        if team_file.exists():
            team_file.unlink()
        return True

    # ------------------------------------------------------------------
    # Workflows
    # ------------------------------------------------------------------

    def create_workflow(
        self, name: str, description: str, team_name: str | None = None
    ) -> AgentWorkflow:
        """Create a new workflow."""
        workflow_id = str(uuid.uuid4())[:8]

        workflow = AgentWorkflow(
            workflow_id=workflow_id,
            name=name,
            description=description,
            team_name=team_name,
        )

        self.workflows[workflow_id] = workflow
        self._save_workflow(workflow)
        return workflow

    def _save_workflow(self, workflow: AgentWorkflow):
        """Save workflow to disk."""
        path = self._workflow_path(workflow.workflow_id)
        with open(path, "w") as f:
            json.dump(workflow.to_dict(), f, indent=2)

    def get_workflow(self, workflow_id: str) -> AgentWorkflow | None:
        """Get workflow by ID."""
        return self.workflows.get(workflow_id)

    def add_agent_to_workflow(self, workflow_id: str, agent_id: str):
        """Add agent to workflow."""
        if workflow_id not in self.workflows:
            return False

        workflow = self.workflows[workflow_id]
        if agent_id not in workflow.agent_ids:
            workflow.agent_ids.append(agent_id)
            self._save_workflow(workflow)
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_agent_tree(self, agent_id: str) -> dict:
        """Get agent tree structure (parent → children hierarchy)."""
        agent = self.agents.get(agent_id)
        if not agent:
            return {}

        return {
            "agent": agent.to_dict(),
            "children": [self.get_agent_tree(cid) for cid in agent.child_ids],
        }

    def get_active_agents(self) -> list[SubAgent]:
        """Get all currently running agents."""
        return [a for a in self.agents.values() if a.status == AgentStatus.RUNNING]

    def get_background_agents(self) -> list[SubAgent]:
        """Get all background agents (running or pending)."""
        return [a for a in self.agents.values() if a.is_background]


# =============================================================================
# Global instance
# =============================================================================

_agent_manager: AgentManager | None = None


def get_agent_manager() -> AgentManager:
    """Get global agent manager."""
    global _agent_manager
    if _agent_manager is None:
        _agent_manager = AgentManager()
    return _agent_manager
