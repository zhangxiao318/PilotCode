"""Risk assessment for tools and commands - ClaudeCode-style implementation.

This module provides:
1. Command risk classification
2. Tool risk scoring
3. Automatic permission for read-only operations
"""

from enum import Enum
from dataclasses import dataclass
from typing import Any
import re


class RiskLevel(Enum):
    """Risk levels for operations."""

    NONE = "none"  # Read-only, no risk
    LOW = "low"  # Low risk (e.g., listing files)
    MEDIUM = "medium"  # Medium risk (e.g., writing files)
    HIGH = "high"  # High risk (e.g., deleting files)
    CRITICAL = "critical"  # Critical risk (e.g., rm -rf, system commands)


@dataclass
class RiskAssessment:
    """Risk assessment result."""

    level: RiskLevel
    reason: str
    auto_allow: bool
    requires_confirmation: bool
    destructive: bool
    read_only: bool


class CommandRiskAnalyzer:
    """Analyze command risk similar to ClaudeCode."""

    # Destructive patterns
    DESTRUCTIVE_PATTERNS = [
        (r"\brm\s+-rf\b", RiskLevel.CRITICAL, "Force recursive delete"),
        (r"\brm\s+-f\b", RiskLevel.HIGH, "Force delete"),
        (r"\brm\s+-r\b", RiskLevel.HIGH, "Recursive delete"),
        (r"\brmdir\s+/s\b", RiskLevel.HIGH, "Windows recursive delete"),
        (r">\s*/", RiskLevel.HIGH, "Overwriting system files"),
        (r">>?\s*\$?[A-Z_]+", RiskLevel.MEDIUM, "Modifying environment variables"),
        (r"chmod\s+[-+]?[rwx]", RiskLevel.MEDIUM, "Changing permissions"),
        (r"chown\s+", RiskLevel.MEDIUM, "Changing ownership"),
        (r"mv\s+.*\s+/dev/null", RiskLevel.HIGH, "Deleting via /dev/null"),
        (r":\s*\)\s*\{\s*:\s*\|\s*:\s*\}&", RiskLevel.CRITICAL, "Fork bomb"),
        (r"curl\s+.*\s*\|\s*sh", RiskLevel.CRITICAL, "Piping curl to shell"),
        (r"wget\s+.*\s*\|\s*sh", RiskLevel.CRITICAL, "Piping wget to shell"),
        (r"dd\s+if=.*of=/dev", RiskLevel.CRITICAL, "Direct disk operations"),
        (r"mkfs", RiskLevel.CRITICAL, "Formatting filesystem"),
        (r"fdisk", RiskLevel.CRITICAL, "Partitioning operations"),
    ]

    # Read-only patterns
    READONLY_PATTERNS = [
        r"^\s*ls\b",
        r"^\s*cat\b",
        r"^\s*head\b",
        r"^\s*tail\b",
        r"^\s*grep\b",
        r"^\s*find\b",
        r"^\s*pwd\b",
        r"^\s*cd\b",
        r"^\s*echo\b",
        r"^\s*wc\b",
        r"^\s*sort\b",
        r"^\s*uniq\b",
        r"^\s*file\b",
        r"^\s*stat\b",
        r"^\s*which\b",
        r"^\s*whereis\b",
        r"^\s*ps\b",
        r"^\s*top\b",
        r"^\s*df\b",
        r"^\s*du\b",
        r"^\s*free\b",
        r"^\s*uptime\b",
        r"^\s*date\b",
        r"^\s*whoami\b",
        r"^\s*id\b",
        r"^\s*uname\b",
        r"^\s*env\b(?!\s*\[)",  # env without assignment
        r"^\s*printenv\b",
        r"^\s*git\s+(status|log|show|diff|branch|remote)",  # Read-only git commands
        r"^\s*python\s+(-c|--version|-h)",  # Python one-liners and help
        r"^\s*pytest\s+(--collect-only|-h)",  # pytest dry-run
    ]

    # Safe file patterns (reading)
    SAFE_FILE_PATTERNS = [
        r"\.(txt|md|py|js|ts|json|yaml|yml|xml|html|css|scss|sass|less)$",
        r"\.(c|cpp|h|hpp|java|go|rs|rb|php|sh|bash|zsh)$",
        r"\.(sql|graphql|prisma)$",
        r"^(README|LICENSE|CHANGELOG|CONTRIBUTING|\.gitignore|\.env)",
    ]

    # Dangerous file patterns
    DANGEROUS_FILE_PATTERNS = [
        r"/etc/(passwd|shadow|sudoers)",
        r"/sys/",
        r"/proc/",
        r"/dev/(sd|hd|nvme)",
        r"\.ssh/",
        r"\.gnupg/",
        r"\.aws/",
        r"\.docker/",
        # Windows dangerous paths (case-insensitive match)
        r"C:\\Windows\\System32",
        r"C:\\Windows\\SysWOW64",
        r"C:\\Windows\\System32\\config",
        r"C:\\Windows\\System32\\drivers\\etc\\hosts",
        r"C:\\ProgramData",
    ]

    def assess_bash_command(self, command: str) -> RiskAssessment:
        """Assess risk of a bash command."""
        command = command.strip()

        if not command:
            return RiskAssessment(
                level=RiskLevel.NONE,
                reason="Empty command",
                auto_allow=True,
                requires_confirmation=False,
                destructive=False,
                read_only=True,
            )

        # Check for destructive patterns
        for pattern, risk, reason in self.DESTRUCTIVE_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return RiskAssessment(
                    level=risk,
                    reason=f"Destructive pattern detected: {reason}",
                    auto_allow=False,
                    requires_confirmation=True,
                    destructive=True,
                    read_only=False,
                )

        # Check for read-only patterns
        for pattern in self.READONLY_PATTERNS:
            if re.match(pattern, command, re.IGNORECASE):
                return RiskAssessment(
                    level=RiskLevel.NONE,
                    reason="Read-only command",
                    auto_allow=True,
                    requires_confirmation=False,
                    destructive=False,
                    read_only=True,
                )

        # Check for write operations
        if self._is_write_operation(command):
            return RiskAssessment(
                level=RiskLevel.MEDIUM,
                reason="File modification operation",
                auto_allow=False,
                requires_confirmation=True,
                destructive=False,
                read_only=False,
            )

        # Default: medium risk for unknown commands
        return RiskAssessment(
            level=RiskLevel.MEDIUM,
            reason="Unknown command type",
            auto_allow=False,
            requires_confirmation=True,
            destructive=False,
            read_only=False,
        )

    def _is_write_operation(self, command: str) -> bool:
        """Check if command performs write operations."""
        write_indicators = [
            r"\btouch\b",
            r"\bmkdir\b",
            r"\bcp\b",
            r"\bmv\b",
            r"\becho\s+.*>",
            r"\bprint\s*\(.*>",
            r"\bwrite\b",
            r"\bappend\b",
            r">\s+[^\s]",
            r">>\s+[^\s]",
        ]
        return any(re.search(pattern, command) for pattern in write_indicators)

    def assess_file_path(self, path: str, operation: str = "read") -> RiskAssessment:
        """Assess risk of a file path."""
        path = path.strip()

        # Check for dangerous paths
        for pattern in self.DANGEROUS_FILE_PATTERNS:
            if re.search(pattern, path):
                return RiskAssessment(
                    level=RiskLevel.CRITICAL,
                    reason=f"Access to sensitive system path: {path}",
                    auto_allow=False,
                    requires_confirmation=True,
                    destructive=True,
                    read_only=False,
                )

        # Check if safe file type
        is_safe = any(re.search(pattern, path) for pattern in self.SAFE_FILE_PATTERNS)

        if operation == "read":
            if is_safe:
                return RiskAssessment(
                    level=RiskLevel.NONE,
                    reason="Safe file type for reading",
                    auto_allow=True,
                    requires_confirmation=False,
                    destructive=False,
                    read_only=True,
                )
            else:
                return RiskAssessment(
                    level=RiskLevel.LOW,
                    reason="Unknown file type",
                    auto_allow=True,  # Still allow reads
                    requires_confirmation=False,
                    destructive=False,
                    read_only=True,
                )

        elif operation in ("write", "edit"):
            return RiskAssessment(
                level=RiskLevel.MEDIUM if is_safe else RiskLevel.HIGH,
                reason=f"File {operation} operation",
                auto_allow=False,
                requires_confirmation=True,
                destructive=False,
                read_only=False,
            )

        return RiskAssessment(
            level=RiskLevel.MEDIUM,
            reason="Unknown file operation",
            auto_allow=False,
            requires_confirmation=True,
            destructive=False,
            read_only=False,
        )


class ToolRiskAnalyzer:
    """Analyze risk of tool calls."""

    TOOL_RISKS = {
        "Bash": RiskLevel.MEDIUM,
        "FileRead": RiskLevel.NONE,
        "Glob": RiskLevel.NONE,
        "Grep": RiskLevel.NONE,
        "FileWrite": RiskLevel.MEDIUM,
        "FileEdit": RiskLevel.MEDIUM,
        "PowerShell": RiskLevel.MEDIUM,
        "WebSearch": RiskLevel.NONE,
        "WebFetch": RiskLevel.NONE,
        "Agent": RiskLevel.MEDIUM,
        "TaskCreate": RiskLevel.LOW,
        "TaskStop": RiskLevel.LOW,
        "TodoWrite": RiskLevel.LOW,
        "Config": RiskLevel.LOW,
        "AskUser": RiskLevel.NONE,
        "Sleep": RiskLevel.NONE,
        "Ripgrep": RiskLevel.NONE,
    }

    def __init__(self):
        self.command_analyzer = CommandRiskAnalyzer()

    def assess_tool(self, tool_name: str, params: dict[str, Any]) -> RiskAssessment:
        """Assess risk of a tool call."""
        base_risk = self.TOOL_RISKS.get(tool_name, RiskLevel.MEDIUM)

        # Tool-specific analysis
        if tool_name == "Bash":
            command = params.get("command", "")
            return self.command_analyzer.assess_bash_command(command)

        elif tool_name in ("FileRead", "FileWrite", "FileEdit"):
            path = params.get("path") or params.get("file_path", "")
            operation = "read" if tool_name == "FileRead" else "write"
            return self.command_analyzer.assess_file_path(path, operation)

        elif tool_name == "PowerShell":
            command = params.get("command", "")
            # Check for read-only PowerShell cmdlets first
            readonly_ps_patterns = [
                r"^\s*Get-",
                r"^\s*Test-",
                r"^\s*Find-",
                r"^\s*cd\b",
                r"^\s*Set-Location\b",
                r"^\s*chdir\b",
                r"^\s*Write-Output\b",
            ]
            for pattern in readonly_ps_patterns:
                if re.match(pattern, command, re.IGNORECASE):
                    return RiskAssessment(
                        level=RiskLevel.NONE,
                        reason="Read-only PowerShell command",
                        auto_allow=True,
                        requires_confirmation=False,
                        destructive=False,
                        read_only=True,
                    )
            # Reuse bash command analyzer for consistent risk assessment
            return self.command_analyzer.assess_bash_command(command)

        elif tool_name == "Agent":
            return RiskAssessment(
                level=RiskLevel.MEDIUM,
                reason="Spawning sub-agent",
                auto_allow=False,
                requires_confirmation=True,
                destructive=False,
                read_only=False,
            )

        # Default for other tools
        auto_allow = base_risk in (RiskLevel.NONE, RiskLevel.LOW)
        return RiskAssessment(
            level=base_risk,
            reason=f"{tool_name} tool execution",
            auto_allow=auto_allow,
            requires_confirmation=not auto_allow,
            destructive=base_risk in (RiskLevel.HIGH, RiskLevel.CRITICAL),
            read_only=base_risk == RiskLevel.NONE,
        )


# Global instance
_default_risk_analyzer: ToolRiskAnalyzer | None = None


def get_risk_analyzer() -> ToolRiskAnalyzer:
    """Get global risk analyzer."""
    global _default_risk_analyzer
    if _default_risk_analyzer is None:
        _default_risk_analyzer = ToolRiskAnalyzer()
    return _default_risk_analyzer
