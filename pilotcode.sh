#!/bin/bash
# PilotCode launcher script
# Usage: ./pilotcode [command] [args...]
#        ./pilotcode           # Start main application
#        ./pilotcode --tui     # Start TUI mode
#        ./pilotcode configure # Run configuration wizard

# Set UTF-8 encoding for proper international character support
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export PYTHONIOENCODING=utf-8

# Get script directory (for PYTHONPATH)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Set PYTHONPATH to include src directory
export PYTHONPATH="${SCRIPT_DIR}/src:${PYTHONPATH}"

# Note: Do NOT cd to SCRIPT_DIR, keep current working directory

# Check if virtual environment exists and activate it
if [ -d ".venv" ] && [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Run PilotCode
if [ $# -eq 0 ]; then
    # No arguments: start main application (default)
    python3 -m pilotcode
elif [[ "$1" == --* ]]; then
    # Arguments start with -- (options): pass through directly
    # e.g., ./pilotcode --auto-allow
    python3 -m pilotcode "$@"
else
    # Arguments start with a command: pass through as-is
    # e.g., ./pilotcode configure --show
    python3 -m pilotcode "$@"
fi
