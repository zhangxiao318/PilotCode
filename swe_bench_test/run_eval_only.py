#!/usr/bin/env python3
"""Evaluate existing predictions and summarize."""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def run_eval(predictions_path, run_id, max_workers=3, timeout=1800):
    cmd = (
        f"python3 -m swebench.harness.run_evaluation "
        f"--dataset_name /home/zx/.cache/swe-bench-lite.json "
        f"--predictions_path {predictions_path} "
        f"--max_workers {max_workers} "
        f"--run_id {run_id} "
        f"--timeout {timeout}"
    )
    log(f"Running: {cmd}")
    start = time.time()
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd="/home/zx/mycc/PilotCode/swe_bench_test",
    )
    elapsed = time.time() - start
    log(f"Eval done in {elapsed/60:.1f}min, rc={result.returncode}")
    if result.returncode != 0:
        log(f"STDERR: {result.stderr[:800]}")
    return result.returncode == 0


def summarize(predictions_path, run_id, label):
    log(f"=== Summarizing {label} ===")
    preds = {}
    with open(predictions_path) as f:
        for line in f:
            d = json.loads(line)
            preds[d["instance_id"]] = d

    report_dir = Path(f"logs/run_evaluation/{run_id}/pilotcode")
    if not report_dir.exists():
        report_dir = Path(f"logs/run_evaluation/{run_id}/pilotcode_v4")

    total = len(preds)
    evaluated = 0
    resolved = 0
    failed = 0
    empty_patch = 0
    details = []

    for inst_id in preds:
        report_file = report_dir / inst_id.replace("__", "_") / "report.json"
        if report_file.exists():
            evaluated += 1
            with open(report_file) as f:
                report = json.load(f)
            data = report.get(inst_id, {})
            patch_none = data.get("patch_is_None", False)
            patch_exists = data.get("patch_exists", False)
            applied = data.get("patch_successfully_applied", False)
            is_resolved = data.get("resolved", False)

            if is_resolved:
                resolved += 1
            elif patch_none or not patch_exists:
                empty_patch += 1
            else:
                failed += 1

            details.append(
                {
                    "instance_id": inst_id,
                    "resolved": is_resolved,
                    "patch_exists": patch_exists,
                    "patch_applied": applied,
                }
            )
        else:
            details.append(
                {
                    "instance_id": inst_id,
                    "resolved": False,
                    "patch_exists": bool(preds[inst_id].get("model_patch")),
                    "patch_applied": False,
                    "no_report": True,
                }
            )

    summary = {
        "label": label,
        "timestamp": datetime.now().isoformat(),
        "predictions_file": predictions_path,
        "run_id": run_id,
        "total": total,
        "evaluated": evaluated,
        "resolved": resolved,
        "failed": failed,
        "empty_patch": empty_patch,
        "resolution_rate": resolved / total if total else 0,
        "details": details,
    }

    out_path = f"evaluation_summary_{label}.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)

    log(f"  Total: {total}")
    log(f"  Evaluated: {evaluated}")
    log(f"  Resolved: {resolved}")
    log(f"  Failed: {failed}")
    log(f"  Empty patch: {empty_patch}")
    log(f"  Resolution rate: {resolved}/{total} = {summary['resolution_rate']:.1%}")
    log(f"  Summary written to {out_path}")
    return summary


def main():
    log("=" * 60)
    log("EVAL-ONLY PIPELINE START")
    log("=" * 60)

    # Phase 1: Evaluate 5-instance predictions
    log("\n>>> PHASE 1: predictions_5_simple_v3.jsonl")
    ok1 = run_eval("predictions_5_simple_v3.jsonl", "pilotcode_v3_5eval", max_workers=3)
    s1 = summarize("predictions_5_simple_v3.jsonl", "pilotcode_v3_5eval", "5_instances")

    # Phase 2: Evaluate 25-instance predictions
    log("\n>>> PHASE 2: predictions_all.jsonl")
    ok2 = run_eval("predictions_all.jsonl", "pilotcode_all_25eval", max_workers=3)
    s2 = summarize("predictions_all.jsonl", "pilotcode_all_25eval", "25_instances")

    log("\n" + "=" * 60)
    log("ALL EVALUATION COMPLETE")
    log(f"5-instance:  {s1['resolved']}/{s1['total']} = {s1['resolution_rate']:.1%}")
    log(f"25-instance: {s2['resolved']}/{s2['total']} = {s2['resolution_rate']:.1%}")
    log("=" * 60)


if __name__ == "__main__":
    main()
