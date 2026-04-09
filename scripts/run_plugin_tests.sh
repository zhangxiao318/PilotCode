#!/bin/bash
# Quick plugin test runner

echo "=========================================="
echo "Running Plugin Tests"
echo "=========================================="

# Plugin unit tests
echo ""
echo "Plugin Unit Tests:"
python3 -m pytest tests/plugins/unit -q --tb=short

# Plugin integration tests (optional)
echo ""
echo "Plugin Integration Tests (optional):"
python3 -m pytest tests/plugins/integration -q --tb=short || echo "Some integration tests failed (optional)"

echo ""
echo "=========================================="
echo "Plugin Tests Complete"
echo "=========================================="
