"""AI-powered security analysis for command validation.

Following Claude Code's approach of using AI to detect potential
command injection and security risks in bash commands.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .token_estimation import TokenEstimator


class RiskLevel(Enum):
    """Risk level for command security."""

    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SecurityAnalysis:
    """Result of AI security analysis."""

    is_safe: bool
    risk_level: RiskLevel
    reason: str
    command_prefix: str | None = None
    subcommand_prefixes: list[str] | None = None
    suggestions: list[str] | None = None


# Dangerous patterns that indicate potential injection
DANGEROUS_PATTERNS = [
    # Command substitution that could execute arbitrary code
    (r"\$\([^)]*[`;&|]", RiskLevel.HIGH, "Command substitution with shell operators"),
    # Backtick command substitution
    (r"`[^`]*[`;&|]", RiskLevel.HIGH, "Backtick substitution with shell operators"),
    # Process substitution
    (r"<\s*\([^)]+\)", RiskLevel.MEDIUM, "Process substitution detected"),
    # Unescaped semicolons in unexpected places
    (
        r"[^\\];\s*(?:rm|mv|cp|cat|echo|wget|curl|eval|exec)\s",
        RiskLevel.HIGH,
        "Chained commands with dangerous operations",
    ),
    # Eval with variables
    (r'\beval\s+["\']?\$', RiskLevel.CRITICAL, "Eval with variable expansion"),
    # Exec that replaces shell
    (r"\bexec\s+(?:</dev/)", RiskLevel.HIGH, "Exec with redirection"),
    # Shell injection via variables in curl/wget
    (r"(?:curl|wget)\s+[^\s]*\$", RiskLevel.MEDIUM, "URL with variable expansion"),
    # Here-document with command substitution
    (r"<<[^>]*\$\(", RiskLevel.HIGH, "Here-document with command substitution"),
    # Dynamic command construction
    (r'\b(?:sh|bash|zsh)\s+-c\s*["\']', RiskLevel.HIGH, "Shell with -c flag"),
]

# Safe command prefixes (commonly used safe commands)
SAFE_COMMANDS = {
    "ls",
    "cat",
    "head",
    "tail",
    "less",
    "more",
    "grep",
    "find",
    "git status",
    "git log",
    "git diff",
    "git show",
    "git branch",
    "git remote",
    "git config",
    "git stash",
    "git tag",
    "pwd",
    "echo",
    "cd",
    "mkdir",
    "touch",
    "cp",
    "mv",
    "rm -i",
    "wc",
    "sort",
    "uniq",
    "awk",
    "sed",
    "cut",
    "tr",
    "python",
    "python3",
    "node",
    "npm",
    "yarn",
    "pnpm",
    "cargo",
    "rustc",
    "go",
    "javac",
    "java",
    "docker ps",
    "docker images",
    "docker logs",
    "docker inspect",
    "kubectl get",
    "kubectl describe",
    "kubectl logs",
}

# Commands that need special attention
SENSITIVE_COMMANDS: dict[str, list[str] | None] = {
    "rm": ["-rf", "-fr", "--force", "-f/", "-r/"],
    "dd": ["of=", "if="],
    "mkfs": None,
    "fdisk": None,
    "parted": None,
    "chmod": None,
    "chown": None,
    "sudo": None,
    "su": None,
    "eval": None,
    "exec": None,
    "wget": None,
    "curl": None,
}


def split_command(command: str) -> list[str]:
    """Split command into subcommands by pipes and logical operators."""
    # Simple split by pipes and logical operators
    # This is a simplified version - full shell parsing is complex
    subcommands = re.split(r"\s*[|;]\s*", command)
    return [s.strip() for s in subcommands if s.strip()]


def extract_command_prefix(command: str) -> str:
    """Extract the main command prefix.

    Examples:
    - "cd path/to/files/" => "cd"
    - "git commit -m 'foo'" => "git commit"
    - "gg cat foo.py" => "gg cat"
    """
    parts = command.strip().split()
    if not parts:
        return ""

    # Handle git-like multi-word commands
    if len(parts) >= 2:
        # Common multi-word command patterns
        two_word = f"{parts[0]} {parts[1]}"
        if parts[0] in ("git", "docker", "kubectl", "npm", "yarn", "cargo", "gg"):
            return two_word

    return parts[0]


def analyze_command_dangerous_patterns(command: str) -> list[tuple[RiskLevel, str]]:
    """Analyze command for dangerous patterns using regex."""
    risks = []

    for pattern, risk_level, description in DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            risks.append((risk_level, description))

    return risks


def analyze_command_prefix_safety(prefix: str) -> RiskLevel:
    """Analyze if a command prefix is known to be safe or dangerous."""
    base_cmd = prefix.split()[0] if prefix else ""

    # Check safe list
    if prefix in SAFE_COMMANDS or base_cmd in SAFE_COMMANDS:
        return RiskLevel.SAFE

    # Check sensitive commands
    if base_cmd in SENSITIVE_COMMANDS:
        return RiskLevel.MEDIUM

    # Unknown command
    return RiskLevel.LOW


def simulate_ai_security_analysis(
    command: str, context: dict[str, Any] | None = None
) -> SecurityAnalysis:
    """Simulate AI-powered security analysis.

    In Claude Code, this would use an actual LLM call to analyze
    the command for security risks. Here we implement a rule-based
    version that mimics the AI analysis patterns.

    Args:
        command: The command to analyze
        context: Optional context about the command execution environment

    Returns:
        SecurityAnalysis with risk assessment
    """
    # Split into subcommands
    subcommands = split_command(command)

    # Extract prefixes
    main_prefix = extract_command_prefix(command)
    subcommand_prefixes = [extract_command_prefix(sc) for sc in subcommands]

    # Analyze for dangerous patterns
    pattern_risks = analyze_command_dangerous_patterns(command)

    # Analyze prefix safety
    prefix_risk = analyze_command_prefix_safety(main_prefix)

    # Combine risk assessments
    max_risk = prefix_risk
    reasons = []
    suggestions = []

    for risk_level, description in pattern_risks:
        if _risk_to_int(risk_level) > _risk_to_int(max_risk):
            max_risk = risk_level
        reasons.append(description)

    # Check for specific dangerous scenarios
    if "eval" in command or "exec" in command:
        if not _is_safe_eval_usage(command):
            max_risk = RiskLevel.CRITICAL
            reasons.append("Dynamic code execution detected")
            suggestions.append("Avoid eval/exec with user input")

    if re.search(r"\brm\s+-rf\s+[/?*~]", command):
        max_risk = RiskLevel.CRITICAL
        reasons.append("Dangerous rm -rf pattern")
        suggestions.append("Double-check the target path before executing")

    # Check for variable expansion in URLs
    if re.search(r"(curl|wget)\s+.*\$", command):
        if not _is_safe_url_usage(command):
            max_risk = max(max_risk, RiskLevel.HIGH, key=_risk_to_int)
            reasons.append("Variable expansion in URL")
            suggestions.append("Validate URL variables to prevent injection")

    # Build final analysis
    is_safe = max_risk in (RiskLevel.SAFE, RiskLevel.LOW) and not pattern_risks

    reason = "; ".join(reasons) if reasons else "No obvious risks detected"

    # Add context-aware suggestions
    if context:
        cwd = context.get("cwd", "")
        if cwd and (".." in command or command.startswith("/")):
            # Path traversal check
            if ".." in command and not _is_safe_path_traversal(command, cwd):
                suggestions.append("Verify path traversal doesn't escape intended directory")

    return SecurityAnalysis(
        is_safe=is_safe,
        risk_level=max_risk,
        reason=reason,
        command_prefix=main_prefix,
        subcommand_prefixes=subcommand_prefixes,
        suggestions=suggestions if suggestions else None,
    )


def _risk_to_int(risk: RiskLevel) -> int:
    """Convert risk level to integer for comparison."""
    mapping = {
        RiskLevel.SAFE: 0,
        RiskLevel.LOW: 1,
        RiskLevel.MEDIUM: 2,
        RiskLevel.HIGH: 3,
        RiskLevel.CRITICAL: 4,
    }
    return mapping.get(risk, 0)


def _is_safe_eval_usage(command: str) -> bool:
    """Check if eval usage appears safe."""
    # Very conservative check - eval is generally dangerous
    # Only allow specific safe patterns
    safe_eval_patterns = [
        r'eval\s+"\$\([a-zA-Z_]+\)"',  # eval "$(cmd)" - common pattern
    ]
    for pattern in safe_eval_patterns:
        if re.search(pattern, command):
            return True
    return False


def _is_safe_url_usage(command: str) -> bool:
    """Check if URL usage with variables appears safe."""
    # Check if variable is quoted
    url_pattern = r'(?:curl|wget)\s+["\']?[^"\']*\$[a-zA-Z_][a-zA-Z0-9_]*[^"\']*["\']?'
    match = re.search(url_pattern, command)
    if match:
        # Variable is present - check if properly quoted
        matched = match.group(0)
        if '"' not in matched and "'" not in matched:
            return False
    return True


def _is_safe_path_traversal(command: str, cwd: str) -> bool:
    """Check if path traversal is safe."""
    # This is a simplified check
    # Real implementation would resolve the path
    dangerous_patterns = [
        r"\.\./\.\./\.\.",  # Multiple parent references
        r"/etc/",
        r"/root/",
        r"/home/[^/]+/\.",
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, command):
            return False
    return True


# Memoization cache for security analysis
_security_analysis_cache: dict[str, SecurityAnalysis] = {}


def get_command_security_analysis(
    command: str, context: dict[str, Any] | None = None, use_cache: bool = True
) -> SecurityAnalysis:
    """Get security analysis for a command (with optional caching).

    Args:
        command: The command to analyze
        context: Optional context about execution environment
        use_cache: Whether to use result caching

    Returns:
        SecurityAnalysis result
    """
    if use_cache:
        # Create cache key from command and relevant context
        cache_key = command
        if context:
            cache_key += f":{context.get('cwd', '')}"

        if cache_key in _security_analysis_cache:
            return _security_analysis_cache[cache_key]

        result = simulate_ai_security_analysis(command, context)
        _security_analysis_cache[cache_key] = result
        return result

    return simulate_ai_security_analysis(command, context)


def clear_security_cache() -> None:
    """Clear the security analysis cache."""
    global _security_analysis_cache
    _security_analysis_cache = {}


def estimate_security_check_tokens(command: str) -> int:
    """Estimate tokens needed for AI security check.

    Used for token budgeting before making actual AI calls.
    """
    estimator = TokenEstimator()
    # Security analysis prompt + command
    prompt = """Analyze this bash command for security risks:
Command: {command}

Check for:
1. Command injection vulnerabilities
2. Path traversal risks
3. Unsafe variable expansion
4. Dangerous operations

Respond with risk level and explanation."""

    return estimator.estimate(prompt.format(command=command))
