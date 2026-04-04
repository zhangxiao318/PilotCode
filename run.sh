#!/bin/bash
# Run script for ClaudeDecode

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Set PYTHONPATH to include src directory
export PYTHONPATH="${SCRIPT_DIR}/src:${PYTHONPATH}"

# Check if virtual environment exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Run ClaudeDecode
# If no command specified, default to 'main'
if [ $# -eq 0 ]; then
    python3 -m claudecode main
else
    python3 -m claudecode "$@"
fi
