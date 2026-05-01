#!/usr/bin/env python3
"""Run full SWE-bench pipeline: generate predictions -> evaluate -> summarize."""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Config
INSTANCE_IDS = [
    "astropy__astropy-14182",
    "astropy__astropy-14365",
    "astropy__astropy-14995",
    "astropy__astropy-7746",
    "astropy__astropy-12907",
    "astropy__astropy-6938",
    "django__django-10914",
    "django__django-10924",
    "django__django-11001",
    "django__django-11019",
    "django__django-11039",
    "django__django-11049",
    "django__django-11099",
    "django__django-11133",
    "django__django-11179",
    "django__django-11283",
    "django__django-11422",
    "django__django-11564",
    "django__django-11583",
    "django__django-11620",
    "django__django-11630",
    "django__django-11742",
    "django__django-11797",
    "django__django-11815",
    "django__django-11848",
]
PREDICTIONS_PATH = "predictions_all_v4.jsonl"
RUN_ID = "pilotcode_v4_eval"
DEADLINE = datetime(2026, 4, 30, 8, 30, 0)  # Tomorrow 08:30


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def run_cmd(cmd, timeout=None, cwd=None):
    log(f"Running: {cmd}")
    start = time.time()
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
        elapsed = time.time() - start
        log(f"Done in {elapsed/60:.1f}min, rc={result.returncode}")
        if result.returncode != 0:
            log(f"STDERR: {result.stderr[:500]}")
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        log(f"TIMEOUT after {timeout/60:.1f}min")
        return -1, "", "timeout"


def minutes_left():
    return (DEADLINE - datetime.now()).total_seconds() / 60


def summarize_results(predictions_path, run_id):
    log("=" * 60)
    log("SUMMARIZING RESULTS")
    log("=" * 60)

    # Load predictions
    preds = {}
    if Path(predictions_path).exists():
        with open(predictions_path) as f:
            for line in f:
                d = json.loads(line)
                preds[d["instance_id"]] = d

    # Check evaluation reports
    report_dir = Path(f"logs/run_evaluation/{run_id}/pilotcode")
    total = len(INSTANCE_IDS)
    evaluated = 0
    resolved = 0
    failed = 0
    no_report = []

    for inst_id in INSTANCE_IDS:
        report_file = report_dir / inst_id.replace("__", "_") / "report.json"
        if report_file.exists():
            evaluated += 1
            with open(report_file) as f:
                report = json.load(f)
            data = report.get(inst_id, {})
            if data.get("resolved"):
                resolved += 1
            else:
                failed += 1
        else:
            no_report.append(inst_id)

    log(f"Total instances: {total}")
    log(f"Predictions generated: {len(preds)}")
    log(f"Evaluated: {evaluated}")
    log(f"Resolved: {resolved}")
    log(f"Failed: {failed}")
    log(f"No report: {len(no_report)}")
    if no_report:
        log(f"Missing: {', '.join(no_report)}")

    # Write summary
    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_instances": total,
        "predictions_generated": len(preds),
        "evaluated": evaluated,
        "resolved": resolved,
        "failed": failed,
        "missing_reports": no_report,
        "resolution_rate": resolved / total if total else 0,
    }
    with open("evaluation_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    log("Summary written to evaluation_summary.json")
    return summary


def main():
    log("=" * 60)
    log("SWE-bench FULL PIPELINE START")
    log(f"Deadline: {DEADLINE.strftime('%Y-%m-%d %H:%M')}")
    log(f"Minutes left: {minutes_left():.0f}")
    log("=" * 60)

    # Phase 1: Generate predictions
    ids_str = ",".join(INSTANCE_IDS)
    harness_cmd = (
        f"python3 run_pilotcode_harness.py "
        f"--instance_ids {ids_str} "
        f"--output {PREDICTIONS_PATH} "
        f"--model_name pilotcode_v4"
    )

    # Run harness with generous timeout (10 hours)
    harness_timeout = min(int(minutes_left() * 60) - 3600, 36000)  # leave 1h for eval
    if harness_timeout < 1800:
        log("NOT ENOUGH TIME. Aborting.")
        sys.exit(1)

    rc, stdout, stderr = run_cmd(
        harness_cmd, timeout=harness_timeout, cwd="/home/zx/mycc/PilotCode/swe_bench_test"
    )

    log(f"Harness finished. Minutes left: {minutes_left():.0f}")

    # Phase 2: Evaluate (if time permits)
    if minutes_left() > 120 and Path(PREDICTIONS_PATH).exists():
        eval_timeout = int(minutes_left() * 60) - 300
        eval_cmd = (
            f"python3 -m swebench.harness.run_evaluation "
            f"--dataset_name /home/zx/.cache/swe-bench-lite.json "
            f"--predictions_path {PREDICTIONS_PATH} "
            f"--max_workers 3 "
            f"--run_id {RUN_ID} "
            f"--timeout 1800"
        )
        rc, stdout, stderr = run_cmd(
            eval_cmd, timeout=eval_timeout, cwd="/home/zx/mycc/PilotCode/swe_bench_test"
        )
    else:
        log("Skipping evaluation (not enough time or no predictions)")

    # Phase 3: Summarize
    summary = summarize_results(PREDICTIONS_PATH, RUN_ID)

    log("=" * 60)
    log("PIPELINE COMPLETE")
    log(
        f"Resolved: {summary['resolved']}/{summary['total_instances']} ({summary['resolution_rate']:.1%})"
    )
    log("=" * 60)


if __name__ == "__main__":
    main()
