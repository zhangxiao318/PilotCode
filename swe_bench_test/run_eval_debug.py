#!/usr/bin/env python3
"""Debug SWE-bench evaluation step by step."""

import sys
import os
import faulthandler
import signal

faulthandler.enable()
faulthandler.register(signal.SIGUSR1)

sys.stdout.reconfigure(line_buffering=True)

print("[DEBUG] Importing...", flush=True)
import docker
import platform

from swebench.harness.run_evaluation import (
    get_dataset_from_preds,
    build_env_images,
    run_instances,
)
from swebench.harness.utils import load_swebench_dataset, get_predictions_from_file
from swebench.harness.constants import KEY_INSTANCE_ID, MAP_REPO_VERSION_TO_SPECS

if "pytest-dev/pytest" in MAP_REPO_VERSION_TO_SPECS:
    for ver in MAP_REPO_VERSION_TO_SPECS["pytest-dev/pytest"]:
        MAP_REPO_VERSION_TO_SPECS["pytest-dev/pytest"][ver]["python"] = "3.10"

print("[DEBUG] Loading dataset...", flush=True)
dataset_name = "/home/zx/.cache/swe-bench-lite.json"
split = "test"
dataset = load_swebench_dataset(dataset_name, split)
print(f"[DEBUG] Dataset loaded: {len(dataset)} instances", flush=True)

print("[DEBUG] Loading predictions...", flush=True)
predictions = get_predictions_from_file(
    "/home/zx/mycc/PilotCode/swe_bench_test/predictions_all.jsonl",
    dataset_name,
    split,
)
print(f"[DEBUG] Predictions loaded: {len(predictions)}", flush=True)

pred_map = {pred[KEY_INSTANCE_ID]: pred for pred in predictions}
instance_ids = list(pred_map.keys())
print(f"[DEBUG] Instance IDs: {instance_ids}", flush=True)

run_id = "pilotcode_all_25_eval"
rewrite_reports = False

print("[DEBUG] Calling get_dataset_from_preds()...", flush=True)
ds = get_dataset_from_preds(dataset_name, split, instance_ids, pred_map, run_id, rewrite_reports)
print(f"[DEBUG] Dataset from preds: {len(ds)} instances", flush=True)

print("[DEBUG] Calling load_swebench_dataset(instance_ids)...", flush=True)
full_dataset = load_swebench_dataset(dataset_name, split, instance_ids)
print(f"[DEBUG] Full dataset: {len(full_dataset)} instances", flush=True)

print("[DEBUG] Calling docker.from_env()...", flush=True)
client = docker.from_env()
print("[DEBUG] Docker client OK", flush=True)

print("[DEBUG] Calling build_env_images()...", flush=True)
build_env_images(
    client,
    ds,
    force_rebuild=False,
    max_workers=4,
    namespace=None,
    instance_image_tag="latest",
    env_image_tag="latest",
)
print("[DEBUG] build_env_images() done", flush=True)

print("[DEBUG] Calling run_instances()...", flush=True)
run_instances(
    pred_map,
    ds,
    full_dataset,
    client,
    run_id,
    timeout=1800,
    rm_image=False,
    rewrite_reports=False,
)
print("[DEBUG] Done", flush=True)
