#!/bin/bash
# Regression test suite for PilotCode
# Runs all tests including plugin tests

set -e

echo "=========================================="
echo "PilotCode Regression Test Suite"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track results
FAILED=0

# Function to run tests
run_test_suite() {
    local name="$1"
    local path="$2"
    local markers="$3"
    local optional="${4:-false}"
    
    echo ""
    echo "------------------------------------------"
    echo "Running: $name"
    echo "------------------------------------------"
    
    local cmd="python3 -m pytest $path -q --tb=short"
    if [ -n "$markers" ]; then
        cmd="$cmd -m \"$markers\""
    fi
    
    if eval "$cmd"; then
        echo -e "${GREEN}PASSED: $name${NC}"
    else
        if [ "$optional" = "false" ]; then
            echo -e "${RED}FAILED: $name${NC}"
            FAILED=1
        else
            echo -e "${YELLOW}OPTIONAL FAILED: $name (continuing...)${NC}"
        fi
    fi
}

# Core unit tests (always required)
run_test_suite "Core Unit Tests" "tests/unit" "not integration and not e2e and not network and not slow" false

# Plugin unit tests (always required)
run_test_suite "Plugin Unit Tests" "tests/plugins/unit" "plugin_unit" false

# Tool tests
run_test_suite "Tool Tests" "tests/unit/tools" "" false

# Summary
echo ""
echo "=========================================="
echo "Regression Test Summary"
echo "=========================================="

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All required tests PASSED!${NC}"
    exit 0
else
    echo -e "${RED}Some tests FAILED!${NC}"
    exit 1
fi
