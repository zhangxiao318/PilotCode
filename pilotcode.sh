#!/bin/bash
# PilotCode launcher script
# Usage: ./pilotcode.sh [command] [args...]

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Set PYTHONPATH
export PYTHONPATH="${SCRIPT_DIR}/src:${PYTHONPATH}"

# Run pilotcode - if no arguments, run main (start the application)
if [ $# -eq 0 ]; then
    python3 -m pilotcode
else
    python3 -m pilotcode "$@"
fi
