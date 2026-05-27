---
description: Root cause analysis of token calculation not updating after message input
type: analysis
tags: token, calculation, cache, submit_message, query_engine
---

# Token Calculation Issue Analysis

## Problem Summary
The token usage count in the UI does not update when new messages are input. This occurs because the token manager's cache is not reset after messages are added to the conversation history.

## Root Cause
In `src/pilotcode/query_engine.py`, the `submit_message` method adds messages to `self.messages` but does not reset the token manager's cache afterward. This causes `count_tokens()` to return stale cached values instead of recalculating the current token usage.

## Key Findings

### 1. TokenManager Cache Behavior
- TokenManager uses a sophisticated caching system with multiple layers:
  - API-reported usage (highest priority)
  - Precise tokenizer results
  - Exact base + delta estimation
  - Heuristic fallback
- Cache is invalidated when message list hash changes
- `reset_cache()` is called in specific scenarios but not after message additions

### 2. Problem Locations
The following locations properly reset cache:
- `clear_history()` method
- `load_session()` method  
- `load_from_storage()` method
- `/session load` command

But the following location does NOT reset cache:
- `submit_message()` method - after adding any message to `self.messages`

### 3. Message Addition Flow in submit_message()
The method adds messages in several places:
1. `user_msg = UserMessage(content=prompt)` → `self.messages.append(user_msg)` 
2. `assistant_msg = AssistantMessage(content=reply)` → `self.messages.append(assistant_msg)`
3. `review_msg = SystemMessage(content=review_msg_content)` → `self.messages.append(review_msg)`
4. `tool_use_msg = ToolUseMessage(...)` → `self.messages.append(tool_use_msg)`
5. `tool_result_msg = ToolResultMessage(...)` → `self.messages.append(tool_result_msg)`

## Solution
After each `self.messages.append()` call in `submit_message()`, add:
```python
self._token_mgr.reset_cache()
```

This ensures that `count_tokens()` will recalculate the token usage instead of returning cached stale values.

## Verification
The fix should be tested by:
1. Inputting a message and checking if token count updates
2. Inputting multiple messages and verifying cumulative token count
3. Using `/status` command to verify token count reflects current messages