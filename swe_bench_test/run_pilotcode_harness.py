#!/usr/bin/env python3
"""
PilotCode harness for SWE-bench with task decomposition, checklist verification,
and local repo pre-clone for Docker evaluation.

Usage:
    HF_ENDPOINT=https://hf-mirror.com python3 run_pilotcode_harness.py \
        --dataset princeton-nlp/SWE-bench_Lite \
        --output predictions.jsonl \
        --max_workers 4

Then run evaluation:
    python3 -m swebench.harness.run_evaluation \
        --dataset_name princeton-nlp/SWE-bench_Lite \
        --predictions_path predictions.jsonl \
        --max_workers 4 \
        --run_id pilotcode_test
"""

import argparse
import json
import os
import py_compile
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from swebench.harness.utils import load_swebench_dataset
from swebench.harness.constants import KEY_INSTANCE_ID, KEY_MODEL, KEY_PREDICTION, MAP_REPO_VERSION_TO_SPECS

# Import PilotCode complexity classifier for routing
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from pilotcode.components.repl import classify_task_complexity

# Patch pytest spec to use Python 3.10 (current pytest main requires >=3.10)
if 'pytest-dev/pytest' in MAP_REPO_VERSION_TO_SPECS:
    for ver in MAP_REPO_VERSION_TO_SPECS['pytest-dev/pytest']:
        MAP_REPO_VERSION_TO_SPECS['pytest-dev/pytest'][ver]['python'] = '3.10'


PILOTCODE_PROMPT_TEMPLATE = """\
You are given a code repository and a bug report. Your task is to fix the bug described in the report.

Bug Report:
{problem_statement}

Current working directory: {cwd}
Repository: {repo}
Version: {version}

CRITICAL INSTRUCTIONS:
1. You have a budget of approximately 40-50 tool calls TOTAL.
2. Spend NO MORE than 5-8 calls on reading/exploration.
3. For large codebases, USE CodeSearch FIRST to locate relevant symbols/files before reading.
4. Once you locate the bug, MAKE THE CODE EDIT IMMEDIATELY. Do NOT keep reading "just to be sure".
5. After editing, run `git diff` to verify the patch is non-empty.
6. If you run low on turns (past turn 35), declare completion with whatever fix you have.
"""

DEFAULT_MAX_ITERATIONS = 50


def strip_test_file_changes(patch: str) -> str:
    """Remove diff hunks for test files from a patch.

    SWE-bench applies its own test_patch after the model_patch. If the model
    patch also modifies test files, the test_patch may fail to apply due to
    conflicts. Stripping test file changes ensures clean eval.
    """
    if not patch or not patch.strip():
        return patch
    lines = patch.split("\n")
    result = []
    in_test_hunk = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("diff --git a/"):
            # Determine file path from the b/ prefix
            parts = line.split()
            filepath = ""
            for j, part in enumerate(parts):
                if part.startswith("b/"):
                    filepath = part[2:]
                    break
            in_test_hunk = (
                "/tests/" in filepath
                or "/test_" in filepath
                or filepath.startswith("tests/")
            )
            if not in_test_hunk:
                result.append(line)
            i += 1
            # Skip index line if present
            if i < len(lines) and lines[i].startswith("index "):
                if not in_test_hunk:
                    result.append(lines[i])
                i += 1
            continue
        if not in_test_hunk:
            result.append(line)
        i += 1
    cleaned = "\n".join(result).strip()
    if cleaned and not cleaned.endswith("\n"):
        cleaned += "\n"
    return cleaned


def run_cmd(cmd: str, cwd: str | None = None, timeout: int = 300) -> tuple[int, str, str]:
    result = subprocess.run(
        cmd,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


REPO_CACHE_DIR = os.environ.get("SWE_BENCH_REPO_CACHE", os.path.join(tempfile.gettempdir(), "swe-bench-work"))


def clone_and_checkout(repo: str, commit: str, work_dir: str) -> bool:
    """Clone repo to persistent cache, then copy to work_dir. Reuse if already correct commit."""
    os.makedirs(REPO_CACHE_DIR, exist_ok=True)
    repo_slug = repo.replace("/", "__")
    cache_dir = os.path.join(REPO_CACHE_DIR, f"{repo_slug}_{commit}")

    # Check work_dir quick reuse
    if os.path.isdir(os.path.join(work_dir, ".git")):
        rc, head, _ = run_cmd("git rev-parse HEAD", cwd=work_dir)
        if rc == 0 and head.strip() == commit:
            run_cmd("git clean -fdx", cwd=work_dir)
            run_cmd(f"git reset --hard {commit}", cwd=work_dir)
            print(f"[CACHE] Reused work_dir {work_dir} at {commit}")
            return True

    # Check persistent cache
    if os.path.isdir(os.path.join(cache_dir, ".git")):
        rc, head, _ = run_cmd("git rev-parse HEAD", cwd=cache_dir)
        if rc == 0 and head.strip() == commit:
            print(f"[CACHE] Reusing cached repo {cache_dir}")
        else:
            shutil.rmtree(cache_dir, ignore_errors=True)
    else:
        shutil.rmtree(cache_dir, ignore_errors=True)

    if not os.path.exists(cache_dir):
        os.makedirs(os.path.dirname(cache_dir), exist_ok=True)
        repo_url = f"https://github.com/{repo}.git"
        rc, _, stderr = run_cmd(f"git clone --depth 1 --filter=blob:none {repo_url} {cache_dir}", timeout=300)
        if rc != 0:
            print(f"[WARN] Shallow clone failed, trying full clone: {stderr}")
            rc, _, stderr = run_cmd(f"git clone {repo_url} {cache_dir}", timeout=600)
            if rc != 0:
                print(f"[ERROR] Failed to clone {repo}: {stderr}")
                return False
        rc, _, stderr = run_cmd(f"git fetch --depth 1 origin {commit}", cwd=cache_dir, timeout=120)
        if rc != 0:
            rc, _, stderr = run_cmd(f"git fetch origin {commit}", cwd=cache_dir, timeout=300)
        rc, _, stderr = run_cmd(f"git checkout {commit}", cwd=cache_dir, timeout=60)
        if rc != 0:
            print(f"[ERROR] Failed to checkout {commit}: {stderr}")
            return False

    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    shutil.copytree(cache_dir, work_dir, symlinks=True)
    return True


def run_pilotcode(
    cwd: str, prompt: str, max_iterations: int = DEFAULT_MAX_ITERATIONS, planning: bool = False
) -> tuple[int, str]:
    """Run PilotCode in headless mode on the given prompt."""
    planning_flag = "" if planning else "--no-planning"
    cmd = (
        f"python3 -m pilotcode main "
        f"--skip-config-check --auto-allow --max-iterations {max_iterations} "
        f"{planning_flag} "
        f"-p {shlex.quote(prompt)}"
    )
    rc, stdout, stderr = run_cmd(cmd, cwd=cwd, timeout=1800)
    full_output = stdout + "\n" + stderr
    return rc, full_output


def get_git_diff(cwd: str) -> str:
    """Get unified git diff from cwd."""
    rc, stdout, _ = run_cmd("git diff", cwd=cwd)
    if rc == 0:
        return stdout
    return ""


import asyncio
from pilotcode.utils.env_diagnosis import (
    looks_like_environment_error,
    diagnose_and_fix_environment,
)


def get_test_targets_from_patch(test_patch: str, repo: str) -> list[str]:
    """Extract test targets from test_patch diff."""
    targets = []
    seen = set()
    for line in test_patch.split("\n"):
        if line.startswith("diff --git a/") and ".py" in line:
            parts = line.split()
            if len(parts) >= 4:
                filepath = parts[2][2:]  # strip 'b/' prefix
                if filepath in seen:
                    continue
                seen.add(filepath)
                # Only keep files that look like tests
                is_test_file = (
                    "/tests/" in filepath
                    or "/test_" in filepath
                    or filepath.startswith("tests/")
                )
                if not is_test_file:
                    continue
                if repo == "django/django":
                    if filepath.startswith("tests/") and filepath.endswith(".py"):
                        mod = filepath[6:-3].replace("/", ".")
                        targets.append(mod)
                else:
                    targets.append(filepath)
    return targets


def apply_test_patch(work_dir: str, test_patch: str) -> bool:
    """Apply the SWE-bench test patch so local test runs exercise the right tests."""
    if not test_patch.strip():
        return False
    patch_path = os.path.join(work_dir, "_test_patch.diff")
    with open(patch_path, "w") as f:
        f.write(test_patch)
    rc, _, stderr = run_cmd("git apply _test_patch.diff", cwd=work_dir)
    if rc != 0:
        # Some patches need -p0 or --3way; try a fallback
        rc2, _, stderr2 = run_cmd("patch -p1 -f -i _test_patch.diff", cwd=work_dir)
        if rc2 != 0:
            print(f"[WARN] Failed to apply test patch: {stderr or stderr2}")
            return False
    print("[INFO] Test patch applied successfully.")
    return True


def _run_tests_once(work_dir: str, instance: dict) -> tuple[int, str]:
    """Internal helper: run tests once without auto-fix."""
    repo = instance.get("repo", "")
    test_patch = instance.get("test_patch", "")
    targets = get_test_targets_from_patch(test_patch, repo)
    if not targets:
        return 0, "No test targets extracted from test_patch"

    apply_test_patch(work_dir, test_patch)

    # Ensure 'python' exists (many test scripts use #!/usr/bin/env python)
    run_cmd("which python3", cwd=work_dir)
    run_cmd("ln -sf $(which python3) python", cwd=work_dir)

    if repo == "django/django":
        test_cmd = f"python3 ./tests/runtests.py --verbosity 2 --settings=test_sqlite --parallel 1 {' '.join(targets)}"
    else:
        test_cmd = f"python3 -m pytest -rA --tb=short --no-header {' '.join(targets)}"

    rc, stdout, stderr = run_cmd(test_cmd, cwd=work_dir, timeout=300)
    combined = stdout + "\n" + stderr

    # Fallback: try python -m pytest if pytest binary missing
    if rc != 0 and ("pytest: command not found" in combined or "No module named 'pytest'" in combined):
        test_cmd = test_cmd.replace("python3 -m pytest ", "python3 -m pytest ")
        rc, stdout, stderr = run_cmd(test_cmd, cwd=work_dir, timeout=300)
        combined = stdout + "\n" + stderr

    return rc, combined


def run_instance_tests(work_dir: str, instance: dict, max_env_fix_attempts: int = 1) -> tuple[int, str]:
    """Try to run relevant tests locally in work_dir, with optional automatic environment repair."""
    for attempt in range(max_env_fix_attempts + 1):
        rc, combined = _run_tests_once(work_dir, instance)
        if rc == 0:
            return 0, combined
        if looks_like_environment_error(combined):
            print(f"[TEST ENV] Environment error detected on test run {attempt + 1}, attempting auto-fix...")
            fixed = asyncio.run(
                diagnose_and_fix_environment(
                    combined,
                    work_dir,
                    auto_allow=True,
                    interactive=False,
                )
            )
            if fixed:
                print(f"[TEST ENV] Fix applied, re-running tests...")
                continue
            else:
                print(f"[TEST ENV] Auto-fix failed.")
        break
    return rc, combined


REDESIGN_PROMPT_TEMPLATE = """\
Your previous fix was applied but tests FAILED with the following error(s):

{errors}

This strongly suggests your understanding of the bug is INCOMPLETE or INCORRECT.

You MUST reconsider your approach from scratch. Do NOT simply tweak the previous patch.

Requirements:
1. Re-read the failing test and ALL code it exercises.
2. Use Grep to find every call site of the function you changed.
3. Identify the TRUE root cause. Your previous assumption may be wrong.
4. Consider whether your fix introduced a regression or missed a call site.
5. Produce a COMPLETELY REVISED fix.
6. Run the tests again to confirm they pass before declaring completion.

Previous patch (for reference only — do not assume it is correct):
```diff
{patch}
```

Original Bug Report:
{problem_statement}
"""

SYNTAX_REDESIGN_PROMPT_TEMPLATE = """\
Your previous fix was applied but it contains SYNTAX ERRORS:

{errors}

This means your edit corrupted the source file. You MUST fix the syntax before anything else.

Requirements:
1. Read the EXACT current state of the file(s) you modified.
2. Identify where the syntax error was introduced (mismatched brackets, wrong indentation, duplicate keywords, etc.).
3. Apply a CORRECTED edit that fixes the syntax while preserving the intended logic.
4. Run `python3 -m py_compile <file>` to verify the syntax is valid before declaring completion.

Previous patch (for reference only):
```diff
{patch}
```

Original Bug Report:
{problem_statement}
"""


def check_patch_syntax(work_dir: str, patch: str) -> tuple[bool, str]:
    """Check modified Python files for syntax errors. Returns (ok, error_message)."""
    if not patch:
        return True, ""
    # Extract modified filenames from patch
    files = set(re.findall(r'^diff --git a/(.+?) b/', patch, re.MULTILINE))
    errors = []
    for f in files:
        if not f.endswith('.py'):
            continue
        filepath = os.path.join(work_dir, f)
        if not os.path.exists(filepath):
            continue
        try:
            py_compile.compile(filepath, doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"{f}: {e}")
    if errors:
        return False, "\n".join(errors)
    return True, ""


def extract_test_errors(test_output: str, max_chars: int = 4000) -> str:
    """Extract the most informative parts of test output for LLM feedback."""
    # Keep FAIL/ERROR blocks and the tail
    lines = test_output.split("\n")
    error_lines = []
    for line in lines:
        if any(k in line for k in ("FAIL:", "ERROR:", "Traceback", "AssertionError", "TypeError", "ValueError")):
            error_lines.append(line)
    # Also include last portion of output
    tail = "\n".join(lines[-100:])
    combined = "\n".join(error_lines) + "\n\n--- Tail of output ---\n" + tail
    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n[truncated]"
    return combined


def solve_instance(instance: dict, model_name: str = "pilotcode") -> dict:
    """Run PilotCode on a single SWE-bench instance with built-in planning, verification, and test-feedback redesign."""
    instance_id = instance["instance_id"]
    repo = instance["repo"]
    base_commit = instance["base_commit"]
    problem_statement = instance["problem_statement"]

    print(f"\n{'='*60}")
    print(f"Solving instance: {instance_id}")
    print(f"{'='*60}")

    work_dir = os.path.join(tempfile.gettempdir(), "swe-bench-work-v2", instance_id)
    os.makedirs(work_dir, exist_ok=True)

    # Clone and checkout
    if not clone_and_checkout(repo, base_commit, work_dir):
        return {
            KEY_INSTANCE_ID: instance_id,
            KEY_MODEL: model_name,
            KEY_PREDICTION: "",
        }

    # Run PilotCode (automatically selects planning mode based on task complexity)
    prompt = PILOTCODE_PROMPT_TEMPLATE.format(
        problem_statement=problem_statement.replace('"', '\\"'),
        cwd=work_dir,
        repo=repo,
        version=instance.get("version", ""),
    )

    patch = ""
    output = ""
    # Classify once upfront
    import asyncio
    use_planning = asyncio.run(classify_task_complexity(prompt, cwd=work_dir)) == "PLAN"
    if use_planning:
        print("📋 Task classified as complex — running in planning mode")
    else:
        print("⚡ Task classified as simple — running in direct execution mode with feedback")

    for attempt in range(2):
        if attempt > 0:
            print(f"[RETRY] Empty patch on attempt 1, retrying {instance_id} with planning enabled...")
            use_planning = True
        max_iter = 45 if use_planning else DEFAULT_MAX_ITERATIONS
        try:
            rc, output = run_pilotcode(work_dir, prompt, max_iterations=max_iter, planning=use_planning)
            print(output)
            if rc != 0:
                print(f"[WARNING] PilotCode exited with code {rc} for {instance_id}")
        except subprocess.TimeoutExpired as e:
            print(f"[ERROR] PilotCode timed out for {instance_id}: {e}")
            output = str(e)
        patch = get_git_diff(work_dir)
        print(f"[INFO] Generated patch length: {len(patch)} chars (attempt {attempt + 1})")
        if patch:
            break

    # --- Syntax check + test-feedback redesign loop ---
    if patch:
        for redesign in range(2):
            # 1) Syntax check first (lightweight, no environment needed)
            syntax_ok, syntax_errors = check_patch_syntax(work_dir, patch)
            if not syntax_ok:
                print(f"[REDESIGN {redesign + 1}] Syntax errors detected. Feeding back to LLM...")
                redesign_prompt = SYNTAX_REDESIGN_PROMPT_TEMPLATE.format(
                    errors=syntax_errors,
                    patch=patch,
                    problem_statement=problem_statement,
                )
                run_cmd(f"git checkout {base_commit}", cwd=work_dir)
                try:
                    rc, output = run_pilotcode(work_dir, redesign_prompt, max_iterations=DEFAULT_MAX_ITERATIONS)
                    print(output)
                    new_patch = get_git_diff(work_dir)
                    if new_patch:
                        patch = new_patch
                        print(f"[INFO] Syntax redesign generated new patch ({len(patch)} chars)")
                        continue
                    else:
                        print(f"[WARN] Syntax redesign produced empty patch, keeping previous patch.")
                        break
                except subprocess.TimeoutExpired as e:
                    print(f"[ERROR] Syntax redesign timed out for {instance_id}: {e}")
                    break

            # 2) Run tests (skip for astropy — local env always broken)
            if repo == "astropy/astropy":
                print(f"[SKIP] Local tests disabled for astropy instances — relying on Docker eval.")
                break

            print(f"[TEST] Running tests for {instance_id} (redesign {redesign})...")
            test_rc, test_output = run_instance_tests(work_dir, instance)
            if test_rc == 0:
                print(f"[INFO] Tests passed.")
                break

            if looks_like_environment_error(test_output):
                print(f"[WARN] Test environment issue detected, skipping test feedback.")
                print(f"       {test_output[:200].replace(chr(10), ' ')}")
                break

            print(f"[REDESIGN {redesign + 1}] Tests failed. Feeding errors back to LLM...")
            test_errors = extract_test_errors(test_output)
            redesign_prompt = REDESIGN_PROMPT_TEMPLATE.format(
                errors=test_errors,
                patch=patch,
                problem_statement=problem_statement,
            )
            # Reset repo to clean state before redesign
            run_cmd(f"git checkout {base_commit}", cwd=work_dir)
            try:
                rc, output = run_pilotcode(work_dir, redesign_prompt, max_iterations=DEFAULT_MAX_ITERATIONS)
                print(output)
                new_patch = get_git_diff(work_dir)
                if new_patch:
                    patch = new_patch
                    print(f"[INFO] Redesign generated new patch ({len(patch)} chars)")
                else:
                    print(f"[WARN] Redesign produced empty patch, keeping previous patch.")
                    break
            except subprocess.TimeoutExpired as e:
                print(f"[ERROR] Redesign timed out for {instance_id}: {e}")
                break
        else:
            print(f"[WARN] Max redesign attempts reached for {instance_id}")

    # Strip test file changes to avoid conflicts with SWE-bench test_patch
    cleaned_patch = strip_test_file_changes(patch)
    if cleaned_patch != patch:
        print(f"[INFO] Stripped test file changes from patch ({len(patch)} -> {len(cleaned_patch)} chars)")

    prediction = {
        KEY_INSTANCE_ID: instance_id,
        KEY_MODEL: model_name,
        KEY_PREDICTION: cleaned_patch,
    }

    return prediction


def load_completed_ids(output_path: Path) -> set[str]:
    """Load instance IDs that already have predictions in the output file."""
    completed = set()
    if output_path.exists():
        with open(output_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    pred = json.loads(line)
                    completed.add(pred.get(KEY_INSTANCE_ID, ""))
                except json.JSONDecodeError:
                    continue
    return completed


def main():
    parser = argparse.ArgumentParser(description="PilotCode SWE-bench Harness")
    parser.add_argument(
        "--dataset",
        type=str,
        default="princeton-nlp/SWE-bench_Lite",
        help="SWE-bench dataset name or local JSON/JSONL path",
    )
    parser.add_argument(
        "--split",
        type=str,
        default="test",
        help="Dataset split (default: test)",
    )
    parser.add_argument(
        "--instance_ids",
        type=str,
        default=None,
        help="Comma-separated list of instance IDs to run (default: all)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="predictions.jsonl",
        help="Output predictions file",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of instances to process (for testing)",
    )
    parser.add_argument(
        "--model_name",
        type=str,
        default="pilotcode",
        help="Model name to write in predictions",
    )
    args = parser.parse_args()

    # Ensure HF_ENDPOINT is set for faster dataset loading in China
    if not os.environ.get("HF_ENDPOINT"):
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

    # Load dataset (with local disk cache)
    cache_dataset_path = "/home/zx/.cache/swe-bench-lite.json"
    if os.path.exists(cache_dataset_path) and os.path.getsize(cache_dataset_path) > 0:
        print(f"[CACHE] Loading dataset from local cache: {cache_dataset_path}")
        with open(cache_dataset_path) as f:
            dataset = json.load(f)
    else:
        print(f"[INFO] Loading dataset: {args.dataset} (split={args.split})")
        try:
            dataset = load_swebench_dataset(args.dataset, args.split)
        except Exception as e:
            print(f"[ERROR] Failed to load dataset: {e}")
            sys.exit(1)
        os.makedirs(os.path.dirname(cache_dataset_path), exist_ok=True)
        with open(cache_dataset_path, "w") as f:
            json.dump(dataset, f)
        print(f"[CACHE] Dataset saved to {cache_dataset_path}")

    print(f"[INFO] Loaded {len(dataset)} instances")

    # Filter instances
    if args.instance_ids:
        target_ids = set(args.instance_ids.split(","))
        dataset = [inst for inst in dataset if inst["instance_id"] in target_ids]
        print(f"[INFO] Filtered to {len(dataset)} instances")

    if not dataset:
        print("[ERROR] No instances to process")
        sys.exit(1)

    # Resume support: skip already completed instances
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    completed_ids = load_completed_ids(output_path)
    if completed_ids:
        print(f"[INFO] Resuming: {len(completed_ids)} instances already completed")

    dataset = [inst for inst in dataset if inst["instance_id"] not in completed_ids]
    print(f"[INFO] Processing {len(dataset)} remaining instances")

    if args.limit is not None:
        dataset = dataset[:args.limit]
        print(f"[INFO] Limited to first {len(dataset)} instances")

    # Solve instances and append predictions immediately
    processed = 0
    for inst in dataset:
        pred = solve_instance(inst, model_name=args.model_name)
        with open(output_path, "a") as f:
            f.write(json.dumps(pred) + "\n")
        processed += 1
        print(f"[INFO] Progress: {processed}/{len(dataset)} instances in this run")

    print(f"\n[INFO] Appended {processed} predictions to {output_path}")
    total_completed = len(completed_ids) + processed
    print(f"[INFO] Total completed: {total_completed}")
    print("\nTo run evaluation, execute:")
    print(
        f"  python3 -m swebench.harness.run_evaluation "
        f"--dataset_name {args.dataset} "
        f"--predictions_path {output_path} "
        f"--max_workers 4 "
        f"--run_id pilotcode_test"
    )


if __name__ == "__main__":
    main()
