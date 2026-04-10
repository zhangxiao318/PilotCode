"""Built-in hooks for common functionality.

These hooks provide basic functionality out of the box.
"""

from __future__ import annotations

import fnmatch
from typing import Optional

from .types import HookType, HookContext, HookResult, PermissionDecision
from .manager import HookManager


def register_builtin_hooks(manager: Optional[HookManager] = None) -> None:
    """Register built-in hooks.

    Args:
        manager: HookManager to register with (uses global if None)
    """
    if manager is None:
        from .manager import get_hook_manager

        manager = get_hook_manager()

    # Register logging hook
    _register_logging_hooks(manager)

    # Register permission hooks
    _register_permission_hooks(manager)

    # Register safety hooks
    _register_safety_hooks(manager)


def _register_logging_hooks(manager: HookManager) -> None:
    """Register basic logging hooks."""

    @manager.register(HookType.PRE_TOOL_USE, name="tool-use-logger", priority=-100)
    async def log_tool_use(context: HookContext) -> HookResult:
        """Log tool usage (low priority so it runs last)."""
        # This is a placeholder - real implementation would use proper logging
        # print(f"[HOOK] Tool: {context.tool_name}, Input: {context.tool_input}")
        return HookResult()

    @manager.register(HookType.SESSION_START, name="session-logger")
    async def log_session_start(context: HookContext) -> HookResult:
        """Log session start."""
        # print(f"[HOOK] Session started: {context.session_id}")
        return HookResult()


def _register_permission_hooks(manager: HookManager) -> None:
    """Register permission-related hooks."""

    @manager.register(HookType.PERMISSION_REQUEST, name="auto-allow-readonly", priority=100)
    async def auto_allow_readonly(context: HookContext) -> HookResult:
        """Auto-allow read-only operations."""
        details = context.metadata.get("details", {})
        tool_name = details.get("tool_name", "")

        # List of read-only tools that can be auto-allowed
        read_only_tools = ["Read", "Glob", "Grep", "Ls", "View"]

        if tool_name in read_only_tools:
            return HookResult(
                permission_decision=PermissionDecision(
                    behavior="allow",
                    message=f"Auto-allowed read-only tool: {tool_name}",
                )
            )

        return HookResult()  # Passthrough

    @manager.register(HookType.PRE_TOOL_USE, name="destructive-operation-warning", priority=50)
    async def warn_destructive_operations(context: HookContext) -> HookResult:
        """Add warnings for potentially destructive operations."""
        tool_name = context.tool_name or ""
        tool_input = context.tool_input or {}

        # Check for destructive operations
        destructive_tools = ["Bash", "Write", "Edit", "Delete"]

        if tool_name in destructive_tools:
            # Check for specific patterns
            if tool_name == "Bash":
                command = tool_input.get("command", "")
                dangerous_patterns = [
                    "rm -rf /",
                    "rm -rf /*",
                    "> /dev/sda",
                    "mkfs.",
                    "dd if=",
                ]
                for pattern in dangerous_patterns:
                    if pattern in command:
                        return HookResult(
                            allow_execution=False,
                            stop_reason=f"Dangerous command detected: {pattern}",
                            message=f"Blocked potentially destructive command: {command}",
                        )

        return HookResult()


def _register_safety_hooks(manager: HookManager) -> None:
    """Register safety-related hooks."""

    @manager.register(HookType.PRE_TOOL_USE, name="git-safety", priority=75)
    async def git_safety_hook(context: HookContext) -> HookResult:
        """Add safety checks for git operations."""
        tool_name = context.tool_name
        tool_input = context.tool_input or {}

        if tool_name == "Bash":
            command = tool_input.get("command", "")

            # Check for git push --force
            if "git push" in command and ("--force" in command or "-f" in command):
                return HookResult(
                    allow_execution=True,  # Allow but warn
                    message="⚠️ Warning: Force push detected. Ensure you understand the risks.",
                    additional_context="This is a force push operation.",
                )

            # Check for git reset --hard
            if "git reset" in command and "--hard" in command:
                return HookResult(
                    allow_execution=True,
                    message="⚠️ Warning: Hard reset will discard uncommitted changes.",
                )

        return HookResult()

    @manager.register(HookType.FILE_CHANGED, name="auto-refresh-on-change")
    async def auto_refresh(context: HookContext) -> HookResult:
        """Handle file changes - placeholder for auto-refresh logic."""
        # This could trigger file watchers, clear caches, etc.
        return HookResult(
            additional_context=f"File changed: {context.file_path}",
        )


# Pattern-based permission rules
class PermissionRule:
    """A rule for automatically handling permissions."""

    def __init__(
        self,
        tool_pattern: str,
        behavior: str,  # allow, deny, ask
        path_pattern: Optional[str] = None,
        message: Optional[str] = None,
    ):
        self.tool_pattern = tool_pattern
        self.behavior = behavior
        self.path_pattern = path_pattern
        self.message = message

    def matches(self, tool_name: str, tool_input: dict) -> bool:
        """Check if this rule matches the tool call."""
        # Match tool name
        if not fnmatch.fnmatch(tool_name, self.tool_pattern):
            return False

        # Match path if specified
        if self.path_pattern:
            # Try common path fields
            for key in ["path", "file_path", "file", "directory", "dir"]:
                path = tool_input.get(key)
                if path and fnmatch.fnmatch(str(path), self.path_pattern):
                    return True
            return False

        return True


class PermissionRuleSet:
    """A set of permission rules."""

    def __init__(self):
        self.rules: list[PermissionRule] = []

    def add_rule(self, rule: PermissionRule) -> None:
        """Add a rule to the set."""
        self.rules.append(rule)

    def check(
        self,
        tool_name: str,
        tool_input: dict,
    ) -> Optional[PermissionDecision]:
        """Check rules against a tool call.

        Returns:
            PermissionDecision if a rule matches, None otherwise
        """
        for rule in self.rules:
            if rule.matches(tool_name, tool_input):
                return PermissionDecision(
                    behavior=rule.behavior,
                    message=rule.message,
                )
        return None

    def create_hook_callback(self):
        """Create a hook callback from this rule set."""
        rule_set = self

        async def permission_hook(context: HookContext) -> HookResult:
            if context.hook_type != HookType.PERMISSION_REQUEST:
                return HookResult()

            details = context.metadata.get("details", {})
            tool_name = details.get("tool_name", "")
            tool_input = details.get("tool_input", {})

            decision = rule_set.check(tool_name, tool_input)
            if decision:
                return HookResult(permission_decision=decision)

            return HookResult()

        return permission_hook


def create_default_permission_rules() -> PermissionRuleSet:
    """Create a default set of permission rules."""
    rules = PermissionRuleSet()

    # Allow all read operations
    rules.add_rule(PermissionRule("Read", "allow", message="Auto-allowed file read"))
    rules.add_rule(PermissionRule("Glob", "allow", message="Auto-allowed file glob"))
    rules.add_rule(PermissionRule("Grep", "allow", message="Auto-allowed file search"))

    # Protect sensitive paths
    rules.add_rule(
        PermissionRule("*", "ask", path_pattern="*.ssh/*"),
        message="SSH directory access requires confirmation",
    )
    rules.add_rule(
        PermissionRule("*", "ask", path_pattern="*.gnupg/*"),
        message="GPG directory access requires confirmation",
    )
    rules.add_rule(
        PermissionRule("*", "ask", path_pattern="*/.env*"),
        message="Environment file access requires confirmation",
    )

    # Protect system directories
    rules.add_rule(
        PermissionRule("*", "deny", path_pattern="/etc/*"),
        message="System directory access denied",
    )
    rules.add_rule(
        PermissionRule("*", "deny", path_pattern="/usr/*"),
        message="System directory access denied",
    )

    return rules


# Hook to load hooks from plugins
def load_plugin_hooks(
    hooks_config: dict,
    plugin_source: str,
    manager: Optional[HookManager] = None,
) -> None:
    """Load hooks from a plugin's hooks configuration.

    Args:
        hooks_config: Hooks configuration from plugin
        plugin_source: Plugin identifier
        manager: HookManager to register with
    """
    if manager is None:
        from .manager import get_hook_manager

        manager = get_hook_manager()

    # Map hook names to types
    hook_type_map = {
        "preToolUse": HookType.PRE_TOOL_USE,
        "postToolUse": HookType.POST_TOOL_USE,
        "postToolUseFailure": HookType.POST_TOOL_USE_FAILURE,
        "sessionStart": HookType.SESSION_START,
        "userPromptSubmit": HookType.USER_PROMPT_SUBMIT,
        "permissionRequest": HookType.PERMISSION_REQUEST,
        "cwdChanged": HookType.CWD_CHANGED,
        "fileChanged": HookType.FILE_CHANGED,
    }

    for hook_name, hook_list in hooks_config.items():
        hook_type = hook_type_map.get(hook_name)
        if not hook_type:
            continue

        for hook_def in hook_list:
            if isinstance(hook_def, str):
                # Simple command hook
                # In real implementation, would load from file
                pass
            elif isinstance(hook_def, dict):
                # Structured hook definition
                # In real implementation, would load callback from specified source
                pass
