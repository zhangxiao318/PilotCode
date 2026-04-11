"""Plugin policy management for enterprises.

Allows organizations to define and enforce policies for plugin usage.
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class PolicyAction(Enum):
    """Policy enforcement actions."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    NOTIFY = "notify"


class PolicyScope(Enum):
    """Scope of policy application."""

    GLOBAL = "global"
    MARKETPLACE = "marketplace"
    PLUGIN = "plugin"
    PUBLISHER = "publisher"


@dataclass
class PolicyRule:
    """A single policy rule."""

    name: str
    description: str
    scope: PolicyScope
    pattern: str  # Glob pattern for matching
    action: PolicyAction
    message: Optional[str] = None

    def matches(self, value: str) -> bool:
        """Check if value matches this rule."""
        return fnmatch.fnmatch(value, self.pattern)


@dataclass
class PluginPolicy:
    """Complete plugin policy configuration."""

    name: str
    version: str = "1.0"
    description: str = ""

    # Rules
    rules: list[PolicyRule] = field(default_factory=list)

    # Allowlists/Blocklists
    allowed_marketplaces: list[str] = field(default_factory=list)
    blocked_marketplaces: list[str] = field(default_factory=list)
    allowed_publishers: list[str] = field(default_factory=list)
    blocked_publishers: list[str] = field(default_factory=list)
    allowed_plugins: list[str] = field(default_factory=list)
    blocked_plugins: list[str] = field(default_factory=list)

    # Requirements
    require_signatures: bool = False
    require_trusted_publishers: bool = False
    require_approval_for_install: bool = False

    # Auto-update policy
    auto_update_allowed: bool = True
    auto_update_sources: list[str] = field(default_factory=list)

    # Audit
    audit_all_installs: bool = True
    audit_all_operations: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "rules": [
                {
                    "name": r.name,
                    "description": r.description,
                    "scope": r.scope.value,
                    "pattern": r.pattern,
                    "action": r.action.value,
                    "message": r.message,
                }
                for r in self.rules
            ],
            "allowed_marketplaces": self.allowed_marketplaces,
            "blocked_marketplaces": self.blocked_marketplaces,
            "allowed_publishers": self.allowed_publishers,
            "blocked_publishers": self.blocked_publishers,
            "allowed_plugins": self.allowed_plugins,
            "blocked_plugins": self.blocked_plugins,
            "require_signatures": self.require_signatures,
            "require_trusted_publishers": self.require_trusted_publishers,
            "require_approval_for_install": self.require_approval_for_install,
            "auto_update_allowed": self.auto_update_allowed,
            "auto_update_sources": self.auto_update_sources,
            "audit_all_installs": self.audit_all_installs,
            "audit_all_operations": self.audit_all_operations,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PluginPolicy":
        """Create from dictionary."""
        policy = cls(
            name=data["name"],
            version=data.get("version", "1.0"),
            description=data.get("description", ""),
            allowed_marketplaces=data.get("allowed_marketplaces", []),
            blocked_marketplaces=data.get("blocked_marketplaces", []),
            allowed_publishers=data.get("allowed_publishers", []),
            blocked_publishers=data.get("blocked_publishers", []),
            allowed_plugins=data.get("allowed_plugins", []),
            blocked_plugins=data.get("blocked_plugins", []),
            require_signatures=data.get("require_signatures", False),
            require_trusted_publishers=data.get("require_trusted_publishers", False),
            require_approval_for_install=data.get("require_approval_for_install", False),
            auto_update_allowed=data.get("auto_update_allowed", True),
            auto_update_sources=data.get("auto_update_sources", []),
            audit_all_installs=data.get("audit_all_installs", True),
            audit_all_operations=data.get("audit_all_operations", False),
        )

        # Load rules
        for rule_data in data.get("rules", []):
            policy.rules.append(
                PolicyRule(
                    name=rule_data["name"],
                    description=rule_data.get("description", ""),
                    scope=PolicyScope(rule_data["scope"]),
                    pattern=rule_data["pattern"],
                    action=PolicyAction(rule_data["action"]),
                    message=rule_data.get("message"),
                )
            )

        return policy


class PolicyManager:
    """Manages plugin policies.

    Loads and applies organization policies for plugin management.
    """

    DEFAULT_POLICY_PATHS = [
        ".pilotcode/policy.json",
        ".claude/policy.json",
        ".config/pilotcode/policy.json",
    ]

    def __init__(self, policy_path: Optional[Path] = None):
        self.policy: Optional[PluginPolicy] = None
        self.policy_path: Optional[Path] = policy_path
        self._load_policy()

    def _load_policy(self) -> None:
        """Load policy from file."""
        # Try specified path first
        if self.policy_path and self.policy_path.exists():
            self._load_from_path(self.policy_path)
            return

        # Try default paths
        for path_str in self.DEFAULT_POLICY_PATHS:
            path = Path(path_str)
            if path.exists():
                self._load_from_path(path)
                return

        # No policy found - use default (permissive)
        self.policy = PluginPolicy(name="default")

    def _load_from_path(self, path: Path) -> None:
        """Load policy from a specific path."""
        try:
            with open(path, "r") as f:
                data = json.load(f)
            self.policy = PluginPolicy.from_dict(data)
            self.policy_path = path
        except (json.JSONDecodeError, KeyError, IOError) as e:
            print(f"Warning: Failed to load policy from {path}: {e}")
            self.policy = PluginPolicy(name="default")

    def save_policy(self, path: Optional[Path] = None) -> None:
        """Save current policy to file."""
        if not self.policy:
            return

        save_path = path or self.policy_path or Path(".pilotcode/policy.json")
        save_path.parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, "w") as f:
            json.dump(self.policy.to_dict(), f, indent=2)

    def check_marketplace(self, marketplace: str) -> tuple[bool, Optional[str]]:
        """Check if marketplace is allowed.

        Returns:
            Tuple of (allowed, message)
        """
        if not self.policy:
            return True, None

        # Check blocklist first
        if marketplace in self.policy.blocked_marketplaces:
            return False, f"Marketplace '{marketplace}' is blocked by policy"

        # Check allowlist if defined
        if self.policy.allowed_marketplaces:
            if marketplace not in self.policy.allowed_marketplaces:
                return False, f"Marketplace '{marketplace}' is not in allowed list"

        return True, None

    def check_publisher(self, publisher: str) -> tuple[bool, Optional[str]]:
        """Check if publisher is allowed.

        Returns:
            Tuple of (allowed, message)
        """
        if not self.policy:
            return True, None

        # Check blocklist
        if publisher in self.policy.blocked_publishers:
            return False, f"Publisher '{publisher}' is blocked by policy"

        # Check allowlist if defined
        if self.policy.allowed_publishers:
            if publisher not in self.policy.allowed_publishers:
                return False, f"Publisher '{publisher}' is not in allowed list"

        return True, None

    def check_plugin(self, plugin_id: str) -> tuple[bool, Optional[str]]:
        """Check if plugin is allowed.

        Returns:
            Tuple of (allowed, message)
        """
        if not self.policy:
            return True, None

        # Extract name and marketplace
        if "@" in plugin_id:
            name, marketplace = plugin_id.rsplit("@", 1)
        else:
            name, marketplace = plugin_id, None

        # Check blocklist
        if plugin_id in self.policy.blocked_plugins:
            return False, f"Plugin '{plugin_id}' is blocked by policy"
        if name in self.policy.blocked_plugins:
            return False, f"Plugin '{name}' is blocked by policy"

        # Check allowlist if defined
        if self.policy.allowed_plugins:
            allowed = (
                plugin_id in self.policy.allowed_plugins or name in self.policy.allowed_plugins
            )
            if not allowed:
                return False, f"Plugin '{plugin_id}' is not in allowed list"

        # Check marketplace
        if marketplace:
            allowed, msg = self.check_marketplace(marketplace)
            if not allowed:
                return False, msg

        return True, None

    def check_rules(
        self,
        marketplace: str,
        publisher: str,
        plugin_id: str,
    ) -> tuple[PolicyAction, Optional[str]]:
        """Check policy rules.

        Returns:
            Tuple of (action, message)
        """
        if not self.policy:
            return PolicyAction.ALLOW, None

        for rule in self.policy.rules:
            # Check scope and match
            if rule.scope == PolicyScope.MARKETPLACE:
                if rule.matches(marketplace):
                    return rule.action, rule.message or f"Rule '{rule.name}' matched"
            elif rule.scope == PolicyScope.PUBLISHER:
                if rule.matches(publisher):
                    return rule.action, rule.message or f"Rule '{rule.name}' matched"
            elif rule.scope == PolicyScope.PLUGIN:
                if rule.matches(plugin_id):
                    return rule.action, rule.message or f"Rule '{rule.name}' matched"
            elif rule.scope == PolicyScope.GLOBAL:
                if rule.matches(plugin_id):
                    return rule.action, rule.message or f"Rule '{rule.name}' matched"

        return PolicyAction.ALLOW, None

    def can_install(self, plugin_id: str, publisher: str, marketplace: str) -> tuple[bool, str]:
        """Comprehensive check if plugin can be installed.

        Returns:
            Tuple of (can_install, message)
        """
        # Check plugin
        allowed, msg = self.check_plugin(plugin_id)
        if not allowed:
            return False, msg

        # Check publisher
        allowed, msg = self.check_publisher(publisher)
        if not allowed:
            return False, msg

        # Check marketplace
        allowed, msg = self.check_marketplace(marketplace)
        if not allowed:
            return False, msg

        # Check rules
        action, msg = self.check_rules(marketplace, publisher, plugin_id)
        if action == PolicyAction.DENY:
            return False, msg or "Denied by policy"
        if action == PolicyAction.REQUIRE_APPROVAL:
            return True, "Requires approval"

        return True, "Allowed"

    def can_auto_update(self, plugin_id: str, marketplace: str) -> bool:
        """Check if auto-update is allowed."""
        if not self.policy:
            return True

        if not self.policy.auto_update_allowed:
            return False

        if self.policy.auto_update_sources:
            return marketplace in self.policy.auto_update_sources

        return True

    def requires_approval(self, plugin_id: str) -> bool:
        """Check if installation requires approval."""
        if not self.policy:
            return False

        return self.policy.require_approval_for_install

    def requires_signature(self) -> bool:
        """Check if signatures are required."""
        if not self.policy:
            return False

        return self.policy.require_signatures

    def requires_trusted_publisher(self) -> bool:
        """Check if trusted publishers are required."""
        if not self.policy:
            return False

        return self.policy.require_trusted_publishers

    def should_audit_installs(self) -> bool:
        """Check if installs should be audited."""
        if not self.policy:
            return False

        return self.policy.audit_all_installs

    def get_policy_summary(self) -> str:
        """Get a human-readable policy summary."""
        if not self.policy:
            return "No policy configured"

        lines = [
            f"Policy: {self.policy.name}",
            f"Version: {self.policy.version}",
        ]

        if self.policy.description:
            lines.append(f"Description: {self.policy.description}")

        lines.append("")

        # Lists
        if self.policy.allowed_marketplaces:
            lines.append(f"Allowed Marketplaces: {', '.join(self.policy.allowed_marketplaces)}")
        if self.policy.blocked_marketplaces:
            lines.append(f"Blocked Marketplaces: {', '.join(self.policy.blocked_marketplaces)}")
        if self.policy.allowed_publishers:
            lines.append(f"Allowed Publishers: {', '.join(self.policy.allowed_publishers)}")
        if self.policy.blocked_publishers:
            lines.append(f"Blocked Publishers: {', '.join(self.policy.blocked_publishers)}")

        lines.append("")

        # Requirements
        reqs = []
        if self.policy.require_signatures:
            reqs.append("Signatures required")
        if self.policy.require_trusted_publishers:
            reqs.append("Trusted publishers required")
        if self.policy.require_approval_for_install:
            reqs.append("Approval required for install")

        if reqs:
            lines.append("Requirements: " + ", ".join(reqs))

        return "\n".join(lines)


class PolicyError(Exception):
    """Policy-related error."""

    pass
