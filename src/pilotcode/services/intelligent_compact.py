"""Intelligent context compaction - ClaudeCode-style implementation.

This module implements advanced context management:
1. Micro-compact: Clear old tool results but keep summary markers
2. Time-based compaction: Progressive content clearing
3. Structured summary generation
"""

import json
import hashlib
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from ..types.message import MessageType


@dataclass
class CompactConfig:
    """Configuration for context compaction."""
    # Token thresholds
    warning_threshold: int = 100000  # Warn at 100k tokens
    compact_threshold: int = 150000  # Compact at 150k tokens
    critical_threshold: int = 180000  # Aggressive compact at 180k tokens
    
    # Message thresholds
    min_messages_to_keep: int = 6  # Always keep last 6 exchanges
    max_messages_full_content: int = 20  # Keep full content for last 20
    
    # Tool result management
    clear_tool_results_after: int = 10  # Clear tool results older than 10 messages
    preserve_recent_tool_results: bool = True  # Keep recent tool results


@dataclass
class ToolResultSummary:
    """Summary of a tool result for compaction."""
    tool_name: str
    success: bool
    result_preview: str  # First 100 chars
    result_hash: str  # For detecting changes
    timestamp: float


@dataclass
class CompactedMessage:
    """A message that has been compacted."""
    original_type: str
    role: str
    content_summary: str | None
    tool_calls: list[dict] | None
    tool_results_cleared: bool = False
    original_token_count: int = 0
    compacted_token_count: int = 0


@dataclass 
class CompactionResult:
    """Result of context compaction."""
    original_messages: int
    compacted_messages: int
    original_tokens: int
    compacted_tokens: int
    messages_removed: int
    tool_results_cleared: int
    summaries_generated: int
    preserved_context: dict[str, Any]


class IntelligentContextCompactor:
    """Intelligent context compactor similar to ClaudeCode."""
    
    # Marker for cleared tool results
    CLEARED_MARKER = "[Previous tool result content cleared to save context space]"
    
    def __init__(self, config: CompactConfig | None = None):
        self.config = config or CompactConfig()
        self.preserved_tool_results: dict[str, ToolResultSummary] = {}
    
    def estimate_tokens(self, text: str) -> int:
        """Rough token estimation (1 token ≈ 4 chars for English)."""
        return len(text) // 4
    
    def should_compact(self, messages: list[Any], total_tokens: int | None = None) -> bool:
        """Determine if compaction is needed."""
        if len(messages) < self.config.min_messages_to_keep:
            return False
        
        if total_tokens is None:
            total_tokens = sum(
                self.estimate_tokens(str(getattr(m, 'content', '')))
                for m in messages
            )
        
        return total_tokens > self.config.compact_threshold
    
    def compact_tool_result(
        self, 
        message: Any,
        preserve_in_summary: bool = True
    ) -> Any:
        """Compact a tool result message, keeping only essential info."""
        from ..types.message import ToolResultMessage
        
        if not isinstance(message, ToolResultMessage):
            return message
        
        content = message.content
        if isinstance(content, str) and len(content) > 200:
            # Create summary
            preview = content[:100] + "..." if len(content) > 100 else content
            
            # Store in preserved results if needed
            if preserve_in_summary:
                self.preserved_tool_results[message.tool_use_id] = ToolResultSummary(
                    tool_name="unknown",  # Could extract from related ToolUseMessage
                    success=not message.is_error,
                    result_preview=preview,
                    result_hash=hashlib.md5(content.encode()).hexdigest()[:8],
                    timestamp=datetime.now().timestamp()
                )
            
            # Return compacted version
            return ToolResultMessage(
                tool_use_id=message.tool_use_id,
                content=self.CLEARED_MARKER + f" (was {len(content)} chars)",
                is_error=message.is_error
            )
        
        return message
    
    def compact_messages(
        self,
        messages: list[Any],
        total_tokens: int | None = None
    ) -> CompactionResult:
        """Compact messages intelligently."""
        if not self.should_compact(messages, total_tokens):
            return CompactionResult(
                original_messages=len(messages),
                compacted_messages=len(messages),
                original_tokens=total_tokens or 0,
                compacted_tokens=total_tokens or 0,
                messages_removed=0,
                tool_results_cleared=0,
                summaries_generated=0,
                preserved_context={}
            )
        
        from ..types.message import (
            SystemMessage, UserMessage, AssistantMessage, 
            ToolUseMessage, ToolResultMessage
        )
        
        original_count = len(messages)
        original_tokens = total_tokens or sum(
            self.estimate_tokens(str(getattr(m, 'content', '')))
            for m in messages
        )
        
        result_messages = []
        tool_results_cleared = 0
        summaries_generated = 0
        
        # Always keep first system message
        if messages and isinstance(messages[0], SystemMessage):
            result_messages.append(messages[0])
            start_idx = 1
        else:
            start_idx = 0
        
        # Determine which messages to compact
        total = len(messages)
        keep_recent = self.config.min_messages_to_keep
        
        for i, msg in enumerate(messages[start_idx:], start=start_idx):
            # Always keep recent messages
            if i >= total - keep_recent:
                result_messages.append(msg)
                continue
            
            # Compact old tool results
            if isinstance(msg, ToolResultMessage):
                compacted = self.compact_tool_result(msg, preserve_in_summary=True)
                if compacted is not msg:
                    tool_results_cleared += 1
                    result_messages.append(compacted)
                    continue
            
            # For other messages, keep but could summarize if very long
            if isinstance(msg, (UserMessage, AssistantMessage)):
                content = getattr(msg, 'content', '')
                if isinstance(content, str) and len(content) > 1000:
                    # Could implement message summarization here
                    pass
            
            result_messages.append(msg)
        
        compacted_tokens = sum(
            self.estimate_tokens(str(getattr(m, 'content', '')))
            for m in result_messages
        )
        
        return CompactionResult(
            original_messages=original_count,
            compacted_messages=len(result_messages),
            original_tokens=original_tokens,
            compacted_tokens=compacted_tokens,
            messages_removed=original_count - len(result_messages),
            tool_results_cleared=tool_results_cleared,
            summaries_generated=summaries_generated,
            preserved_context={
                'cleared_tool_results': len(self.preserved_tool_results),
                'compaction_time': datetime.now().isoformat()
            }
        )
    
    def generate_structured_summary(
        self,
        messages: list[Any],
        include_files: bool = True,
        include_errors: bool = True
    ) -> dict[str, Any]:
        """Generate structured summary of conversation (ClaudeCode-style)."""
        from ..types.message import (
            UserMessage, AssistantMessage, ToolUseMessage, ToolResultMessage
        )
        
        summary = {
            "primary_request": "",
            "key_technical_concepts": [],
            "files_examined": [],
            "files_modified": [],
            "errors_encountered": [],
            "pending_tasks": [],
            "user_messages": [],
            "tool_usage_summary": {}
        }
        
        for msg in messages:
            # Extract user messages
            if isinstance(msg, UserMessage):
                content = str(getattr(msg, 'content', ''))
                summary["user_messages"].append(content[:200])
                if not summary["primary_request"]:
                    summary["primary_request"] = content[:500]
            
            # Track file operations
            elif isinstance(msg, ToolUseMessage):
                tool_name = msg.name
                params = msg.input if isinstance(msg.input, dict) else {}
                
                # Track tool usage
                summary["tool_usage_summary"][tool_name] = \
                    summary["tool_usage_summary"].get(tool_name, 0) + 1
                
                # Track file operations
                if tool_name in ('FileRead', 'FileWrite', 'FileEdit'):
                    path = params.get('path') or params.get('file_path', '')
                    if path:
                        if tool_name == 'FileRead':
                            summary["files_examined"].append(path)
                        else:
                            summary["files_modified"].append(path)
                
                # Extract technical concepts from code
                if tool_name == 'FileRead' and 'content' in str(params):
                    # Could extract imports, class names, etc.
                    pass
            
            # Track errors
            elif isinstance(msg, ToolResultMessage):
                if msg.is_error:
                    error_content = str(getattr(msg, 'content', ''))
                    summary["errors_encountered"].append(error_content[:200])
        
        # Deduplicate
        summary["files_examined"] = list(set(summary["files_examined"]))
        summary["files_modified"] = list(set(summary["files_modified"]))
        
        return summary


# Global instance
_default_compactor: IntelligentContextCompactor | None = None


def get_intelligent_compactor() -> IntelligentContextCompactor:
    """Get global intelligent compactor."""
    global _default_compactor
    if _default_compactor is None:
        _default_compactor = IntelligentContextCompactor()
    return _default_compactor
