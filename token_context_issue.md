# Token Context Management Issue Analysis

## Problem Summary

The test results show a clear issue with the TokenManager's token counting behavior. When adding messages to a conversation, the token count stays constant at 26 tokens regardless of the number of messages added.

## Root Cause Analysis

Looking at the debug output, the issue is in the TokenManager's caching logic:

1. **First Message (count=1)**: Uses Priority 2 (Precise tokenizer) and returns 26 tokens
2. **Subsequent Messages**: All use Priority 2 (Precise tokenizer rate-limited) and return the same cached value of 26 tokens

This happens because:
- The `_last_precise_count` is set to 26 after the first message
- The `_last_precise_count_hash` is calculated from the message state
- For subsequent messages, the hash stays the same (because we're adding identical messages)
- The rate limit check (`MIN_PRECISE_INTERVAL`) prevents re-computation

## Technical Details from Debug Output

The debug log shows:
```
DEBUG TokenManager.count_tokens: Starting with hash=8451902438455414388, messages_count=1
DEBUG TokenManager.count_tokens: Priority 2 (Precise tokenizer) - returning 26
...
DEBUG TokenManager.count_tokens: Starting with hash=188841005132129794, messages_count=2
DEBUG TokenManager.count_tokens: Priority 2 (Precise tokenizer rate-limited) - returning 26
```

The issue is that the hash calculation doesn't change when we add new messages because:
1. The same message content is being used repeatedly
2. The `_compute_state_hash()` function is not properly detecting the change in message count
3. There's likely an issue with how the hash is computed when messages are added

## Fix Approaches

1. **Fix the hash computation**: Ensure that `_compute_state_hash()` properly accounts for all messages in the conversation
2. **Update the caching logic**: The cache should be invalidated when new messages are added
3. **Modify rate limiting logic**: Ensure that rate limiting doesn't prevent legitimate re-calculation when the conversation state changes

## Proposed Solution

The issue is in the `_compute_state_hash()` method. Looking at the token manager code, it's not properly tracking that the messages list has changed. The hash calculation is likely missing the actual message content or not properly detecting changes in the message list.

Looking at the current implementation:
```python
def _compute_state_hash(self) -> str:
    """Cheap hash of current conversation state."""
    parts: list[str] = []
    for m in self.messages:
        if hasattr(m, "content"):
            parts.append(f"{getattr(m, 'role', 'user')}:{m.content}")
        elif hasattr(m, "name") and hasattr(m, "input"):
            parts.append(f"tool:{m.name}:{m.input}")
        else:
            parts.append(str(m))
    if self.tools:
        try:
            parts.append(
                json.dumps(
                    [t.to_dict() if hasattr(t, "to_dict") else t for t in self.tools],
                    sort_keys=True,
                )
            )
        except Exception:
            pass
    return str(hash("|".join(parts)))
```

The issue is that when we add identical messages, the hash values are the same and the cache is reused. We need to make sure that:
1. The hash properly includes the current message count
2. Or that we properly detect when a new message is added

The simplest fix would be to include the length of messages in the hash calculation.