---
description: Fixed ! shell escape in TUI v2 - process_query bypasses LLM for ! commands
type: reference
tags: tui-v2, shell-escape, process_query, session-service
---

## Problem

When running `!dir` (or any `!` shell escape) in TUI v2, the app appeared frozen with no output.

**Root cause**: `session_service.py`'s `process_query()` did not check for `!` prefix. The text `!dir` was sent directly to the LLM via `query_engine.submit_message("!dir")`, requiring a full LLM round-trip (5-20+ seconds) with no immediate feedback.

The web server (`server.py:1917`) handled `!` correctly by checking `text.startswith("!")` before calling the query engine. The `handle_command()` method in `session_service.py:1103` also had correct `!` handling, but `process_query()` never called it.

## Fix

Added `!` shell escape interception at the beginning of `process_query()` (session_service.py:349-408):
- Check `text.startswith("!")` right after status update
- Execute shell command directly via `asyncio.create_subprocess_shell`
- Emit `$ command` as OPEN block and output as CLOSE block
- Set `is_processing=False` and return immediately
- 30s timeout with error message
- Output capped at 5000 chars

This mirrors the same pattern used in `server.py` and `_dispatch_shell_escape()`.

## Files changed

- `src/pilotcode/ui/session_service.py` — added `!` interception in `process_query()`
