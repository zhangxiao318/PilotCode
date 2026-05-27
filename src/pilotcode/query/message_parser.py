"""Message parsing for QueryEngine.

Encapsulates XML tool-call fallback parsing, cleanup, and API conversion.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ..types.message import ToolUseMessage, ToolResultMessage, to_api_format

logger = logging.getLogger(__name__)


class MessageParser:
    """Parses assistant content for XML tool calls and cleans up messages."""

    @staticmethod
    def parse_content_tool_calls(content: str) -> list[dict[str, Any]]:
        """Parse XML/pseudo-XML tool calls embedded in assistant content.

        Supports formats like:
          <tool_call><function=Bash><parameter=command>ls</parameter></function></tool_call>
          <tool_call><name>Bash</name><arguments>{"command":"ls"}</arguments></tool_call>
          <function=Bash><parameter=command>cd</parameter></tool_call>  (incomplete)

        Returns list of dicts with 'name' and 'arguments' keys.
        """
        tool_calls: list[dict[str, Any]] = []

        # Pattern 1: <tool_call>...<function=Name>...<parameter=key>value</parameter>...</function>...</tool_call>
        pattern = r"<tool_call>\s*<function=(\w+)>\s*(.*?)\s*</function>\s*</tool_call>"
        for match in re.finditer(pattern, content, re.DOTALL):
            tool_name = match.group(1)
            params_block = match.group(2)

            arguments: dict[str, Any] = {}
            param_pattern = r"<parameter=(\w+)>(.*?)</parameter>"
            for pmatch in re.finditer(param_pattern, params_block, re.DOTALL):
                arguments[pmatch.group(1)] = pmatch.group(2).strip()

            if tool_name:
                tool_calls.append({"name": tool_name, "arguments": arguments})

        # Pattern 2: <tool_call>...</tool_call> with <name> and <arguments> children
        if not tool_calls:
            pattern2 = (
                r"<tool_call>\s*<name>(\w+)</name>\s*<arguments>(.*?)</arguments>\s*</tool_call>"
            )
            for match in re.finditer(pattern2, content, re.DOTALL):
                tool_name = match.group(1)
                args_text = match.group(2).strip()
                try:
                    arguments = json.loads(args_text)
                except json.JSONDecodeError:
                    arguments = {"raw": args_text}
                if tool_name:
                    tool_calls.append({"name": tool_name, "arguments": arguments})

        # Pattern 3: Incomplete/flaky XML without <tool_call> wrapper or missing closing tags
        if not tool_calls:
            pattern3 = r"<function=(\w+)>\s*(.*?)\s*</tool_call>"
            for match in re.finditer(pattern3, content, re.DOTALL):
                tool_name = match.group(1)
                params_block = match.group(2)

                arguments: dict[str, Any] = {}
                param_pattern = r"<parameter=(\w+)>(.*?)(?:</parameter>|\s*</tool_call>|$)"
                for pmatch in re.finditer(param_pattern, params_block, re.DOTALL):
                    arguments[pmatch.group(1)] = pmatch.group(2).strip()

                if not arguments:
                    kv_pattern = r"(\w+)\s*=\s*([^\s<]+|<[^>]+>)"
                    for kvmatch in re.finditer(kv_pattern, params_block):
                        arguments[kvmatch.group(1)] = kvmatch.group(2).strip()

                if tool_name:
                    tool_calls.append({"name": tool_name, "arguments": arguments})

        return tool_calls

    @staticmethod
    def remove_xml_tool_calls(content: str) -> str:
        """Remove XML/pseudo-XML tool call blocks from content."""
        cleaned = re.sub(
            r"<tool_call>\s*<function=\w+>\s*.*?\s*</function>\s*</tool_call>",
            "",
            content,
            flags=re.DOTALL,
        )
        cleaned = re.sub(
            r"<tool_call>\s*<name>\w+</name>\s*<arguments>.*?</arguments>\s*</tool_call>",
            "",
            cleaned,
            flags=re.DOTALL,
        )
        cleaned = re.sub(
            r"<function=\w+>\s*.*?\s*</tool_call>",
            "",
            cleaned,
            flags=re.DOTALL,
        )
        return cleaned.strip()

    @staticmethod
    def convert_to_api_messages(messages: list[Any]) -> list[dict[str, Any]]:
        """Convert internal messages to API format.

        Delegates to types.message.to_api_format().
        """
        return to_api_format(messages)

    @staticmethod
    def cleanup_orphaned_tool_calls(messages: list[Any]) -> None:
        """Remove ToolUseMessages that have no corresponding ToolResultMessage.

        The API invariant requires every tool_call in an assistant message
        to be followed by a tool response with the same tool_call_id.
        Orphaned ToolUseMessages (no result) cause 400 errors from DeepSeek.
        """
        seen_calls: set[str] = set()
        orphaned_indices: list[int] = []

        for msg in messages:
            if isinstance(msg, ToolResultMessage):
                seen_calls.add(msg.tool_use_id)

        for i, msg in enumerate(messages):
            if isinstance(msg, ToolUseMessage):
                if msg.tool_use_id not in seen_calls:
                    orphaned_indices.append(i)

        if orphaned_indices:
            logger.warning(
                "Cleaning up %d orphaned ToolUseMessages (no matching ToolResultMessage)",
                len(orphaned_indices),
            )
            for i in reversed(orphaned_indices):
                del messages[i]
