#!/usr/bin/env python3
"""Generic E2E task verification script.

Reads verification rules from YAML files alongside task descriptions:
    tests/e2e/tasks/task<N>_verify.yaml

Usage:
    python verify_tasks.py              # Verify all tasks with verify configs
    python verify_tasks.py --task 2     # Verify only task 2
    python verify_tasks.py --json       # Output JSON for CI integration
"""

from __future__ import annotations

import argparse
import ast
import json
import py_compile
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Force UTF-8 output on Windows to avoid encoding errors when printing
# check results that contain Unicode characters (e.g. warning symbols).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str = ""


@dataclass
class TaskResult:
    task_name: str
    description: str
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)


class GenericVerifier:
    """Generic verifier that reads rules from YAML and executes them."""

    def __init__(self, project_root: Path):
        self.root = project_root

    def _read_file(self, rel_path: str) -> str:
        path = self.root / rel_path
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _resolve_file(self, rel_path: str) -> Path:
        return self.root / rel_path

    def _ast_parse(self, rel_path: str) -> ast.AST | None:
        source = self._read_file(rel_path)
        if not source:
            return None
        try:
            return ast.parse(source)
        except SyntaxError:
            return None

    def _find_function(self, tree: ast.AST, name: str) -> ast.AST | None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return node
        return None

    def run_check(self, check: dict[str, Any]) -> CheckResult:
        check_type = check.get("type", "")
        name = check.get("name", "unknown")
        rel_file = check.get("file", "")
        file_path = self._resolve_file(rel_file)

        # ---- syntax check ----
        if check_type == "syntax":
            if not file_path.exists():
                return CheckResult(name, False, f"{rel_file} not found")
            try:
                py_compile.compile(str(file_path), doraise=True)
                return CheckResult(name, True, f"{rel_file} compiles OK")
            except py_compile.PyCompileError as e:
                return CheckResult(name, False, f"{rel_file} syntax error: {e}")

        # ---- file_exists check ----
        if check_type == "file_exists":
            exists = file_path.exists()
            return CheckResult(
                name, exists, f"{rel_file} exists" if exists else f"{rel_file} missing"
            )

        # ---- contains check ----
        if check_type == "contains":
            if not file_path.exists():
                return CheckResult(name, False, f"{rel_file} not found")
            source = self._read_file(rel_file)
            pattern = check.get("pattern", "")
            found = pattern in source
            return CheckResult(
                name, found, f"found '{pattern}'" if found else f"missing '{pattern}'"
            )

        # ---- function_exists check ----
        if check_type == "function_exists":
            if not file_path.exists():
                return CheckResult(name, False, f"{rel_file} not found")
            tree = self._ast_parse(rel_file)
            func_name = check.get("function", "")
            func = self._find_function(tree, func_name) if tree else None
            found = func is not None
            return CheckResult(
                name, found, f"{func_name}() defined" if found else f"{func_name}() missing"
            )

        # ---- function_contains check ----
        if check_type == "function_contains":
            if not file_path.exists():
                return CheckResult(name, False, f"{rel_file} not found")
            source = self._read_file(rel_file)
            tree = self._ast_parse(rel_file)
            func_name = check.get("function", "")
            pattern = check.get("pattern", "")
            func = self._find_function(tree, func_name) if tree else None
            if func is None:
                return CheckResult(name, False, f"{func_name}() not found")
            func_lines = source.splitlines()[func.lineno - 1:func.end_lineno]
            func_source = "\n".join(func_lines)
            found = pattern in func_source
            return CheckResult(
                name,
                found,
                (
                    f"{func_name}() contains '{pattern}'"
                    if found
                    else f"{func_name}() missing '{pattern}'"
                ),
            )

        # ---- max_functions check ----
        if check_type == "max_functions":
            if not file_path.exists():
                return CheckResult(name, False, f"{rel_file} not found")
            tree = self._ast_parse(rel_file)
            func_count = (
                sum(1 for node in ast.walk(tree) if isinstance(node, ast.FunctionDef))
                if tree
                else 0
            )
            max_count = check.get("max_count", 999)
            ok = func_count <= max_count
            return CheckResult(
                name,
                ok,
                (
                    f"{func_count} functions (max {max_count})"
                    if ok
                    else f"{func_count} functions (exceeds max {max_count})"
                ),
            )

        return CheckResult(name, False, f"unknown check type: {check_type}")

    def verify(self, config_path: Path) -> TaskResult:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        task_name = config.get("task_name", config_path.stem)
        description = config.get("description", "")
        checks_config = config.get("checks", [])

        result = TaskResult(task_name, description, passed=False)
        for check_cfg in checks_config:
            result.checks.append(self.run_check(check_cfg))

        result.passed = all(c.passed for c in result.checks)
        return result


def discover_configs(tasks_dir: Path) -> list[Path]:
    """Discover all *_verify.yaml files in tasks directory."""
    return sorted(tasks_dir.glob("*_verify.yaml"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generic E2E task verification")
    parser.add_argument("--task", type=int, help="Verify specific task only")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--root", type=Path, default=Path("."), help="Project root")
    args = parser.parse_args()

    tasks_dir = args.root / "tests" / "e2e" / "tasks"
    configs = discover_configs(tasks_dir)

    if args.task:
        target = tasks_dir / f"task{args.task}_verify.yaml"
        configs = [c for c in configs if c.name == target.name]
        if not configs:
            print(f"No verify config found for task {args.task}")
            return 1

    verifier = GenericVerifier(args.root)
    results: list[TaskResult] = []
    for config in configs:
        results.append(verifier.verify(config))

    if args.json:
        output = []
        for r in results:
            output.append(
                {
                    "task": r.task_name,
                    "description": r.description,
                    "passed": r.passed,
                    "checks": [
                        {"name": c.name, "passed": c.passed, "message": c.message} for c in r.checks
                    ],
                }
            )
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        all_passed = True
        for r in results:
            status = "PASS" if r.passed else "FAIL"
            print(f"\n[{status}] {r.task_name}")
            if r.description:
                print(f"      {r.description}")
            for c in r.checks:
                icon = "  [OK]" if c.passed else "  [FAIL]"
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
