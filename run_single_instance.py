#!/usr/bin/env python3
"""Run a single SWE-bench instance through the PilotCode harness."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "swe_bench_test"))
from run_pilotcode_harness import solve_instance

CACHE_JSON = "/home/zx/.cache/swe-bench-lite.json"

def load_instance_cached(instance_id: str):
    if os.path.exists(CACHE_JSON):
        with open(CACHE_JSON) as f:
            dataset = json.load(f)
    else:
        from swebench.harness.utils import load_swebench_dataset
        dataset = load_swebench_dataset("princeton-nlp/SWE-bench_Lite", "test")
    for inst in dataset:
        if inst["instance_id"] == instance_id:
            return inst
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("instance_id")
    parser.add_argument("--output", default="predictions_single.jsonl")
    args = parser.parse_args()

    instance = load_instance_cached(args.instance_id)
    if instance is None:
        print(f"Instance {args.instance_id} not found in dataset")
        sys.exit(1)

    prediction = solve_instance(instance)
    with open(args.output, "a") as f:
        f.write(json.dumps(prediction) + "\n")
    print(json.dumps(prediction, indent=2))

if __name__ == "__main__":
    main()
