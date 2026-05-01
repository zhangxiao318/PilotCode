#!/usr/bin/env python3
import json, subprocess, sys, time
from datetime import datetime
from pathlib import Path

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


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def run_harness():
    ids_str = ",".join(INSTANCE_IDS)
    cmd = (
        f"python3 run_pilotcode_harness.py "
        f"--instance_ids {ids_str} "
        f"--output predictions_all_v5.jsonl "
        f"--model_name pilotcode_v5"
    )
    log(f"Starting harness: {cmd}")
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd="/home/zx/mycc/PilotCode/swe_bench_test",
    )
    log(f"Harness done, rc={result.returncode}")
    if result.returncode != 0:
        log(f"STDERR: {result.stderr[:500]}")
    return result.returncode == 0


def run_eval():
    cmd = (
        "python3 -m swebench.harness.run_evaluation "
        "--dataset_name /home/zx/.cache/swe-bench-lite.json "
        "--predictions_path predictions_all_v5.jsonl "
        "--max_workers 3 "
        "--run_id pilotcode_v5_eval "
        "--timeout 1800"
    )
    log(f"Starting eval: {cmd}")
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd="/home/zx/mycc/PilotCode/swe_bench_test",
    )
    log(f"Eval done, rc={result.returncode}")
    return result.returncode == 0


def summarize():
    preds = {}
    if Path("predictions_all_v5.jsonl").exists():
        with open("predictions_all_v5.jsonl") as f:
            for line in f:
                d = json.loads(line)
                preds[d["instance_id"]] = d

    report_dir = Path("logs/run_evaluation/pilotcode_v5_eval/pilotcode")
    resolved = 0
    failed = 0
    evaluated = 0
    for inst_id in INSTANCE_IDS:
        rf = report_dir / inst_id / "report.json"
        if rf.exists():
            evaluated += 1
            with open(rf) as f:
                report = json.load(f)
            if report.get(inst_id, {}).get("resolved"):
                resolved += 1
            else:
                failed += 1

    log(f"=" * 60)
    log(f"V5 SUMMARY: {resolved}/{len(INSTANCE_IDS)} resolved ({resolved/len(INSTANCE_IDS):.1%})")
    log(f"Evaluated: {evaluated}, Failed: {failed}, No report: {len(INSTANCE_IDS)-evaluated}")
    log(f"=" * 60)

    with open("evaluation_summary_v5.json", "w") as f:
        json.dump(
            {
                "resolved": resolved,
                "total": len(INSTANCE_IDS),
                "rate": resolved / len(INSTANCE_IDS),
            },
            f,
        )


if __name__ == "__main__":
    log("=" * 60)
    log("V5 FULL PIPELINE START")
    log("=" * 60)

    if run_harness():
        run_eval()
    summarize()

    log("PIPELINE COMPLETE")
