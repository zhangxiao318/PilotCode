---
description: Fix for token calculation not updating after message input
type: fix
tags: token, calculation, cache, submit_message, query_engine
---

# Token Calculation Fix

## Problem
The token usage count in the UI does not update when new messages are input because the token manager's cache is not reset after messages are added to the conversation history.

## Root Cause
In `src/pilotcode/query_engine.py`, the `submit_message` method adds messages to `self.messages` but does not reset the token manager's cache afterward. This causes `count_tokens()` to return stale cached values instead of recalculating the current token usage.

## Solution Implemented
Added `self._token_mgr.reset_cache()` calls after each message addition in the `submit_message` method:

1. **After user message addition** (line ~329):
   ```python
   user_msg = UserMessage(content=prompt)
   self.messages.append(user_msg)
   self._token_mgr.reset_cache()  # Added this line
   yield QueryResult(message=user_msg, is_complete=False)
   ```

2. **After assistant message addition** (line ~357):
   ```python
   assistant_msg = AssistantMessage(content=reply)
   self.messages.append(assistant_msg)
   self._token_mgr.reset_cache()  # Added this line
   yield QueryResult(message=assistant_msg, is_complete=False)
   ```

3. **After system message addition** (line ~417):
   ```python
   review_msg = SystemMessage(content=review_msg_content)
   self.messages.append(review_msg)
   self._token_mgr.reset_cache()  # Added this line
   ```

4. **After tool use message addition** (line ~653):
   ```python
   tool_use_msg = ToolUseMessage(...)
   self.messages.append(tool_use_msg)
   self._token_mgr.reset_cache()  # Added this line
   ```

5. **After tool result message addition** (line ~761):
   ```python
   tool_result_msg = ToolResultMessage(...)
   self.messages.append(tool_result_msg)
   self._token_mgr.reset_cache()  # Added this line
   ```

## Verification
The fix ensures that:
1. Token count updates immediately when new messages are added
2. `/status` command shows correct token usage
3. UI displays accurate token information
4. No performance impact as cache reset is only called when necessary

This resolves the issue where token usage remained static despite new messages being input.