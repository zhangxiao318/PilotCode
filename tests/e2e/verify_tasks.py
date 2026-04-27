#!/usr/bin/env python3
"""Automated verification script for E2E task modifications.

Usage:
    python verify_tasks.py          # Verify all tasks
    python verify_tasks.py --task 2 # Verify only task 2
    python verify_tasks.py --json   # Output JSON for CI integration
"""

from __future__ import annotations

import argparse
import ast
import json
import py_compile
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str = ""


@dataclass
class TaskResult:
    task_name: str
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.task_name}"


class Verifier:
    """Base verifier with common utilities."""

    def __init__(self, project_root: Path):
        self.root = project_root

    def _read_file(self, rel_path: str) -> str:
        path = self.root / rel_path
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _compile_check(self, rel_path: str) -> CheckResult:
        path = self.root / rel_path
        try:
            py_compile.compile(str(path), doraise=True)
            return CheckResult("syntax", True, f"{rel_path} compiles OK")
        except py_compile.PyCompileError as e:
            return CheckResult("syntax", False, f"{rel_path} syntax error: {e}")

    def _ast_parse(self, rel_path: str) -> ast.AST | None:
        source = self._read_file(rel_path)
        if not source:
            return None
        try:
            return ast.parse(source)
        except SyntaxError:
            return None

    def _find_function(self, tree: ast.AST, name: str) -> ast.FunctionDef | None:
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        return None


class Task2Verifier(Verifier):
    """Verify task2: add disk usage to status_cmd.py."""

    def verify(self) -> TaskResult:
        result = TaskResult("Task 2: Simple Edit (status_cmd.py)", passed=False)

        # Check 1: syntax
        result.checks.append(self._compile_check("src/pilotcode/commands/status_cmd.py"))

        source = self._read_file("src/pilotcode/commands/status_cmd.py")
        tree = self._ast_parse("src/pilotcode/commands/status_cmd.py")

        # Check 2: import shutil exists
        has_shutil = "import shutil" in source
        result.checks.append(CheckResult(
            "import_shutil", has_shutil,
            "has 'import shutil'" if has_shutil else "missing 'import shutil'"
        ))

        # Check 3: _fmt_bytes function exists
        has_fmt_bytes = tree is not None and self._find_function(tree, "_fmt_bytes") is not None
        result.checks.append(CheckResult(
            "_fmt_bytes", has_fmt_bytes,
            "_fmt_bytes() defined" if has_fmt_bytes else "_fmt_bytes() missing"
        ))

        # Check 4: disk usage in status_command
        func = self._find_function(tree, "status_command") if tree else None
        func_source = ast.unparse(func) if func else ""
        has_disk_usage = "shutil.disk_usage" in func_source or "Disk Usage" in func_source
        result.checks.append(CheckResult(
            "disk_usage", has_disk_usage,
            "disk usage section present" if has_disk_usage else "disk usage section missing"
        ))

        # Check 5: exception handling
        has_try_except = "try" in func_source and "except" in func_source
        result.checks.append(CheckResult(
            "exception_handling", has_try_except,
            "has try/except" if has_try_except else "missing try/except"
        ))

        result.passed = all(c.passed for c in result.checks)
        return result


class Task3Verifier(Verifier):
    """Verify task3: add warning symbol to bar.py."""

    def verify(self) -> TaskResult:
        result = TaskResult("Task 3: Medium Edit (bar.py)", passed=False)

        # Check 1: syntax
        result.checks.append(self._compile_check("src/pilotcode/tui_v2/components/status/bar.py"))

        source = self._read_file("src/pilotcode/tui_v2/components/status/bar.py")
        tree = self._ast_parse("src/pilotcode/tui_v2/components/status/bar.py")

        func = self._find_function(tree, "_get_right_text") if tree else None
        func_source = ast.unparse(func) if func else ""

        # Check 2: warning symbol logic exists
        has_warning = "⚠" in func_source and "80.0" in func_source
        result.checks.append(CheckResult(
            "warning_symbol", has_warning,
            "⚠ warning for pct > 80.0" if has_warning else "missing ⚠ warning logic"
        ))

        # Check 3: parts.append still exists (format preserved)
        has_append = "parts.append" in func_source
        result.checks.append(CheckResult(
            "format_preserved", has_append,
            "parts.append preserved" if has_append else "parts.append missing"
        ))

        # Check 4: no new functions added (only _get_right_text modified)
        func_count = sum(1 for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)) if tree else 0
        # bar.py originally has ~18 functions; task3 should not add/remove any
        func_count_ok = func_count <= 20
        result.checks.append(CheckResult(
            "scope_limited", func_count_ok,
            f"{func_count} functions (<=20, no new functions added)" if func_count_ok else f"{func_count} functions (too many, scope leak?)"
        ))

        result.passed = all(c.passed for c in result.checks)
        return result


class Task4Verifier(Verifier):
    """Verify task4: multi-file timestamp command integration."""

    def verify(self) -> TaskResult:
        result = TaskResult("Task 4: Multi-File Edit", passed=False)

        # Check 1: timestamp_cmd.py exists and compiles
        ts_path = "src/pilotcode/commands/timestamp_cmd.py"
        ts_exists = (self.root / ts_path).exists()
        result.checks.append(CheckResult(
            "timestamp_file", ts_exists,
            f"{ts_path} exists" if ts_exists else f"{ts_path} missing"
        ))
        if ts_exists:
            result.checks.append(self._compile_check(ts_path))

            source = self._read_file(ts_path)
            tree = self._ast_parse(ts_path)

            # Check 2: function signature and content
            func = self._find_function(tree, "timestamp_command") if tree else None
            func_source = ast.unparse(func) if func else ""
            has_time = "%Y-%m-%d %H:%M:%S" in func_source
            has_cwd = "context.cwd" in func_source
            has_python = "sys.version" in func_source

            result.checks.append(CheckResult("timestamp_time", has_time, "time format OK" if has_time else "time format missing"))
            result.checks.append(CheckResult("timestamp_cwd", has_cwd, "cwd OK" if has_cwd else "cwd missing"))
            result.checks.append(CheckResult("timestamp_python", has_python, "python version OK" if has_python else "python version missing"))

            # Check 3: registration
            has_register = "register_command" in source and "timestamp" in source
            result.checks.append(CheckResult("registration", has_register, "registered" if has_register else "not registered"))

            has_aliases = '"ts"' in source or "'ts'" in source
            result.checks.append(CheckResult("aliases", has_aliases, "alias 'ts' OK" if has_aliases else "alias 'ts' missing"))

        # Check 4: __init__.py imports timestamp_cmd
        init_source = self._read_file("src/pilotcode/commands/__init__.py")
        has_import = "timestamp_cmd" in init_source
        result.checks.append(CheckResult(
            "init_import", has_import,
            "timestamp_cmd imported in __init__.py" if has_import else "timestamp_cmd NOT imported"
        ))

        # Check 5: status_cmd.py has Last Check
        status_source = self._read_file("src/pilotcode/commands/status_cmd.py")
        has_last_check = "Last Check" in status_source
        result.checks.append(CheckResult(
            "last_check", has_last_check,
            "'Last Check' in status_cmd" if has_last_check else "'Last Check' missing in status_cmd"
        ))

        result.passed = all(c.passed for c in result.checks)
        return result


TASK_VERIFIERS: dict[int, Callable[[Path], TaskResult]] = {
    2: lambda root: Task2Verifier(root).verify(),
    3: lambda root: Task3Verifier(root).verify(),
    4: lambda root: Task4Verifier(root).verify(),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify E2E task modifications")
    parser.add_argument("--task", type=int, choices=[2, 3, 4], help="Verify specific task only")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--root", type=Path, default=Path("."), help="Project root directory")
    args = parser.parse_args()

    tasks = [args.task] if args.task else [2, 3, 4]
    results: list[TaskResult] = []

    for task_num in tasks:
        verifier = TASK_VERIFIERS[task_num]
        results.append(verifier(args.root))

    if args.json:
        output = []
        for r in results:
            output.append({
                "task": r.task_name,
                "passed": r.passed,
                "checks": [{"name": c.name, "passed": c.passed, "message": c.message} for c in r.checks],
            })
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        all_passed = True
        for r in results:
            print(f"\n{r.summary}")
            for c in r.checks:
                icon = "  ✓" if c.passed else "  ✗"
                print(f"{icon} {c.name}: {c.message}")
            if not r.passed:
                all_passed = False

        print(f"\n{'=' * 40}")
        if all_passed:
            print("All tasks PASSED")
        else:
            print("Some tasks FAILED")

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
