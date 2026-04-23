#!/usr/bin/env python3
"""Run SWE-bench evaluation with local dataset cache."""
import sys
import os

sys.stdout.reconfigure(line_buffering=True)

print("[DEBUG] Importing...", flush=True)
from swebench.harness.run_evaluation import main
from swebench.harness.utils import load_swebench_dataset, get_predictions_from_file
from swebench.harness.constants import KEY_INSTANCE_ID, MAP_REPO_VERSION_TO_SPECS

# Patch pytest spec to use Python 3.10
if "pytest-dev/pytest" in MAP_REPO_VERSION_TO_SPECS:
    for ver in MAP_REPO_VERSION_TO_SPECS["pytest-dev/pytest"]:
        MAP_REPO_VERSION_TO_SPECS["pytest-dev/pytest"][ver]["python"] = "3.10"

print("[DEBUG] Loading dataset...", flush=True)
dataset = load_swebench_dataset("/home/zx/.cache/swe-bench-lite.json", "test")
print(f"[DEBUG] Dataset loaded: {len(dataset)} instances", flush=True)

print("[DEBUG] Loading predictions...", flush=True)
predictions = get_predictions_from_file(
    "/home/zx/mycc/PilotCode/swe_bench_test/predictions_merged.jsonl",
    "/home/zx/.cache/swe-bench-lite.json",
    "test",
)
print(f"[DEBUG] Predictions loaded: {len(predictions)}", flush=True)

pred_map = {pred[KEY_INSTANCE_ID]: pred for pred in predictions}
instance_ids = list(pred_map.keys())
print(f"[DEBUG] Instance IDs: {instance_ids}", flush=True)

print("[DEBUG] Calling main()...", flush=True)
main(
    dataset_name="/home/zx/.cache/swe-bench-lite.json",
    split="test",
    instance_ids=instance_ids,
    predictions_path="/home/zx/mycc/PilotCode/swe_bench_test/predictions_merged.jsonl",
    max_workers=4,
    force_rebuild=False,
    cache_level="env",
    clean=False,
    open_file_limit=4096,
    run_id="pilotcode_merged_20_eval",
    timeout=1800,
    namespace=None,
    rewrite_reports=False,
    modal=False,
)
print("[DEBUG] Done", flush=True)
