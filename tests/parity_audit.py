#!/usr/bin/env python3
"""Automated parity audit script.

Compares the current Python implementation against the expected feature surface
derived from the TypeScript original. Produces a markdown report and exits with
a non-zero code if critical features are missing.

Usage:
    PYTHONPATH=src python tests/parity_audit.py [--json] [--critical-only]
"""

import sys
import os
import json
import argparse
from dataclasses import dataclass, field, asdict
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pilotcode.tools.registry import get_all_tools
from pilotcode.commands.base import get_all_commands
from pilotcode.agent.agent_manager import ENHANCED_AGENT_DEFINITIONS
from pilotcode.hooks.hook_manager import HookType


@dataclass
class AuditResult:
    category: str
    total: int
    implemented: int
    missing: list[str] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)

    @property
    def coverage(self) -> float:
        return self.implemented / self.total if self.total else 1.0


CRITICAL_TOOLS = {
    "Bash", "FileRead", "FileEdit", "FileWrite",
    "Glob", "Grep", "WebSearch", "WebFetch",
    "AskUser", "TodoWrite", "Agent", "TaskCreate",
    "TaskGet", "TaskList", "TaskStop", "Brief",
    "NotebookEdit", "EnterPlanMode", "ExitPlanMode",
}

CRITICAL_COMMANDS = {
    "help", "clear", "quit", "config", "compact",
    "cost", "diff", "doctor", "export", "history",
    "model", "plan", "session", "status", "theme",
    "branch", "commit", "git", "agents", "workflow",
    "tasks", "skills", "tools",
}


def audit_tools() -> AuditResult:
    expected_tools = {
        # Core
        "Bash", "FileRead", "FileEdit", "FileWrite", "Glob", "Grep",
        "WebFetch", "WebSearch", "AskUser", "TodoWrite", "Skill",
        "Agent", "Brief", "NotebookEdit",
        # Plan/Worktree
        "EnterPlanMode", "ExitPlanMode", "UpdatePlanStep",
        "EnterWorktree", "ExitWorktree", "ListWorktrees",
        # Tasks
        "TaskOutput", "TaskStop", "TaskCreate", "TaskGet",
        "TaskUpdate", "TaskList",
        # Communication
        "SendMessage", "ReceiveMessage",
        "TeamCreate", "TeamDelete", "TeamAddMember", "TeamList",
        # MCP/LSP
        "MCP", "ListMcpResources", "ReadMcpResource", "LSP",
        # Utility
        "ToolSearch", "SyntheticOutput",
        # Git
        "GitStatus", "GitDiff", "GitLog", "GitBranch",
        # Config/Other
        "Config", "PowerShell", "REPL", "Sleep",
        "RemoteTrigger", "CronCreate", "CronDelete", "CronList", "CronUpdate",
    }
    implemented = {t.name for t in get_all_tools()}
    missing = sorted(expected_tools - implemented)
    return AuditResult(
        category="Tools",
        total=len(expected_tools),
        implemented=len(expected_tools & implemented),
        missing=missing,
        notes={
            "Core tool coverage": f"{len(expected_tools & implemented)}/{len(expected_tools)}",
        },
    )


def audit_commands() -> AuditResult:
    expected_commands = {
        # System
        "help", "clear", "quit", "config", "compact", "cost",
        "diff", "doctor", "export", "history", "model",
        "plan", "session", "status", "theme", "memory",
        "version", "tools",
        # Git
        "branch", "commit", "git", "stash", "tag", "remote",
        "merge", "rebase", "reset", "clean", "cherrypick",
        "revert", "blame", "bisect", "switch",
        # Agent/Task
        "agents", "workflow", "tasks", "skills",
        # Code
        "lint", "format", "test", "coverage",
        "symbols", "references", "review",
        # File
        "cat", "ls", "cd", "pwd", "edit", "mkdir", "rm",
        "cp", "mv", "touch", "head", "tail", "wc", "find",
        # Other
        "mcp", "lsp", "debug", "env", "cron",
        "rename", "share",
    }
    implemented = {c.name for c in get_all_commands()}
    missing = sorted(expected_commands - implemented)
    return AuditResult(
        category="Commands",
        total=len(expected_commands),
        implemented=len(expected_commands & implemented),
        missing=missing,
        notes={
            "Core command coverage": f"{len(expected_commands & implemented)}/{len(expected_commands)}",
        },
    )


def audit_agent_types() -> AuditResult:
    expected = {"coder", "debugger", "explainer", "tester", "reviewer", "planner", "explorer"}
    implemented = set(ENHANCED_AGENT_DEFINITIONS.keys())
    missing = sorted(expected - implemented)
    return AuditResult(
        category="Agent Types",
        total=len(expected),
        implemented=len(expected & implemented),
        missing=missing,
    )


def audit_hooks() -> AuditResult:
    expected = {
        "PRE_TOOL_USE", "POST_TOOL_USE",
        "PRE_AGENT_RUN", "POST_AGENT_RUN",
        "ON_ERROR", "ON_PERMISSION_DENIED",
    }
    implemented = {h.name for h in HookType}
    missing = sorted(expected - implemented)
    return AuditResult(
        category="Hook Types",
        total=len(expected),
        implemented=len(expected & implemented),
        missing=missing,
    )


def run_audit(critical_only: bool = False) -> list[AuditResult]:
    results = [
        audit_tools(),
        audit_commands(),
        audit_agent_types(),
        audit_hooks(),
    ]
    return results


def format_markdown(results: list[AuditResult]) -> str:
    lines = [
        "# PilotCode Parity Audit Report",
        "",
        "| Category | Implemented | Total | Coverage |",
        "|----------|-------------|-------|----------|",
    ]
    for r in results:
        lines.append(f"| {r.category} | {r.implemented} | {r.total} | {r.coverage:.0%} |")

    lines.append("")
    for r in results:
        if r.missing:
            lines.append(f"## Missing {r.category}")
            for item in r.missing:
                lines.append(f"- {item}")
            lines.append("")
        for k, v in r.notes.items():
            lines.append(f"**{k}:** {v}")
        lines.append("")

    return "\n".join(lines)


def check_critical_failures(results: list[AuditResult]) -> list[str]:
    failures = []
    tool_result = next((r for r in results if r.category == "Tools"), None)
    cmd_result = next((r for r in results if r.category == "Commands"), None)

    if tool_result:
        for t in CRITICAL_TOOLS:
            if t in tool_result.missing:
                failures.append(f"CRITICAL tool missing: {t}")

    if cmd_result:
        for c in CRITICAL_COMMANDS:
            if c in cmd_result.missing:
                failures.append(f"CRITICAL command missing: {c}")

    return failures


def main():
    parser = argparse.ArgumentParser(description="PilotCode parity audit")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--critical-only", action="store_true", help="Only check critical features")
    args = parser.parse_args()

    results = run_audit(critical_only=args.critical_only)
    failures = check_critical_failures(results)

    if args.json:
        payload = {
            "results": [asdict(r) for r in results],
            "critical_failures": failures,
            "pass": len(failures) == 0,
        }
        print(json.dumps(payload, indent=2))
    else:
        print(format_markdown(results))
        if failures:
            print("\n## Critical Failures")
            for f in failures:
                print(f"- {f}")

    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
