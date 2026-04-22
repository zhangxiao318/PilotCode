"""Permission management for tool execution with risk assessment."""

from enum import Enum
from dataclasses import dataclass, field
from typing import Callable, Awaitable
from datetime import datetime
import hashlib
import json

from ..services.risk_assessment import get_risk_analyzer, RiskAssessment


class PermissionLevel(Enum):
    """Permission levels for tool execution."""

    ASK = "ask"  # Always ask for permission
    ALLOW = "allow"  # Allow for this session
    ALWAYS_ALLOW = "always_allow"  # Always allow (persist)
    DENY = "deny"  # Deny for this session
    NEVER_ALLOW = "never_allow"  # Never allow (persist)


@dataclass
class ToolPermission:
    """Permission settings for a specific tool."""

    tool_name: str
    level: PermissionLevel
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "level": self.level.value,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ToolPermission":
        return cls(
            tool_name=data["tool_name"],
            level=PermissionLevel(data["level"]),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


@dataclass
class PermissionRequest:
    """A request for permission to execute a tool."""

    tool_name: str
    tool_input: dict
    description: str
    risk_level: str  # "low", "medium", "high", "critical"

    def get_fingerprint(self) -> str:
        """Generate a fingerprint for this request type."""
        # Create a hash based on tool name and input pattern
        data = f"{self.tool_name}:{json.dumps(self.tool_input, sort_keys=True)}"
        return hashlib.md5(data.encode()).hexdigest()[:16]


class PermissionManager:
    """Manages permissions for tool execution.

    Features:
    - Per-tool permission levels
    - Session-level permissions
    - Persistent permissions (saved to config)
    - Risk-based permission prompts
    """

    # Tools that are always safe (read-only or harmless writes)
    SAFE_TOOLS = {
        "FileRead",
        "Glob",
        "Grep",
        "Ripgrep",
        "CodeSearch",
        "CodeContext",
        "CodeIndex",
        "WebSearch",
        "WebFetch",
        "GitStatus",
        "GitDiff",
        "GitLog",
        "GitBranch",
        "TaskGet",
        "TaskList",
        "TaskOutput",
        "ListMcpResources",
        "ReadMcpResource",
        "CronList",
        "ListWorktrees",
        "TeamList",
        "Config",
        "ToolSearch",
        "Brief",
        "AskUser",
        "Sleep",
        "TodoWrite",
    }

    # Tools that can modify files
    WRITE_TOOLS = {"FileWrite", "FileEdit", "Bash"}

    # High risk tools
    HIGH_RISK_TOOLS = {"Bash"}

    def __init__(self):
        self._permissions: dict[str, ToolPermission] = {}
        self._session_grants: set[str] = set()  # Fingerprints granted this session
        self._session_denies: set[str] = set()  # Fingerprints denied this session
        self._permission_callback: (
            Callable[[PermissionRequest], Awaitable[PermissionLevel]] | None
        ) = None

    def set_permission_callback(
        self, callback: Callable[[PermissionRequest], Awaitable[PermissionLevel]]
    ):
        """Set callback for interactive permission requests."""
        self._permission_callback = callback

    def get_tool_risk_level(self, tool_name: str, tool_input: dict | None = None) -> str:
        """Determine risk level for a tool execution using advanced risk analysis."""
        risk_analyzer = get_risk_analyzer()
        assessment = risk_analyzer.assess_tool(tool_name, tool_input or {})
        return assessment.level.value

    def get_risk_assessment(self, tool_name: str, tool_input: dict) -> RiskAssessment:
        """Get full risk assessment for a tool execution."""
        risk_analyzer = get_risk_analyzer()
        return risk_analyzer.assess_tool(tool_name, tool_input)

    def check_permission(self, tool_name: str, tool_input: dict) -> tuple[bool, str]:
        """Check if tool execution is permitted with risk-based auto-allow.

        Returns:
            (is_permitted, reason)
        """
        # Get risk assessment
        assessment = self.get_risk_assessment(tool_name, tool_input)

        # Auto-allow read-only operations (NONE risk level)
        if assessment.auto_allow and assessment.read_only:
            return True, f"Auto-allowed: {assessment.reason}"

        # Create permission request
        request = PermissionRequest(
            tool_name=tool_name,
            tool_input=tool_input,
            description=f"Execute {tool_name}",
            risk_level=assessment.level.value,
        )
        fingerprint = request.get_fingerprint()

        # Check session grants
        if fingerprint in self._session_grants:
            return True, "Granted this session"

        # Check session denies
        if fingerprint in self._session_denies:
            return False, "Denied this session"

        # Check stored permissions
        if tool_name in self._permissions:
            perm = self._permissions[tool_name]
            if perm.level == PermissionLevel.ALWAYS_ALLOW:
                return True, "Always allowed"
            if perm.level == PermissionLevel.NEVER_ALLOW:
                return False, "Never allowed"
            if perm.level == PermissionLevel.ALLOW:
                return True, "Allowed this session"
            if perm.level == PermissionLevel.DENY:
                return False, "Denied this session"

        # Need to ask
        return False, f"Permission required: {assessment.reason}"

    async def request_permission(
        self, tool_name: str, tool_input: dict
    ) -> tuple[bool, PermissionLevel]:
        """Request permission interactively.

        Returns:
            (is_granted, permission_level_chosen)
        """
        if not self._permission_callback:
            # No callback set, deny by default for safety
            return False, PermissionLevel.DENY

        risk = self.get_tool_risk_level(tool_name, tool_input)
        request = PermissionRequest(
            tool_name=tool_name,
            tool_input=tool_input,
            description=f"Execute {tool_name}",
            risk_level=risk,
        )

        level = await self._permission_callback(request)
        fingerprint = request.get_fingerprint()

        # Apply permission
        if level in (PermissionLevel.ALLOW, PermissionLevel.ALWAYS_ALLOW):
            if level == PermissionLevel.ALLOW:
                self._session_grants.add(fingerprint)
            self._permissions[tool_name] = ToolPermission(tool_name=tool_name, level=level)
            return True, level
        else:
            if level == PermissionLevel.DENY:
                self._session_denies.add(fingerprint)
            self._permissions[tool_name] = ToolPermission(tool_name=tool_name, level=level)
            return False, level

    def grant_session_permission(self, tool_name: str, tool_input: dict | None = None):
        """Grant permission for this session only."""
        request = PermissionRequest(
            tool_name=tool_name, tool_input=tool_input or {}, description="", risk_level=""
        )
        self._session_grants.add(request.get_fingerprint())

    def revoke_session_permission(self, tool_name: str, tool_input: dict):
        """Revoke session permission."""
        request = PermissionRequest(
            tool_name=tool_name, tool_input=tool_input, description="", risk_level=""
        )
        fingerprint = request.get_fingerprint()
        self._session_grants.discard(fingerprint)

    def reset_session_permissions(self):
        """Reset all session-level permissions."""
        self._session_grants.clear()
        self._session_denies.clear()

    def save_permissions(self):
        """Save persistent permissions to config."""
        from ..utils.config import get_config_manager

        # Only save ALWAYS_ALLOW and NEVER_ALLOW
        {
            k: v.to_dict()
            for k, v in self._permissions.items()
            if v.level in (PermissionLevel.ALWAYS_ALLOW, PermissionLevel.NEVER_ALLOW)
        }

        manager = get_config_manager()
        manager.load_global_config()

        # Store in config (you might want to add a field for this)
        # For now, we'll just keep in memory

    def load_permissions(self):
        """Load persistent permissions from config."""
        # TODO: Implement loading from config
        pass


# Global instance
_permission_manager: PermissionManager | None = None


def get_permission_manager() -> PermissionManager:
    """Get global permission manager."""
    global _permission_manager
    if _permission_manager is None:
        _permission_manager = PermissionManager()
    return _permission_manager
