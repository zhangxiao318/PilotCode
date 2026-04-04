#!/bin/bash
# Run script for PilotCode

# Set UTF-8 encoding for proper international character support
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export PYTHONIOENCODING=utf-8

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Set PYTHONPATH to include src directory
export PYTHONPATH="${SCRIPT_DIR}/src:${PYTHONPATH}"

# Check if virtual environment exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Run PilotCode
# If no command specified, default to 'main'
if [ $# -eq 0 ]; then
    python3 -m pilotcode main
else
    python3 -m pilotcode "$@"
fi
