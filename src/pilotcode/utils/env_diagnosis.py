"""Environment diagnosis and automatic repair utilities."""

import json
import re
import subprocess
from typing import Callable

ENV_ERROR_SIGNATURES = [
    "ModuleNotFoundError",
    "ImportError",
    "No module named",
    "gcc: error",
    "gcc: command not found",
    "x86_64-linux-gnu-gcc: command not found",
    "Unable to find vcvarsall.bat",
    "error: Microsoft Visual C++",
    "fatal error: ",
    "cannot find -l",
    "ld: library not found",
    "pytest: command not found",
    "python: can't open file",
    "cannot import name",
    "No such file or directory",
    "django-admin: command not found",
    "Could not find a version that satisfies the requirement",
    "PEP 517",
    "Legacy-install-failure",
    "subprocess-exited-with-error",
    "error: command 'gcc' failed",
    "error: command 'x86_64-linux-gnu-gcc' failed",
    "Cython.Compiler.Errors.CompileError",
    "pkg_resources.VersionConflict",
    "AttributeError: module 'pkg_resources'",
]


def looks_like_environment_error(output: str) -> bool:
    """Heuristic to decide whether a failure is caused by the environment."""
    if not output:
        return False
    for sig in ENV_ERROR_SIGNATURES:
        if sig in output:
            return True
    return False


def extract_diagnosis_json(response_text: str) -> dict | None:
    """Extract JSON diagnosis from LLM response."""
    text = response_text.strip()
    # Try markdown code block first
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Try first { ... } pair
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None


async def diagnose_and_fix_environment(
    error_output: str,
    work_dir: str,
    auto_allow: bool = False,
    progress_callback: Callable[[str], None] | None = None,
    interactive: bool = False,
) -> bool:
    """Diagnose an environment error and optionally fix it.

    Args:
        error_output: The stderr/stdout that triggered the diagnosis.
        work_dir: Working directory containing the project.
        auto_allow: Whether to auto-allow tool executions during diagnosis.
        progress_callback: Optional callback for progress messages.
        interactive: If True and requires_user_permission is true, ask the user.

    Returns:
        True if a fix was applied and succeeded, False otherwise.
    """
    # Lazy import to avoid circular dependency
    from pilotcode.components.repl import run_headless, _env_diagnosis_ctx

    diag_prompt = f"""\
An environment or build error occurred while working on the project.

--- Error Output ---
{error_output[:3000]}
--- End Error Output ---

Your task:
1. Read the project's setup/configuration files (e.g., pyproject.toml, setup.py, setup.cfg, requirements.txt, Makefile, tox.ini, .github/workflows) in the workspace.
2. Identify the root cause: missing compiler, missing system library, incompatible Python package version, or missing executable.
3. Propose exactly ONE bash command that can fix it in this environment.

Output ONLY a JSON object with this structure:
{{
  "diagnosis": "One-sentence root cause",
  "fix_command": "Single bash command (or empty if unfixable)",
  "requires_user_permission": true,
  "risk": "Brief risk or side effect"
}}
"""

    if progress_callback:
        progress_callback("[ENV] Diagnosing environment issue...")

    # Mark that we are inside an env-diagnosis session to prevent nested dead loops
    token = _env_diagnosis_ctx.set(True)
    try:
        result = await run_headless(
            diag_prompt,
            auto_allow=auto_allow,
            json_mode=False,
            max_iterations=15,
            cwd=work_dir,
            progress_callback=progress_callback,
            disable_env_diagnosis=True,
        )
    finally:
        _env_diagnosis_ctx.reset(token)

    diagnosis = extract_diagnosis_json(result.get("response", ""))
    if not diagnosis:
        if progress_callback:
            progress_callback("[ENV] Could not parse diagnosis from LLM")
        return False

    cmd = diagnosis.get("fix_command", "").strip()
    if not cmd:
        if progress_callback:
            progress_callback(f"[ENV] No fix command proposed. Diagnosis: {diagnosis.get('diagnosis')}")
        return False

    needs_perm = diagnosis.get("requires_user_permission", True)
    risk = diagnosis.get("risk", "")

    if interactive and needs_perm:
        print("\n" + "=" * 60)
        print("[ENVIRONMENT ISSUE DETECTED]")
        print(f"Diagnosis: {diagnosis.get('diagnosis')}")
        if risk:
            print(f"Risk: {risk}")
        print(f"Proposed fix command: {cmd}")
        print("=" * 60)
        try:
            answer = input("Execute this command? [y/N/a(always allow env fixes)] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer in ("a", "always"):
            # Caller can decide to remember this, but for now we just allow this once
            interactive = False
        elif answer not in ("y", "yes"):
            print("Skipping environment fix.")
            return False
    else:
        if progress_callback:
            progress_callback(f"[ENV] Auto-applying fix: {cmd}")

    proc = subprocess.run(
        cmd,
        shell=True,
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=300,
    )
    success = proc.returncode == 0
    log = (proc.stdout + "\n" + proc.stderr).strip()
    if progress_callback:
        status = "succeeded" if success else "failed"
        preview = log[:500] + ("\n[truncated]" if len(log) > 500 else "")
        progress_callback(f"[ENV] Fix {status}. Output:\n{preview}")
    return success
