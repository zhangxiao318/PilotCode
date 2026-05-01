"""
Simple test to verify PilotCode can fix a bug and produce a git diff (patch).
This tests the core harness pipeline without requiring SWE-bench dataset.
"""

import os
import subprocess
import tempfile
import json


def run_cmd(cmd, cwd=None, timeout=300):
    result = subprocess.run(
        cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )
    return result.returncode, result.stdout, result.stderr


def test_pilotcode_fix():
    # Create a temporary git repo with a simple bug
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = os.path.join(tmpdir, "test_repo")
        os.makedirs(repo_dir)

        # Init git repo
        run_cmd("git init", cwd=repo_dir)
        run_cmd("git config user.email 'test@test.com'", cwd=repo_dir)
        run_cmd("git config user.name 'Test'", cwd=repo_dir)

        # Write a buggy Python file
        buggy_code = """\
def add(a, b):
    # Bug: missing return
    a + b
"""
        with open(os.path.join(repo_dir, "math_utils.py"), "w") as f:
            f.write(buggy_code)

        run_cmd("git add .", cwd=repo_dir)
        run_cmd("git commit -m 'initial'", cwd=repo_dir)

        # Prompt for PilotCode
        prompt = (
            "The file math_utils.py has a bug: the function 'add' does not return "
            "the result. Fix it so that the function returns a + b. "
            "Do not add any extra text or explanation, just make the minimal fix."
        )

        # Run PilotCode headless
        pilotcode_cmd = (
            f"cd {repo_dir} && python3 -m pilotcode "
            f"--skip-config-check --auto-allow --max-iterations 15 "
            f'-p "{prompt}"'
        )
        print(f"Running: {pilotcode_cmd}")
        rc, stdout, stderr = run_cmd(pilotcode_cmd, cwd=repo_dir, timeout=120)
        print("STDOUT:\n", stdout)
        print("STDERR:\n", stderr)

        if rc != 0:
            print(f"PilotCode exited with code {rc}")
            return False

        # Get git diff
        rc, diff, _ = run_cmd("git diff", cwd=repo_dir)
        print("GIT DIFF:\n", diff)

        if "return" in diff:
            print("SUCCESS: PilotCode produced a patch that includes 'return'")
            return True
        else:
            print("FAILURE: Patch does not contain expected fix")
            return False


if __name__ == "__main__":
    success = test_pilotcode_fix()
    exit(0 if success else 1)
