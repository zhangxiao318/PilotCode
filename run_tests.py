#!/usr/bin/env python3
"""Simple test runner for development."""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Run tests
import pytest
sys.exit(pytest.main(["-v", "src/tests/"] + sys.argv[1:]))
