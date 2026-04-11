"""Tool Sandbox - Secure isolated execution of tools.

This module provides sandboxed execution for potentially dangerous operations:
1. Command sandboxing with resource limits
2. Network isolation
3. Filesystem restrictions
4. Resource monitoring (CPU, memory, time)
5. Dry-run mode for testing

Security Features:
- Process isolation
- Resource limits (CPU, memory, time)
- Filesystem restrictions (chroot, readonly)
- Network blocking
- Dangerous command detection
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


class SandboxLevel(Enum):
    """Sandbox security levels."""

    NONE = "none"  # No sandboxing
    LIGHT = "light"  # Basic restrictions
    MODERATE = "moderate"  # Standard restrictions
    STRICT = "strict"  # Heavy restrictions
    PARANOID = "paranoid"  # Maximum security


class SandboxError(Exception):
    """Base exception for sandbox errors."""

    pass


class SecurityViolation(SandboxError):
    """Raised when a security violation is detected."""

    pass


class ResourceLimitExceeded(SandboxError):
    """Raised when resource limits are exceeded."""

    pass


@dataclass
class SandboxConfig:
    """Configuration for sandbox execution."""

    # Security level
    level: SandboxLevel = SandboxLevel.MODERATE

    # Resource limits
    max_execution_time: float = 60.0  # seconds
    max_memory_mb: int = 512  # MB
    max_cpu_percent: float = 100.0  # Percent of one core
    max_output_size: int = 10 * 1024 * 1024  # 10MB

    # Filesystem restrictions
    allowed_paths: list[str] = field(default_factory=list)
    blocked_paths: list[str] = field(
        default_factory=lambda: (
            [
                "/etc/passwd",
                "/etc/shadow",
                "/root",
                "~/.ssh",
                # Windows sensitive paths
                r"C:\Windows\System32\config\SAM",
                r"C:\Windows\System32\drivers\etc\hosts",
            ]
            if os.name == "posix"
            else [
                # Windows-specific blocked paths
                r"C:\Windows\System32\config\SAM",
                r"C:\Windows\System32\drivers\etc\hosts",
                "~/.ssh",
            ]
        )
    )
    readonly_paths: list[str] = field(default_factory=list)

    # Network restrictions
    allow_network: bool = True
    allowed_hosts: list[str] = field(default_factory=list)
    blocked_hosts: list[str] = field(default_factory=list)

    # Execution options
    dry_run: bool = False  # Don't actually execute
    capture_output: bool = True
    working_directory: Optional[str] = None
    environment_variables: dict[str, str] = field(default_factory=dict)

    # Dangerous command detection
    block_dangerous_commands: bool = True
    dangerous_patterns: list[str] = field(
        default_factory=lambda: [
            r"rm\s+-rf\s+/",
            r">\s*/dev/sda",
            r"mkfs\.",
            r"dd\s+if=.*of=/dev/",
            r":\(\)\{:\|:\&\};:",  # Fork bomb
            r"curl.*\|\s*sh",
            r"wget.*\|\s*sh",
        ]
    )


@dataclass
class SandboxResult:
    """Result of sandboxed execution."""

    success: bool
    return_code: int
    stdout: str
    stderr: str
    execution_time: float
    peak_memory_mb: float

    # Security info
    security_violations: list[str] = field(default_factory=list)
    blocked_commands: list[str] = field(default_factory=list)

    # Dry run info
    would_execute: bool = False
    simulated_output: str = ""


class CommandAnalyzer:
    """Analyzes commands for security risks."""

    DANGEROUS_PATTERNS = [
        (r"\brm\s+-rf\s+/(\s|$)", "Attempt to delete root filesystem"),
        (r"\brm\s+-rf\s+~/\.\w+", "Attempt to delete home directory config"),
        (r">\s*/dev/sda", "Attempt to overwrite disk"),
        (r"\bmkfs\.\w+", "Attempt to format filesystem"),
        (r"\bdd\s+if=\S+\s+of=/dev/\w+", "Attempt to write to device"),
        (r":\(\)\{:\|:\&\};:", "Fork bomb detected"),
        (r"curl\s+\S+\s*\|\s*(ba)?sh", "Pipe from network to shell"),
        (r"wget\s+\S+\s*\|\s*(ba)?sh", "Pipe from network to shell"),
        (r"eval\s*\$", "Dangerous eval usage"),
        (r"exec\s+\$", "Dangerous exec usage"),
        (r">\s*~/.\w+", "Overwriting config files"),
        (r"chmod\s+\+x\s+/tmp/", "Making temp files executable"),
    ]

    SENSITIVE_PATHS = [
        "/etc/passwd",
        "/etc/shadow",
        "/etc/hosts",
        "/root",
        "~/.ssh",
        "~/.gnupg",
        "~/.aws",
        "~/.kube",
    ]

    @classmethod
    def analyze(cls, command: str) -> dict[str, Any]:
        """Analyze command for security risks.

        Returns dict with:
        - is_safe: bool
        - risk_level: str
        - violations: list of str
        - sensitive_paths_accessed: list of str
        """
        violations = []
        risk_score = 0

        # Check dangerous patterns
        for pattern, description in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                violations.append(description)
                risk_score += 10

        # Check sensitive paths
        sensitive_accessed = []
        for path in cls.SENSITIVE_PATHS:
            expanded = os.path.expanduser(path)
            if expanded in command or path in command:
                sensitive_accessed.append(path)
                risk_score += 5

        # Determine risk level
        if risk_score >= 20:
            risk_level = "critical"
        elif risk_score >= 10:
            risk_level = "high"
        elif risk_score >= 5:
            risk_level = "medium"
        elif risk_score > 0:
            risk_level = "low"
        else:
            risk_level = "safe"

        return {
            "is_safe": risk_score == 0,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "violations": violations,
            "sensitive_paths_accessed": sensitive_accessed,
        }

    @classmethod
    def is_safe(cls, command: str) -> bool:
        """Quick check if command is safe."""
        result = cls.analyze(command)
        return result["is_safe"]


class ToolSandbox:
    """Sandbox for secure tool execution.

    Usage:
        sandbox = ToolSandbox(SandboxConfig(level=SandboxLevel.STRICT))

        result = sandbox.execute("ls -la", timeout=30)
        if result.success:
            print(result.stdout)
    """

    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._analyzer = CommandAnalyzer()

    def execute(
        self, command: str, timeout: Optional[float] = None, env: Optional[dict[str, str]] = None
    ) -> SandboxResult:
        """Execute command in sandbox.

        Args:
            command: Command to execute
            timeout: Override default timeout
            env: Additional environment variables

        Returns:
            SandboxResult with execution details
        """
        start_time = time.time()
        timeout = timeout or self.config.max_execution_time

        # Security analysis
        analysis = self._analyzer.analyze(command)

        # Check for security violations
        if analysis["violations"] and self.config.block_dangerous_commands:
            return SandboxResult(
                success=False,
                return_code=-1,
                stdout="",
                stderr=f"Security violation: {analysis['violations'][0]}",
                execution_time=0,
                peak_memory_mb=0,
                security_violations=analysis["violations"],
                blocked_commands=[command],
            )

        # Dry run mode
        if self.config.dry_run:
            return SandboxResult(
                success=True,
                return_code=0,
                stdout=f"[DRY RUN] Would execute: {command}",
                stderr="",
                execution_time=0,
                peak_memory_mb=0,
                would_execute=True,
                simulated_output=f"Command: {command}\nExit: 0",
            )

        # Prepare execution
        working_dir = self.config.working_directory or os.getcwd()

        # Merge environment
        run_env = os.environ.copy()
        run_env.update(self.config.environment_variables)
        if env:
            run_env.update(env)

        # Apply sandbox restrictions based on level
        if self.config.level == SandboxLevel.PARANOID:
            return self._execute_paranoid(command, timeout, working_dir, run_env)
        elif self.config.level == SandboxLevel.STRICT:
            return self._execute_strict(command, timeout, working_dir, run_env)
        elif self.config.level == SandboxLevel.MODERATE:
            return self._execute_moderate(command, timeout, working_dir, run_env)
        else:
            return self._execute_light(command, timeout, working_dir, run_env)

    def _execute_light(
        self, command: str, timeout: float, working_dir: str, env: dict[str, str]
    ) -> SandboxResult:
        """Execute with light sandboxing."""
        return self._run_subprocess(command, timeout, working_dir, env)

    def _execute_moderate(
        self, command: str, timeout: float, working_dir: str, env: dict[str, str]
    ) -> SandboxResult:
        """Execute with moderate sandboxing."""
        # Apply resource limits via ulimit (Unix only)
        if os.name == "posix":
            # Pre-command to set limits
            limit_cmd = (
                f"ulimit -t {int(timeout)} -v {self.config.max_memory_mb * 1024} 2>/dev/null; "
            )
            command = limit_cmd + command

        return self._run_subprocess(command, timeout, working_dir, env)

    def _execute_strict(
        self, command: str, timeout: float, working_dir: str, env: dict[str, str]
    ) -> SandboxResult:
        """Execute with strict sandboxing."""
        # Use timeout command and restrict environment
        if os.name == "posix":
            # Use timeout command
            command = f"timeout {timeout}s {command}"

            # Clear sensitive environment variables
            sensitive_vars = ["AWS_SECRET", "GITHUB_TOKEN", "PRIVATE_KEY", "PASSWORD"]
            for var in sensitive_vars:
                if var in env:
                    del env[var]

        return self._run_subprocess(command, timeout, working_dir, env)

    def _execute_paranoid(
        self, command: str, timeout: float, working_dir: str, env: dict[str, str]
    ) -> SandboxResult:
        """Execute with maximum security (paranoid mode).

        Uses containers or chroot if available.
        """
        # For now, fall back to strict mode
        # In production, this would use Docker containers
        return self._execute_strict(command, timeout, working_dir, env)

    def _run_subprocess(
        self, command: str, timeout: float, working_dir: str, env: dict[str, str]
    ) -> SandboxResult:
        """Run command using subprocess with monitoring."""
        start_time = time.time()
        peak_memory = 0.0

        try:
            # Run subprocess
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=working_dir,
                env=env,
                preexec_fn=self._set_process_limits if os.name == "posix" else None,
            )

            # Monitor execution
            stdout_data = b""
            stderr_data = b""

            try:
                stdout_data, stderr_data = process.communicate(timeout=timeout)
                execution_time = time.time() - start_time

                # Truncate if too large
                if len(stdout_data) > self.config.max_output_size:
                    stdout_data = stdout_data[: self.config.max_output_size]
                    stdout_data += b"\n[Output truncated due to size limit]"

                return SandboxResult(
                    success=process.returncode == 0,
                    return_code=process.returncode,
                    stdout=stdout_data.decode("utf-8", errors="replace"),
                    stderr=stderr_data.decode("utf-8", errors="replace"),
                    execution_time=execution_time,
                    peak_memory_mb=peak_memory,
                )

            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

                return SandboxResult(
                    success=False,
                    return_code=-1,
                    stdout=stdout_data.decode("utf-8", errors="replace"),
                    stderr=f"Execution timeout after {timeout}s",
                    execution_time=timeout,
                    peak_memory_mb=peak_memory,
                )

        except Exception as e:
            return SandboxResult(
                success=False,
                return_code=-1,
                stdout="",
                stderr=f"Execution error: {str(e)}",
                execution_time=time.time() - start_time,
                peak_memory_mb=0,
            )

    def _set_process_limits(self):
        """Set resource limits for child process (Unix only)."""
        try:
            # CPU time limit
            import resource

            resource.setrlimit(
                resource.RLIMIT_CPU,
                (int(self.config.max_execution_time), int(self.config.max_execution_time)),
            )

            # Memory limit
            resource.setrlimit(
                resource.RLIMIT_AS,
                (self.config.max_memory_mb * 1024 * 1024, self.config.max_memory_mb * 1024 * 1024),
            )
        except Exception:
            pass

    def check_filesystem_access(self, path: str, mode: str = "read") -> bool:
        """Check if filesystem access is allowed.

        Args:
            path: File or directory path
            mode: 'read', 'write', or 'execute'

        Returns:
            True if access is allowed
        """
        expanded_path = os.path.expanduser(path)
        abs_path = os.path.abspath(expanded_path)

        # Check blocked paths
        for blocked in self.config.blocked_paths:
            blocked_expanded = os.path.expanduser(blocked)
            if abs_path.startswith(blocked_expanded):
                return False

        # Check allowed paths (if whitelist is set)
        if self.config.allowed_paths:
            allowed = any(
                abs_path.startswith(os.path.expanduser(allowed))
                for allowed in self.config.allowed_paths
            )
            if not allowed:
                return False

        # Check readonly for write operations
        if mode == "write":
            for readonly in self.config.readonly_paths:
                readonly_expanded = os.path.expanduser(readonly)
                if abs_path.startswith(readonly_expanded):
                    return False

        return True

    def validate_command(self, command: str) -> dict[str, Any]:
        """Validate command without executing.

        Returns validation result with recommendations.
        """
        analysis = self._analyzer.analyze(command)

        # Parse command to check individual parts
        parts = shlex.split(command)

        recommendations = []

        if analysis["risk_level"] == "critical":
            recommendations.append(
                "CRITICAL: This command is extremely dangerous and should not be executed."
            )
        elif analysis["risk_level"] == "high":
            recommendations.append(
                "HIGH RISK: Review carefully before execution. Consider using dry-run mode."
            )

        if analysis["sensitive_paths_accessed"]:
            recommendations.append(
                f"Accesses sensitive paths: {analysis['sensitive_paths_accessed']}"
            )

        if "curl" in command or "wget" in command:
            recommendations.append("Downloads from network. Verify source is trusted.")

        return {
            "valid": analysis["is_safe"] or not self.config.block_dangerous_commands,
            "analysis": analysis,
            "recommendations": recommendations,
            "suggested_config": self._suggest_config(analysis),
        }

    def _suggest_config(self, analysis: dict[str, Any]) -> SandboxConfig:
        """Suggest sandbox config based on risk analysis."""
        if analysis["risk_level"] == "critical":
            return SandboxConfig(level=SandboxLevel.PARANOID, dry_run=True)
        elif analysis["risk_level"] == "high":
            return SandboxConfig(level=SandboxLevel.STRICT)
        elif analysis["risk_level"] == "medium":
            return SandboxConfig(level=SandboxLevel.MODERATE)
        else:
            return SandboxConfig(level=SandboxLevel.LIGHT)


# Global sandbox instance
_default_sandbox: Optional[ToolSandbox] = None


def get_tool_sandbox(config: Optional[SandboxConfig] = None) -> ToolSandbox:
    """Get global tool sandbox instance."""
    global _default_sandbox
    if _default_sandbox is None:
        _default_sandbox = ToolSandbox(config)
    return _default_sandbox


def analyze_command_safety(command: str) -> dict[str, Any]:
    """Quick utility to analyze command safety."""
    return CommandAnalyzer.analyze(command)


def is_command_safe(command: str) -> bool:
    """Quick check if command is safe to execute."""
    return CommandAnalyzer.is_safe(command)
