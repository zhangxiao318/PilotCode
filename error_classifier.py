#!/usr/bin/env python3
"""Classify error type and extract stack trace file:line using regex."""

import re
import sys

PATTERNS = [
    (
        r"(?m)^(\w+(?:Error|Exception|Warning|Interrupt)):",  # Python tb
        r'(?m)^\s*File\s+"([^"]+)",\s+line\s+(\d+)',
    ),
    (r'"type"\s*:\s*"([^"]*error[^"]*)"', None),  # API JSON
    (r"^Error:\s*(.+)$", None),  # Generic
]


def classify(text: str):
    """Return (error_type, [(file, line), ...])."""
    err_type, locations = "UnknownError", []
    for tp, _ in PATTERNS:
        m = re.search(tp, text, re.IGNORECASE)
        if m:
            err_type = "".join(w.capitalize() for w in re.split(r"[_ ]+", m.group(1)))
            break
    for _, lp in PATTERNS:
        if lp:
            for m in re.finditer(lp, text):
                locations.append((m.group(1), int(m.group(2))))
    return err_type, locations


if __name__ == "__main__":
    text = ""
    if not sys.stdin.isatty():
        text = sys.stdin.read()
    elif len(sys.argv) > 1:
        text = open(sys.argv[1]).read()
    if not text:
        print("Usage: echo 'tb' | python error_classifier.py  OR  file arg")
        sys.exit(1)
    err, locs = classify(text)
    print(f"Error Type: {err}")
    print("Stack Trace Locations:")
    for fname, lineno in locs:
        print(f"  File: {fname}, Line: {lineno}")
    if not locs:
        print("  (none extracted)")
