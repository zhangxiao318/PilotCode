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
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from swebench.harness.utils import load_swebench_dataset
from swebench.harness.constants import KEY_INSTANCE_ID, KEY_MODEL, KEY_PREDICTION, MAP_REPO_VERSION_TO_SPECS

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
"""

DEFAULT_MAX_ITERATIONS = 30


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


def clone_and_checkout(repo: str, commit: str, work_dir: str) -> bool:
    """Clone repo and checkout to specific commit using shallow clone for speed."""
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir, exist_ok=True)

    repo_url = f"https://github.com/{repo}.git"
    # Try shallow clone first to save time and bandwidth
    rc, _, stderr = run_cmd(f"git clone --depth 1 --filter=blob:none {repo_url} {work_dir}", timeout=300)
    if rc != 0:
        print(f"[WARN] Shallow clone failed, trying full clone: {stderr}")
        rc, _, stderr = run_cmd(f"git clone {repo_url} {work_dir}", timeout=600)
        if rc != 0:
            print(f"[ERROR] Failed to clone {repo}: {stderr}")
            return False

    # Fetch the specific commit with minimal history
    rc, _, stderr = run_cmd(f"git fetch --depth 1 origin {commit}", cwd=work_dir, timeout=120)
    if rc != 0:
        print(f"[WARN] Shallow fetch failed, trying full fetch: {stderr}")
        rc, _, stderr = run_cmd(f"git fetch origin {commit}", cwd=work_dir, timeout=300)
        if rc != 0:
            print(f"[ERROR] Failed to fetch commit {commit}: {stderr}")
            return False

    rc, _, stderr = run_cmd(f"git checkout {commit}", cwd=work_dir, timeout=60)
    if rc != 0:
        print(f"[ERROR] Failed to checkout {commit}: {stderr}")
        return False

    return True


def run_pilotcode(
    cwd: str, prompt: str, max_iterations: int = DEFAULT_MAX_ITERATIONS
) -> tuple[int, str]:
    """Run PilotCode in headless mode on the given prompt."""
    cmd = (
        f"python3 -m pilotcode main "
        f"--skip-config-check --auto-allow --max-iterations {max_iterations} "
        f"-p {shlex.quote(prompt)}"
    )
    rc, stdout, stderr = run_cmd(cmd, cwd=cwd, timeout=900)
    full_output = stdout + "\n" + stderr
    return rc, full_output


def get_git_diff(cwd: str) -> str:
    """Get unified git diff from cwd."""
    rc, stdout, _ = run_cmd("git diff", cwd=cwd)
    if rc == 0:
        return stdout
    return ""


def solve_instance(instance: dict, model_name: str = "pilotcode") -> dict:
    """Run PilotCode on a single SWE-bench instance with built-in planning and verification."""
    instance_id = instance["instance_id"]
    repo = instance["repo"]
    base_commit = instance["base_commit"]
    problem_statement = instance["problem_statement"]

    print(f"\n{'='*60}")
    print(f"Solving instance: {instance_id}")
    print(f"{'='*60}")

    work_dir = os.path.join(tempfile.gettempdir(), "swe-bench-work", instance_id)
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
    rc, output = run_pilotcode(work_dir, prompt)
    print(output)
    if rc != 0:
        print(f"[WARNING] PilotCode exited with code {rc} for {instance_id}")

    patch = get_git_diff(work_dir)
    print(f"[INFO] Generated patch length: {len(patch)} chars")

    prediction = {
        KEY_INSTANCE_ID: instance_id,
        KEY_MODEL: model_name,
        KEY_PREDICTION: patch,
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

    # Load dataset
    print(f"[INFO] Loading dataset: {args.dataset} (split={args.split})")
    try:
        dataset = load_swebench_dataset(args.dataset, args.split)
    except Exception as e:
        print(f"[ERROR] Failed to load dataset: {e}")
        sys.exit(1)

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
