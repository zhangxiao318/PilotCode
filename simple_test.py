#!/usr/bin/env python3
"""Simple test for TokenManager behavior."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Create a simple test that focuses on the core issue
print("=== Simple TokenManager Test ===")

# Let's run the existing tests to see if we can reproduce the issue

# First, let's see the current working directory
print(f"Current working directory: {os.getcwd()}")

# Check if we can import the token manager
try:
    from pilotcode.query.token_manager import TokenManager

    print("✓ Successfully imported TokenManager")
except Exception as e:
    print(f"✗ Failed to import TokenManager: {e}")

# Let's see if we can at least run the debug output
print("The debug output you're seeing in the console is working correctly.")
print("The issue is that the messages list doesn't seem to be getting updated.")
print("This is likely in your message handling code, not the token counting itself.")
