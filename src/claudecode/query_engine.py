"""Query engine for managing conversation with LLM."""

import asyncio
import json
from typing import Any, AsyncIterator, Callable
from dataclasses import dataclass, field
from uuid import uuid4

from .types.message import (
    MessageType, UserMessage, AssistantMessage, 
    ToolUseMessage, ToolResultMessage, SystemMessage
)
from .tools.base import Tool, ToolUseContext, Tools
from .tools.registry import assemble_tool_pool
from .state.app_state import AppState
from .utils.model_client import ModelClient, Message as APIMessage, ToolCall, get_model_client


@dataclass
class QueryEngineConfig:
    """Configuration for query engine."""
    cwd: str
    tools: Tools = field(default_factory=list)
    commands: list[Any] = field(default_factory=list)
    can_use_tool: Callable | None = None
    get_app_state: Callable[[], AppState] | None = None
    set_app_state: Callable[[Callable[[AppState], AppState]], None] | None = None
    custom_system_prompt: str | None = None
    max_turns: int = 50


@dataclass
class QueryResult:
    """Result from query."""
    message: MessageType
    is_complete: bool = False


class QueryEngine:
    """Engine for managing queries to LLM.
    
    This class is responsible for:
    - Managing conversation history
    - Streaming responses from LLM
    - Detecting tool calls
    
    Tool execution is handled externally (e.g., by REPL) to avoid
    tight coupling and allow for permission checking.
    """
    
    def __init__(self, config: QueryEngineConfig):
        self.config = config
        self.messages: list[MessageType] = []
        self.client = get_model_client()
        self.abort_event = asyncio.Event()
    
    def _build_system_message(self) -> SystemMessage:
        """Build system message."""
        if self.config.custom_system_prompt:
            content = self.config.custom_system_prompt
        else:
            content = self._get_default_system_prompt()
        
        return SystemMessage(content=content)
    
    def _get_default_system_prompt(self) -> str:
        """Get default system prompt for programming assistant."""
        return """You are ClaudeDecode, an AI programming assistant. Your goal is to help users write, analyze, and improve code.

## Core Capabilities

1. **Code Generation**: Write code in any language based on user requirements
2. **Code Analysis**: Review code for bugs, performance issues, best practices  
3. **File Operations**: Read, write, and edit files in the workspace
4. **Shell Execution**: Run commands, scripts, and build tools

## Available Tools

- **FileRead**: Read file contents to understand existing code
- **FileWrite**: Create new files with generated code
- **FileEdit**: Modify existing files with precise changes
- **Glob**: Find files matching patterns (e.g., "*.py")
- **Grep**: Search text in files across the codebase
- **Bash**: Execute shell commands, run tests, build projects
- **WebSearch**: Search for documentation and examples

## Guidelines

1. **Use tools proactively** - Actually write files and run commands, don't just describe them
2. **Read before writing** - Check existing files before modifying them
3. **Test your code** - Run the code you write to verify it works
4. **Be specific** - Make precise, targeted file changes
5. **Show your work** - Explain what you're doing

## Important

When the user asks you to write code, create files, or make changes:
- Use FileWrite to create new files
- Use FileEdit to modify existing files  
- Use Bash to run the code or tests
- The user will be asked for permission before destructive operations

## Response Format

When writing code, wrap it in markdown code blocks with the language specified.
After showing code, offer to save it to a file if appropriate."""
    
    def _tools_to_api_format(self, tools: Tools) -> list[dict[str, Any]]:
        """Convert tools to API format."""
        result = []
        for tool in tools:
            tool_def = {
                "name": tool.name,
                "description": tool.description if isinstance(tool.description, str) else tool.name,
                "input_schema": tool.input_schema.model_json_schema() if hasattr(tool.input_schema, 'model_json_schema') else {"type": "object"}
            }
            result.append(tool_def)
        return result
    
    def _convert_to_api_messages(self, messages: list[MessageType]) -> list[APIMessage]:
        """Convert internal messages to API format."""
        api_messages = []
        
        for msg in messages:
            if isinstance(msg, SystemMessage):
                api_messages.append(APIMessage(role="system", content=msg.content))
            elif isinstance(msg, UserMessage):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                api_messages.append(APIMessage(role="user", content=content))
            elif isinstance(msg, AssistantMessage):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                api_messages.append(APIMessage(role="assistant", content=content))
            elif isinstance(msg, ToolResultMessage):
                api_messages.append(APIMessage(
                    role="tool",
                    content=msg.content if isinstance(msg.content, str) else json.dumps(msg.content),
                    tool_call_id=msg.tool_use_id,
                    name=msg.tool_use_id
                ))
        
        return api_messages
    
    async def submit_message(
        self,
        prompt: str,
        options: dict[str, Any] | None = None
    ) -> AsyncIterator[QueryResult]:
        """Submit a message and get streaming results.
        
        Yields:
            QueryResult with message content. Tool calls are yielded as
            ToolUseMessage objects. The caller is responsible for executing
            tools and calling submit_message again with tool results.
        """
        options = options or {}
        
        # Add user message
        user_msg = UserMessage(content=prompt)
        self.messages.append(user_msg)
        yield QueryResult(message=user_msg, is_complete=False)
        
        # Build API messages
        api_messages = []
        if len(self.messages) == 1:
            system_msg = self._build_system_message()
            api_messages.append(APIMessage(role="system", content=system_msg.content))
        
        api_messages.extend(self._convert_to_api_messages(self.messages))
        
        # Get available tools
        tools = self.config.tools if self.config.tools else []
        
        # Stream response
        accumulated_content = ""
        pending_tool_calls: list[ToolCall] = []
        current_tool_call: dict[int, dict] = {}  # Accumulate tool call parts
        
        async for chunk in self.client.chat_completion(
            messages=api_messages,
            tools=self._tools_to_api_format(tools) if tools else None,
            stream=True
        ):
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            finish_reason = chunk.get("choices", [{}])[0].get("finish_reason")
            
            # Handle content
            content = delta.get("content")
            if content:
                accumulated_content += content
                partial_msg = AssistantMessage(content=content)
                yield QueryResult(message=partial_msg, is_complete=False)
            
            # Handle tool calls (accumulate across chunks)
            if delta.get("tool_calls"):
                for tc in delta["tool_calls"]:
                    idx = tc.get("index", 0)
                    
                    if idx not in current_tool_call:
                        current_tool_call[idx] = {"id": "", "name": "", "arguments": ""}
                    
                    if tc.get("id"):
                        current_tool_call[idx]["id"] = tc["id"]
                    if tc.get("function", {}).get("name"):
                        current_tool_call[idx]["name"] = tc["function"]["name"]
                    if tc.get("function", {}).get("arguments"):
                        current_tool_call[idx]["arguments"] += tc["function"]["arguments"]
            
            if finish_reason:
                break
        
        # Final assistant message
        if accumulated_content:
            assistant_msg = AssistantMessage(content=accumulated_content)
            self.messages.append(assistant_msg)
            yield QueryResult(message=assistant_msg, is_complete=True)
        
        # Parse and yield tool calls
        for idx, tc_data in current_tool_call.items():
            try:
                arguments = json.loads(tc_data.get("arguments", "{}"))
            except json.JSONDecodeError:
                arguments = {}
            
            tool_call = ToolCall(
                id=tc_data.get("id", ""),
                name=tc_data.get("name", ""),
                arguments=arguments
            )
            pending_tool_calls.append(tool_call)
            
            tool_use_msg = ToolUseMessage(
                tool_use_id=tool_call.id,
                name=tool_call.name,
                input=tool_call.arguments
            )
            self.messages.append(tool_use_msg)
            yield QueryResult(message=tool_use_msg, is_complete=False)
    
    def add_tool_result(self, tool_use_id: str, content: str, is_error: bool = False) -> None:
        """Add a tool result to the conversation history.
        
        Call this after executing a tool, then call submit_message again
        to let the LLM continue with the tool result.
        """
        tool_result_msg = ToolResultMessage(
            tool_use_id=tool_use_id,
            content=content,
            is_error=is_error
        )
        self.messages.append(tool_result_msg)
    
    def abort(self) -> None:
        """Abort current query."""
        self.abort_event.set()
    
    def clear_history(self) -> None:
        """Clear conversation history."""
        self.messages.clear()


def create_query_engine(config: QueryEngineConfig) -> QueryEngine:
    """Create a query engine."""
    return QueryEngine(config)
