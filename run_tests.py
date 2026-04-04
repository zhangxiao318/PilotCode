#!/usr/bin/env python3
"""Test runner for PilotCode.

Usage:
    python run_tests.py                    # Run all tests
    python run_tests.py --quick            # Run only fast unit tests
    python run_tests.py --integration      # Run integration tests only
    python run_tests.py --tools            # Run tool tests only
    python run_tests.py --cov              # Run with coverage
    python run_tests.py -k test_name       # Run matching tests
"""

import sys
import os
import subprocess
import argparse


def main():
    parser = argparse.ArgumentParser(description="Run PilotCode test suite")
    parser.add_argument("--quick", action="store_true", help="Skip slow/network tests")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    parser.add_argument("--tools", action="store_true", help="Run tool tests only")
    parser.add_argument("--commands", action="store_true", help="Run command tests only")
    parser.add_argument("--permissions", action="store_true", help="Run permission tests only")
    parser.add_argument("--cov", action="store_true", help="Enable coverage reporting")
    parser.add_argument("-k", dest="keyword", help="Only run tests matching expression")
    parser.add_argument("-v", action="store_true", help="Verbose output")
    parser.add_argument("--run-web-tests", action="store_true", help="Include network-dependent web tests")
    args, extra = parser.parse_known_args()

    # Ensure src is on PYTHONPATH
    env = os.environ.copy()
    src_path = os.path.join(os.path.dirname(__file__), "src")
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = src_path + os.pathsep + env["PYTHONPATH"]
    else:
        env["PYTHONPATH"] = src_path

    pytest_args = [sys.executable, "-m", "pytest"]

    if args.v:
        pytest_args.append("-v")

    if args.cov:
        pytest_args.extend(["--cov=pilotcode", "--cov-report=term-missing"])

    # Determine test target
    if args.integration:
        pytest_args.append("tests/test_integration.py")
    elif args.tools:
        pytest_args.append("tests/test_tools_comprehensive.py")
    elif args.commands:
        pytest_args.append("tests/test_commands.py")
    elif args.permissions:
        pytest_args.append("tests/test_permissions.py")
    else:
        pytest_args.append("tests/")
        # Legacy src/tests has module path issues when tests/ exists at root;
        # run it explicitly only when requested.
        if os.path.isdir("src/tests") and not os.path.isdir("tests"):
            pytest_args.append("src/tests/")

    if args.keyword:
        pytest_args.extend(["-k", args.keyword])

    if args.quick:
        pytest_args.extend(["-m", "not slow and not network"])

    if not args.run_web_tests:
        # Add a marker skip expression if needed, but our web tests use @pytest.mark.skip
        pass

    # Pass through any extra args
    pytest_args.extend(extra)

    print(f"Running: {' '.join(pytest_args)}")
    print(f"PYTHONPATH={env.get('PYTHONPATH')}")
    print()

    result = subprocess.run(pytest_args, env=env)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
