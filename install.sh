#!/bin/bash
# Installation script for PilotCode
# Usage: ./install.sh [--dev] [--index]

set -e

show_help() {
    cat << 'EOF'
Usage: ./install.sh [options]

Options:
  --dev       Install development dependencies (pytest, black, ruff)
  --index     Install extra language parsers (JS, Go, Rust, Java)
  --help      Show this help message

Examples:
  ./install.sh                    Interactive install
  ./install.sh --dev              Install with dev tools
  ./install.sh --index            Install with extra language parsers
  ./install.sh --dev --index      Install everything
EOF
}

DEV_MODE=false
INDEX_MODE=false
for arg in "$@"; do
    case "$arg" in
        --dev) DEV_MODE=true ;;
        --index) INDEX_MODE=true ;;
        --help|-h) show_help; exit 0 ;;
        --*) echo "[ERROR] Unknown option: $arg"; show_help; exit 1 ;;
    esac
done

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
KNOWHOW_DIR="$HOME/.pilotcode/data/knowhow"
if [ ! -d "$KNOWHOW_DIR" ]; then
    echo "Copying default knowhow templates..."
    mkdir -p "$KNOWHOW_DIR"
    cp config/knowhow/*.json "$KNOWHOW_DIR/" 2>/dev/null || true
fi

# Install package in editable mode (with dev extras if requested)
if [ "$DEV_MODE" = true ]; then
    echo "Installing PilotCode with dev dependencies..."
    pip install -e ".[dev]"
else
    echo "Installing PilotCode..."
    pip install -e .
fi

# Try to install tree-sitter C/C++ parsers
echo "Installing tree-sitter parsers for C/C++ code indexing..."
if pip install tree-sitter-c tree-sitter-cpp >/dev/null 2>&1; then
    echo "Tree-sitter C/C++ parsers installed."
else
    echo ""
    echo "========================================"
    echo "[WARNING] Tree-sitter C/C++ parsers failed to install."
    echo "========================================"
    echo ""
    echo "This usually means a C compiler is not available."
    echo ""
    echo "To enable C/C++ code indexing, install a C compiler:"
    echo "  - Debian/Ubuntu: sudo apt install build-essential"
    echo "  - Fedora/RHEL:   sudo dnf install gcc gcc-c++"
    echo "  - macOS:         xcode-select --install"
    echo ""
    echo "PilotCode will still work fine --- C/C++ files will be"
    echo "indexed using regex fallback (slightly less accurate)."
    echo "========================================"
    echo ""
fi

# Optional extra language parsers
if [ "$INDEX_MODE" = true ]; then
    echo "Installing extra language parsers (JS/Go/Rust/Java)..."
    pip install tree-sitter-javascript tree-sitter-go tree-sitter-rust tree-sitter-java || true
fi

echo ""
echo "Installation complete!"
echo ""
if [ "$DEV_MODE" = true ]; then
    echo "Dev mode enabled: pytest, pytest-asyncio, respx, and other dev tools are installed."
    echo ""
fi
echo "To use PilotCode:"
echo "  source .venv/bin/activate"
echo "  pilotcode              # TUI mode"
echo "  pilotcode --web        # Web UI mode"
echo ""
echo "Or directly:"
echo "  ./pilotcode"
echo "  ./pilotcode --web"
echo ""
echo "Optional - global access without activating venv:"
echo "  Add $(pwd)/.venv/bin to your PATH, then use 'pilotcode' anywhere."
echo ""
if [ "$DEV_MODE" = false ] && [ "$INDEX_MODE" = false ]; then
    echo "To install extra dependencies:"
    echo "  ./install.sh --dev      # dev tools (pytest, black, ruff)"
    echo "  ./install.sh --index    # extra language parsers (JS/Go/Rust/Java)"
fi
