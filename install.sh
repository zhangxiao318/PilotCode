#!/bin/bash
# Installation script for PilotCode

set -e

echo "Installing PilotCode..."

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $python_version"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Copy default knowhow templates to user config directory
KNOWHOW_DIR="$HOME/.pilotcode/knowhow"
if [ ! -d "$KNOWHOW_DIR" ]; then
    echo "Copying default knowhow templates..."
    mkdir -p "$KNOWHOW_DIR"
    cp config/knowhow/*.json "$KNOWHOW_DIR/" 2>/dev/null || true
fi

# Install package in editable mode
echo "Installing PilotCode..."
pip install -e .

echo ""
echo "Installation complete!"
echo ""
echo "To use PilotCode:"
echo "  source .venv/bin/activate"
echo "  pilotcode"
echo ""
echo "Or directly:"
echo "  ./pilotcode"
