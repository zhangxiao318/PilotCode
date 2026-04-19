#!/usr/bin/env python3
"""
Verify that SWE-bench + Docker pipeline is installed and functional.
Does NOT require the full SWE-bench dataset.
"""

import docker
import sys

from swebench.harness.test_spec.test_spec import make_test_spec
from swebench.harness.constants import SWEbenchInstance


def test_docker():
    print("Testing Docker client connection...")
    try:
        client = docker.from_env()
        info = client.info()
        print(f"  Docker version: {info['ServerVersion']}")
        print(f"  Containers: {info['Containers']}")
        print("  Docker OK")
        return True
    except Exception as e:
        print(f"  Docker FAILED: {e}")
        return False


def test_swebench_imports():
    print("Testing SWE-bench imports...")
    try:
        from swebench.harness.run_evaluation import main as eval_main
        from swebench.harness.utils import load_swebench_dataset
        from swebench.harness.grading import get_eval_report

        print("  Imports OK")
        return True
    except Exception as e:
        print(f"  Imports FAILED: {e}")
        return False


def test_make_test_spec():
    print("Testing make_test_spec interface...")
    try:
        # Minimal mock instance to verify the function signature works
        mock_instance: SWEbenchInstance = {
            "repo": "psf/requests",
            "instance_id": "psf__requests-9999",
            "base_commit": "abcdef1234567890abcdef1234567890abcdef12",
            "patch": "",
            "test_patch": "",
            "problem_statement": "mock problem",
            "hints_text": "",
            "created_at": "2024-01-01T00:00:00Z",
            "version": "2.31.0",
            "FAIL_TO_PASS": "[]",
            "PASS_TO_PASS": "[]",
            "environment_setup_commit": "abcdef1234567890abcdef1234567890abcdef12",
        }
        # This will fail during script generation because the commit is fake,
        # but it proves the API works.
        try:
            spec = make_test_spec(mock_instance)
            print(f"  TestSpec created: {spec.instance_id}")
        except Exception as e:
            # Expected to fail for fake commit, but we check it fails for the right reason
            error_msg = str(e).lower()
            if "commit" in error_msg or "script" in error_msg or "docker" in error_msg:
                print(
                    f"  make_test_spec callable (expected error for fake commit: {type(e).__name__})"
                )
            else:
                raise
        print("  make_test_spec OK")
        return True
    except Exception as e:
        print(f"  make_test_spec FAILED: {e}")
        return False


def main():
    results = []
    results.append(("Docker", test_docker()))
    results.append(("SWE-bench imports", test_swebench_imports()))
    results.append(("make_test_spec", test_make_test_spec()))

    print("\n" + "=" * 40)
    all_ok = all(r[1] for r in results)
    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  {name}: {status}")
    print("=" * 40)

    if all_ok:
        print("\nSWE-bench pipeline is ready!")
        print("Next step: provide a real dataset and predictions to run full evaluation.")
        sys.exit(0)
    else:
        print("\nSome checks failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
