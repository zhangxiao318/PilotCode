"""Main entry point for PilotCode."""

import sys
import os

# Add src to path for development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pilotcode.cli import cli_main

if __name__ == "__main__":
    cli_main()
