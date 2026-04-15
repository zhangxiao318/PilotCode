#!/usr/bin/env python3
"""
Build a mini SWE-bench dataset from a real GitHub PR.
This avoids needing to download the full HF dataset.
"""

import json
import sys
import argparse

from swebench.collect.utils import Repo
from swebench.collect.build_dataset import create_instance, is_valid_instance, has_test_patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="psf/requests", help="Owner/Name of GitHub repo")
    parser.add_argument("--pull_number", type=int, required=True, help="PR number to convert")
    parser.add_argument("--output", default="mini_dataset.json", help="Output JSON file")
    args = parser.parse_args()

    owner, name = args.repo.split("/")
    repo = Repo(owner, name)

    print(f"Fetching PR #{args.pull_number} from {args.repo}...")
    pull = repo.call_api(repo.api.pulls.get, owner=owner, repo=name, pull_number=args.pull_number)
    if pull is None:
        print("Failed to fetch PR")
        sys.exit(1)

    print(f"PR title: {pull['title']}")
    print(f"Merged: {pull.get('merged_at')}")

    # Add resolved_issues field required by create_instance
    pull["resolved_issues"] = repo.extract_resolved_issues(pull)

    instance = create_instance(repo, pull)
    if not is_valid_instance(instance):
        print("Warning: PR is not a valid SWE-bench instance (not merged or missing issue). Proceeding anyway for testing.")

    if not has_test_patch(instance):
        print("Warning: instance has no test patch")

    # SWE-bench format requires a few extra fields
    record = {
        "repo": instance["repo"],
        "instance_id": f"{instance['repo'].replace('/', '__')}-{args.pull_number}",
        "base_commit": instance["base_commit"],
        "patch": instance["patch"],
        "test_patch": instance["test_patch"],
        "problem_statement": (instance.get("problem_statement") or (pull["title"] + "\n" + (pull.get("body") or ""))),
        "hints_text": "",
        "created_at": pull["created_at"],
        "version": "",
        "FAIL_TO_PASS": "",
        "PASS_TO_PASS": "",
        "environment_setup_commit": instance["base_commit"],
    }

    with open(args.output, "w") as f:
        json.dump([record], f, indent=2)

    print(f"Saved mini dataset to {args.output}")
    print(f"Instance ID: {record['instance_id']}")


if __name__ == "__main__":
    main()
