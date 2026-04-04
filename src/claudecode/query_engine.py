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
    """Engine for managing queries to LLM."""
    
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
3. **Testing**: Write and run tests to verify code correctness
4. **File Operations**: Read, write, and edit files in the workspace
5. **Shell Execution**: Run commands, scripts, and build tools

## Available Tools

- **Bash**: Execute shell commands, run scripts, build projects
- **FileRead**: Read file contents to understand existing code
- **FileWrite**: Create new files with generated code
- **FileEdit**: Modify existing files with precise changes
- **Glob**: Find files matching patterns (e.g., "*.py")
- **Grep**: Search text in files across the codebase
- **Agent**: Spawn specialized agents for complex tasks

## Guidelines

1. **Always use tools proactively** - Don't just describe what to do, actually do it
2. **Read before writing** - Check existing files before modifying them
3. **Test your code** - Run the code you write to verify it works
4. **Be specific** - When editing files, make precise, targeted changes
5. **Show your work** - Explain what you're doing and why

## Response Format

When writing code:
1. Present the code in properly formatted code blocks
2. Explain how the code works
3. Show example usage
4. Offer to save the file or make modifications

When analyzing code:
1. Read the relevant files
2. Identify issues or improvements
3. Provide specific recommendations
4. Offer to implement the fixes

Be helpful, thorough, and practical. Focus on delivering working solutions."""
    
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
            elif isinstance(msg, ToolUseMessage):
                # Tool use is embedded in assistant message
                pass
            elif isinstance(msg, ToolResultMessage):
                api_messages.append(APIMessage(
                    role="tool",
                    content=msg.content if isinstance(msg.content, str) else json.dumps(msg.content),
                    tool_call_id=msg.tool_use_id,
                    name=msg.tool_use_id  # Should be tool name
                ))
        
        return api_messages
    
    async def submit_message(
        self,
        prompt: str,
        options: dict[str, Any] | None = None
    ) -> AsyncIterator[QueryResult]:
        """Submit a message and get streaming results."""
        options = options or {}
        
        # Add user message
        user_msg = UserMessage(content=prompt)
        self.messages.append(user_msg)
        yield QueryResult(message=user_msg, is_complete=False)
        
        # Build system message if first interaction
        api_messages = []
        if len(self.messages) == 1:
            system_msg = self._build_system_message()
            api_messages.append(APIMessage(role="system", content=system_msg.content))
        
        # Add conversation history
        api_messages.extend(self._convert_to_api_messages(self.messages))
        
        # Get tools
        tools = self.config.tools if self.config.tools else []
        
        # Stream response
        accumulated_content = ""
        tool_calls: list[ToolCall] = []
        
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
                # API returns delta content (incremental)
                accumulated_content += content
                
                # Yield the delta content for streaming display
                partial_msg = AssistantMessage(content=content)
                yield QueryResult(message=partial_msg, is_complete=False)
            
            # Handle tool calls (accumulate across chunks)
            if delta.get("tool_calls"):
                for tc in delta["tool_calls"]:
                    # Tool calls come in chunks, accumulate them
                    idx = tc.get("index", 0)
                    
                    # Extend tool_calls list if needed
                    while len(tool_calls) <= idx:
                        tool_calls.append(ToolCall(id="", name="", arguments={}))
                    
                    # Update tool call data
                    if tc.get("id"):
                        tool_calls[idx].id = tc["id"]
                    if tc.get("function", {}).get("name"):
                        tool_calls[idx].name = tc["function"]["name"]
                    if tc.get("function", {}).get("arguments"):
                        import json
                        try:
                            args = json.loads(tc["function"]["arguments"])
                            tool_calls[idx].arguments.update(args)
                        except json.JSONDecodeError:
                            # Partial JSON, accumulate as string and parse later
                            pass
            
            # Check if stream is complete
            if finish_reason:
                break
        
        # Final assistant message with complete content
        if accumulated_content:
            assistant_msg = AssistantMessage(content=accumulated_content)
            self.messages.append(assistant_msg)
            yield QueryResult(message=assistant_msg, is_complete=True)
        
        # Handle tool calls if any
        if tool_calls:
            for tc in tool_calls:
                tool_use_msg = ToolUseMessage(
                    tool_use_id=tc.id,
                    name=tc.name,
                    input=tc.arguments
                )
                self.messages.append(tool_use_msg)
                yield QueryResult(message=tool_use_msg, is_complete=False)
                
                # Execute tool
                tool_result = await self._execute_tool(tc)
                self.messages.append(tool_result)
                yield QueryResult(message=tool_result, is_complete=False)
            
            # Continue conversation with tool results
            async for result in self.submit_message("", options):
                yield result
    
    async def _execute_tool(self, tool_call: ToolCall) -> ToolResultMessage:
        """Execute a tool call."""
        # Find tool
        tool = None
        for t in self.config.tools:
            if t.name == tool_call.name or tool_call.name in t.aliases:
                tool = t
                break
        
        if tool is None:
            return ToolResultMessage(
                tool_use_id=tool_call.id,
                content=f"Tool '{tool_call.name}' not found",
                is_error=True
            )
        
        # Create context
        context = ToolUseContext(
            get_app_state=self.config.get_app_state,
            set_app_state=self.config.set_app_state
        )
        
        # Parse input
        try:
            input_data = tool.input_schema(**tool_call.arguments)
        except Exception as e:
            return ToolResultMessage(
                tool_use_id=tool_call.id,
                content=f"Invalid input: {str(e)}",
                is_error=True
            )
        
        # Execute
        try:
            result = await tool.call(
                input_data,
                context,
                self.config.can_use_tool or (lambda **kwargs: {"behavior": "allow"}),
                None,
                lambda x: None
            )
            
            if result.is_error:
                return ToolResultMessage(
                    tool_use_id=tool_call.id,
                    content=result.error or "Unknown error",
                    is_error=True
                )
            
            return ToolResultMessage(
                tool_use_id=tool_call.id,
                content=result.output_for_assistant or str(result.data)
            )
        except Exception as e:
            return ToolResultMessage(
                tool_use_id=tool_call.id,
                content=f"Error: {str(e)}",
                is_error=True
            )
    
    def abort(self) -> None:
        """Abort current query."""
        self.abort_event.set()


def create_query_engine(config: QueryEngineConfig) -> QueryEngine:
    """Create a query engine."""
    return QueryEngine(config)
