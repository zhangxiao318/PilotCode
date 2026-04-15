#!/usr/bin/env python3
"""
PilotCode harness for SWE-bench with task decomposition, checklist verification,
and local repo pre-clone for Docker evaluation.

Usage:
    python3 run_pilotcode_harness.py \
        --dataset /path/to/swe-bench-lite-test.json \
        --instance_ids "psf/requests-1234,psf/requests-1235" \
        --output predictions.jsonl \
        --max_workers 1

Then run evaluation:
    python3 -m swebench.harness.run_evaluation \
        --dataset_name /path/to/swe-bench-lite-test.json \
        --predictions_path predictions.jsonl \
        --max_workers 1 \
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
    cwd: str, prompt: str, max_iterations: int = DEFAULT_MAX_ITERATIONS, plan_and_verify: bool = True
) -> tuple[int, str]:
    """Run PilotCode in headless mode on the given prompt."""
    plan_flag = "--plan-and-verify" if plan_and_verify else ""
    cmd = (
        f"python3 -m pilotcode main "
        f"--skip-config-check --auto-allow --max-iterations {max_iterations} "
        f"{plan_flag} "
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


def extract_json_from_output(output: str) -> dict | None:
    """Extract the first JSON object from LLM output."""
    # Try to find JSON block
    match = re.search(r"\{.*\}", output, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def generate_plan(work_dir: str, repo: str, problem_statement: str) -> dict:
    """Step 1: Run PilotCode to generate a structured plan."""
    prompt = PLANNING_PROMPT_TEMPLATE.format(
        problem_statement=problem_statement.replace('"', '\\"'),
        cwd=work_dir,
        repo=repo,
    )
    print("[PLAN] Generating task plan...")
    rc, output = run_pilotcode(work_dir, prompt, max_iterations=20)
    if rc != 0:
        print(f"[WARN] Planning exited with code {rc}")
    plan = extract_json_from_output(output)
    if plan is None:
        print("[WARN] Failed to parse plan JSON, using fallback")
        plan = {
            "files_to_modify": [],
            "reasoning": "Plan could not be generated automatically."
        }
    print(f"[PLAN] {len(plan.get('files_to_modify', []))} files identified")
    for item in plan.get("files_to_modify", []):
        print(f"  - {item.get('file')}: {item.get('change')}")
    return plan


def verify_completion(
    work_dir: str, problem_statement: str, plan: dict, current_diff: str
) -> dict:
    """Step 3: Run PilotCode to verify if the fix is complete."""
    prompt = VERIFICATION_PROMPT_TEMPLATE.format(
        problem_statement=problem_statement.replace('"', '\\"'),
        plan_json=json.dumps(plan, indent=2).replace('"', '\\"'),
        current_diff=current_diff.replace('"', '\\"'),
    )
    print("[VERIFY] Checking completion...")
    rc, output = run_pilotcode(work_dir, prompt, max_iterations=15)
    if rc != 0:
        print(f"[WARN] Verification exited with code {rc}")
    result = extract_json_from_output(output)
    if result is None:
        print("[WARN] Failed to parse verification JSON")
        return {"complete": True, "missing_changes": [], "summary": "Parse failed, assuming complete"}
    print(f"[VERIFY] complete={result.get('complete')}, summary={result.get('summary')}")
    for missing in result.get("missing_changes", []):
        print(f"  - MISSING: {missing.get('file')}: {missing.get('issue')}")
    return result


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

    # Run PilotCode with built-in plan-and-verify
    prompt = PILOTCODE_PROMPT_TEMPLATE.format(
        problem_statement=problem_statement.replace('"', '\\"'),
        cwd=work_dir,
        repo=repo,
        version=instance.get("version", ""),
    )
    rc, output = run_pilotcode(work_dir, prompt, plan_and_verify=True)
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


def preclone_repo_for_docker(repo: str, commit: str, instance_id: str) -> str | None:
    """Pre-clone repo locally so SWE-bench Docker build can COPY instead of git clone."""
    cache_dir = os.path.join(tempfile.gettempdir(), "swe-bench-repo-cache", instance_id)
    if os.path.exists(cache_dir):
        shutil.rmtree(cache_dir)
    os.makedirs(cache_dir, exist_ok=True)

    if not clone_and_checkout(repo, commit, cache_dir):
        return None

    return cache_dir


def patch_swebench_for_local_repo(instance: dict, local_repo_path: str) -> None:
    """Monkey-patch swebench to use local repo path instead of git clone in Docker."""
    import swebench.harness.test_spec.create_scripts as cs
    import swebench.harness.dockerfiles as df
    from swebench.harness.constants import KEY_INSTANCE_ID

    original_repo_script = cs.make_repo_script_list

    def patched_repo_script_list(specs, repo, repo_directory, base_commit, env_name):
        instance_id = f"{repo.replace('/', '__')}-{base_commit[:7]}"
        # Check if we have a local pre-cloned repo for this instance
        # Use the passed local_repo_path directly
        scripts = [
            f"mkdir -p {repo_directory}",
            f"cp -r /local_repo/. {repo_directory}/",
            f"chmod -R 777 {repo_directory}",
            f"cd {repo_directory}",
            f"git reset --hard {base_commit}",
            f"git config --global user.email 'setup@swebench.config'",
            f"git config --global user.name 'SWE-bench'",
            f"git commit --allow-empty -am 'SWE-bench'",
        ]
        return scripts

    cs.make_repo_script_list = patched_repo_script_list

    # Also patch Dockerfile instance to COPY local repo
    original_dockerfile_instance = df.get_dockerfile_instance

    def patched_get_dockerfile_instance(platform, language, env_image_name):
        dockerfile = original_dockerfile_instance(platform, language, env_image_name)
        if language == "py":
            # Inject COPY before setup_repo.sh
            dockerfile = dockerfile.replace(
                "COPY ./setup_repo.sh /root/",
                "COPY ./local_repo /local_repo\nCOPY ./setup_repo.sh /root/"
            )
        return dockerfile

    df.get_dockerfile_instance = patched_get_dockerfile_instance


def build_local_prediction_bundle(instance: dict, prediction: dict, local_repo_path: str) -> str:
    """Build a local directory with prediction and repo for evaluation."""
    bundle_dir = os.path.join(tempfile.gettempdir(), "swe-bench-bundles", instance["instance_id"])
    if os.path.exists(bundle_dir):
        shutil.rmtree(bundle_dir)
    os.makedirs(bundle_dir, exist_ok=True)

    # Write prediction
    pred_path = os.path.join(bundle_dir, "prediction.jsonl")
    with open(pred_path, "w") as f:
        f.write(json.dumps(prediction) + "\n")

    # Copy repo
    repo_dest = os.path.join(bundle_dir, "local_repo")
    shutil.copytree(local_repo_path, repo_dest)

    return bundle_dir


def run_local_evaluation(dataset_path: str, bundle_dir: str, run_id: str) -> None:
    """Run SWE-bench evaluation using the local repo bundle."""
    import docker
    from swebench.harness.run_evaluation import main as eval_main

    pred_path = os.path.join(bundle_dir, "prediction.jsonl")
    local_repo = os.path.join(bundle_dir, "local_repo")

    # Patch swebench docker build
    patch_swebench_for_local_repo({}, local_repo)

    print(f"\n[EVAL] Running evaluation with local repo copy...")
    eval_main(
        dataset_name=dataset_path,
        split="test",
        instance_ids=[],
        predictions_path=pred_path,
        max_workers=1,
        force_rebuild=True,
        cache_level="env",
        clean=False,
        open_file_limit=4096,
        run_id=run_id,
        timeout=1800,
        namespace=None,
        rewrite_reports=False,
        modal=False,
    )


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
        "--max_workers",
        type=int,
        default=1,
        help="Maximum parallel workers (default: 1)",
    )
    parser.add_argument(
        "--model_name",
        type=str,
        default="pilotcode",
        help="Model name to write in predictions",
    )
    parser.add_argument(
        "--run_eval",
        action="store_true",
        help="Also run SWE-bench evaluation locally after generating predictions",
    )
    args = parser.parse_args()

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

    # Solve instances
    predictions = []
    for inst in dataset:
        pred = solve_instance(inst, model_name=args.model_name)
        predictions.append(pred)

        # Optionally pre-clone for evaluation
        if args.run_eval:
            local_repo = preclone_repo_for_docker(
                inst["repo"], inst["base_commit"], inst["instance_id"]
            )
            if local_repo:
                bundle_dir = build_local_prediction_bundle(inst, pred, local_repo)
                run_local_evaluation(args.dataset, bundle_dir, f"pilotcode_{inst['instance_id']}")

    # Write predictions
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for pred in predictions:
            f.write(json.dumps(pred) + "\n")

    print(f"\n[INFO] Wrote {len(predictions)} predictions to {output_path}")
    if not args.run_eval:
        print("\nTo run evaluation, execute:")
        print(
            f"  python3 -m swebench.harness.run_evaluation "
            f"--dataset_name {args.dataset} "
            f"--predictions_path {output_path} "
            f"--max_workers {args.max_workers} "
            f"--run_id pilotcode_test"
        )


if __name__ == "__main__":
    main()
