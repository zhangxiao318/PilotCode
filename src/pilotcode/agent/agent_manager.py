"""Enhanced agent manager with full agent lifecycle management."""

import uuid
import json
from enum import Enum
from typing import Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path


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


@dataclass
class AgentMessage:
    """Message in agent conversation."""

    role: str  # system, user, assistant, tool
    content: str
    tool_calls: list[dict] | None = None
    tool_results: list[dict] | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class SubAgent:
    """Sub-agent instance with full state."""

    agent_id: str
    definition: AgentDefinition
    status: AgentStatus = field(default_factory=lambda: AgentStatus.PENDING)
    messages: list[AgentMessage] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    turns: int = 0
    max_turns: int = 10
    output: str = ""
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    parent_id: str | None = None
    child_ids: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
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
            created_at=data.get("created_at", datetime.now().isoformat()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            parent_id=data.get("parent_id"),
            child_ids=data.get("child_ids", []),
            metadata=data.get("metadata", {}),
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
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "agent_ids": self.agent_ids,
            "steps": self.steps,
            "status": self.status.value,
            "created_at": self.created_at,
        }


# Enhanced agent definitions
ENHANCED_AGENT_DEFINITIONS = {
    "coder": AgentDefinition(
        name="coder",
        description="Specialized in writing and editing code",
        system_prompt="""You are an expert coding assistant. Your focus is:
- Writing clean, efficient, well-documented code
- Following best practices and design patterns
- Writing tests alongside implementation
- Using tools to read, write, and edit files

Always explain your approach before making changes.
Use <complete> when finished with the task.""",
        allowed_tools=["Bash", "FileRead", "FileWrite", "FileEdit", "Glob", "Grep", "TodoWrite"],
        color="blue",
        icon="💻",
    ),
    "debugger": AgentDefinition(
        name="debugger",
        description="Specialized in debugging and finding issues",
        system_prompt="""You are an expert debugging assistant. Your focus is:
- Analyzing error messages and stack traces
- Finding root causes of bugs
- Suggesting minimal fixes
- Verifying fixes work

Always trace through the code to understand the issue.
Use <complete> when the bug is identified and fixed.""",
        allowed_tools=["Bash", "FileRead", "Grep", "Glob", "TodoWrite"],
        color="red",
        icon="🐛",
    ),
    "explainer": AgentDefinition(
        name="explainer",
        description="Specialized in explaining code and concepts",
        system_prompt="""You are an expert explainer. Your focus is:
- Making complex code understandable
- Explaining architectural decisions
- Documenting code behavior
- Providing usage examples

Use clear language and relevant examples.
Use <complete> when the explanation is thorough.""",
        allowed_tools=["FileRead", "Grep", "WebSearch"],
        color="green",
        icon="📚",
    ),
    "tester": AgentDefinition(
        name="tester",
        description="Specialized in writing tests",
        system_prompt="""You are an expert testing assistant. Your focus is:
- Writing comprehensive unit tests
- Creating integration tests
- Ensuring edge cases are covered
- Maintaining test quality

Always verify tests can run and pass.
Use <complete> when test coverage is adequate.""",
        allowed_tools=["Bash", "FileRead", "FileWrite", "FileEdit", "TodoWrite"],
        color="yellow",
        icon="🧪",
    ),
    "reviewer": AgentDefinition(
        name="reviewer",
        description="Specialized in code review",
        system_prompt="""You are an expert code reviewer. Your focus is:
- Identifying potential bugs and issues
- Checking code style and conventions
- Suggesting improvements
- Verifying best practices

Be constructive and specific in your feedback.
Use <complete> when the review is complete.""",
        allowed_tools=["FileRead", "Grep", "Glob"],
        color="purple",
        icon="👁️",
    ),
    "planner": AgentDefinition(
        name="planner",
        description="Software architect for designing implementation plans. Read-only.",
        system_prompt="""You are a software architect and planning specialist.

=== CRITICAL: READ-ONLY MODE — NO FILE MODIFICATIONS ===
You are STRICTLY PROHIBITED from:
- Creating new files
- Modifying existing files
- Deleting files
- Moving or copying files
- Running commands that change system state (npm install, pip install, git commit, etc.)

Your role is EXCLUSIVELY to explore the codebase and design implementation plans.
You do NOT have access to file editing tools.

## Your Process
1. **Explore Thoroughly**: Use FileRead, Grep, Glob, CodeSearch to understand the code.
2. **Design Solution**: Create an implementation approach based on findings.
3. **Detail the Plan**: Identify critical files, trace call sites, anticipate risks.

## Output Format
End with a structured plan containing:
- Root cause analysis
- Files to modify (with exact paths)
- Affected call sites
- Verification steps

Use <complete> when the plan is ready for execution.""",
        allowed_tools=["FileRead", "Grep", "Glob", "CodeSearch", "Bash", "GitDiff", "GitLog", "GitStatus"],
        color="cyan",
        icon="📋",
        max_turns=15,
    ),
    "explorer": AgentDefinition(
        name="explorer",
        description="Fast codebase exploration agent. Read-only.",
        system_prompt="""You are a file search specialist.

=== CRITICAL: READ-ONLY MODE — NO FILE MODIFICATIONS ===
You are STRICTLY PROHIBITED from creating, modifying, or deleting any files.
Your role is EXCLUSIVELY to search and analyze existing code.

Guidelines:
- Use Glob for broad file pattern matching
- Use Grep for searching file contents with regex
- Use FileRead when you know the specific file path
- Use Bash ONLY for read-only operations (ls, git status, git log, git diff, find, cat, head, tail)
- NEVER use Bash for: mkdir, touch, rm, cp, mv, git add, git commit, npm install, pip install
- Be efficient: spawn multiple parallel tool calls where possible

Use <complete> when you have found the relevant information.""",
        allowed_tools=["FileRead", "Grep", "Glob", "CodeSearch", "Bash", "GitDiff", "GitLog"],
        color="magenta",
        icon="🔍",
        max_turns=12,
    ),
    "verifier": AgentDefinition(
        name="verifier",
        description="Verification specialist. Read-only adversarial testing.",
        system_prompt="""You are a verification specialist. Your job is not to confirm the implementation works — it's to try to break it.

=== CRITICAL: READ-ONLY MODE — NO FILE MODIFICATIONS ===
You are STRICTLY PROHIBITED from modifying any files in the project directory.

## Verification Strategy
Adapt based on what was changed:
- **Bug fixes**: Reproduce the original bug → verify fix → run regression tests
- **Code changes**: Run build → run test suite → check for regressions
- **Refactoring**: Existing tests MUST pass unchanged → verify observable behavior is identical

## Required Steps
1. Read the project README/CLAUDE.md for build/test commands
2. Run the build (if applicable). A broken build is an automatic FAIL.
3. Run the project's test suite. Failing tests are an automatic FAIL.
4. Run linters/type-checkers if configured.
5. Check for regressions in related code.

## Adversarial Probes
Try to break the implementation:
- Boundary values: 0, -1, empty string, very long strings, unicode
- Edge cases the implementer may have missed

## Output Format
For each check, report:
```
### Check: [what you're verifying]
Command run: [exact command]
Output observed: [actual output]
Result: PASS / FAIL
```

End with exactly:
VERDICT: PASS
or VERDICT: FAIL
or VERDICT: PARTIAL

Use <complete> when verification is done.""",
        allowed_tools=["FileRead", "Grep", "Bash", "GitDiff", "GitStatus"],
        color="red",
        icon="✅",
        max_turns=20,
    ),
}


class AgentManager:
    """Enhanced manager for sub-agents with persistence."""

    def __init__(self, storage_dir: str | None = None):
        self.agents: dict[str, SubAgent] = {}
        self.workflows: dict[str, AgentWorkflow] = {}
        self._callbacks: list[Callable[[str, SubAgent], None]] = []

        # Set up storage
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            from platformdirs import user_data_dir

            app_dir = Path(user_data_dir("pilotcode"))
            self.storage_dir = app_dir / "agents"

        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Load persisted agents
        self._load_all()

    def _agent_path(self, agent_id: str) -> Path:
        """Get storage path for agent."""
        return self.storage_dir / f"{agent_id}.json"

    def _workflow_path(self, workflow_id: str) -> Path:
        """Get storage path for workflow."""
        return self.storage_dir / f"workflow_{workflow_id}.json"

    def _save_agent(self, agent: SubAgent):
        """Save agent to disk."""
        path = self._agent_path(agent.agent_id)
        with open(path, "w") as f:
            json.dump(agent.to_dict(), f, indent=2)

    def _load_all(self):
        """Load all persisted agents."""
        if not self.storage_dir.exists():
            return

        for path in self.storage_dir.glob("*.json"):
            if path.name.startswith("workflow_"):
                continue
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                agent = SubAgent.from_dict(data)
                self.agents[agent.agent_id] = agent
            except Exception:
                pass

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

    def create_agent(
        self,
        agent_type: str | None = None,
        name: str | None = None,
        parent_id: str | None = None,
    ) -> SubAgent:
        """Create a new sub-agent."""
        agent_id = str(uuid.uuid4())[:8]

        if agent_type and agent_type in ENHANCED_AGENT_DEFINITIONS:
            definition = ENHANCED_AGENT_DEFINITIONS[agent_type]
        else:
            definition = ENHANCED_AGENT_DEFINITIONS["coder"]

        # Override name if provided
        if name:
            definition = AgentDefinition(
                name=name,
                description=definition.description,
                system_prompt=definition.system_prompt,
                allowed_tools=definition.allowed_tools,
                color=definition.color,
                icon=definition.icon,
            )

        agent = SubAgent(
            agent_id=agent_id,
            definition=definition,
            max_turns=definition.max_turns,
            parent_id=parent_id,
        )

        self.agents[agent_id] = agent
        self._save_agent(agent)

        # Register with parent
        if parent_id and parent_id in self.agents:
            self.agents[parent_id].child_ids.append(agent_id)
            self._save_agent(self.agents[parent_id])

        self._notify("created", agent)
        return agent

    def get_agent(self, agent_id: str) -> SubAgent | None:
        """Get agent by ID."""
        return self.agents.get(agent_id)

    def list_agents(
        self,
        status: AgentStatus | None = None,
        agent_type: str | None = None,
    ) -> list[SubAgent]:
        """List agents with optional filtering."""
        agents = list(self.agents.values())

        if status:
            agents = [a for a in agents if a.status == status]

        if agent_type:
            agents = [a for a in agents if a.definition.name == agent_type]

        return agents

    def update_agent(self, agent: SubAgent):
        """Update agent state."""
        self.agents[agent.agent_id] = agent
        self._save_agent(agent)
        self._notify("updated", agent)

    def set_agent_status(self, agent_id: str, status: AgentStatus):
        """Set agent status."""
        if agent_id in self.agents:
            agent = self.agents[agent_id]
            agent.status = status

            if status == AgentStatus.RUNNING and not agent.started_at:
                agent.started_at = datetime.now().isoformat()

            if status in (AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.CANCELLED):
                agent.completed_at = datetime.now().isoformat()

            self._save_agent(agent)
            self._notify(f"status:{status.value}", agent)

    def delete_agent(self, agent_id: str) -> bool:
        """Delete an agent."""
        if agent_id not in self.agents:
            return False

        agent = self.agents.pop(agent_id)

        # Delete storage
        path = self._agent_path(agent_id)
        if path.exists():
            path.unlink()

        # Remove from parent's children
        if agent.parent_id and agent.parent_id in self.agents:
            parent = self.agents[agent.parent_id]
            if agent_id in parent.child_ids:
                parent.child_ids.remove(agent_id)
                self._save_agent(parent)

        self._notify("deleted", agent)
        return True

    def create_workflow(self, name: str, description: str) -> AgentWorkflow:
        """Create a new workflow."""
        workflow_id = str(uuid.uuid4())[:8]

        workflow = AgentWorkflow(
            workflow_id=workflow_id,
            name=name,
            description=description,
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

    def get_agent_tree(self, agent_id: str) -> dict:
        """Get agent tree structure."""
        agent = self.agents.get(agent_id)
        if not agent:
            return {}

        return {
            "agent": agent.to_dict(),
            "children": [self.get_agent_tree(cid) for cid in agent.child_ids],
        }


# Global agent manager
_agent_manager: AgentManager | None = None


def get_agent_manager() -> AgentManager:
    """Get global agent manager."""
    global _agent_manager
    if _agent_manager is None:
        _agent_manager = AgentManager()
    return _agent_manager
