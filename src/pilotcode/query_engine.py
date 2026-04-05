"""Query engine for managing conversation with LLM."""

import asyncio
import json
from typing import Any, AsyncIterator, Callable
from dataclasses import dataclass, field
from uuid import uuid4

from .types.message import (
    MessageType, UserMessage, AssistantMessage, 
    ToolUseMessage, ToolResultMessage, SystemMessage,
    serialize_messages, deserialize_messages,
)
from .tools.base import Tool, ToolUseContext, Tools
from .tools.registry import assemble_tool_pool
from .state.app_state import AppState
from .utils.model_client import ModelClient, Message as APIMessage, ToolCall, get_model_client
from .services.token_estimation import get_token_estimator, TokenEstimator
from .services.context_compression import get_context_compressor, CompressionResult
from .services.tool_orchestrator import get_tool_orchestrator, ToolOrchestrator


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
    auto_compact: bool = False
    max_tokens: int = 4000
    cache_tool_results: bool = False


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
        
        # Initialize services
        self._token_estimator = get_token_estimator()
        self._context_compressor = get_context_compressor()
        if config.cache_tool_results:
            self._tool_orchestrator = get_tool_orchestrator()
        else:
            self._tool_orchestrator = None
    
    def _build_system_message(self) -> SystemMessage:
        """Build system message."""
        if self.config.custom_system_prompt:
            content = self.config.custom_system_prompt
        else:
            content = self._get_default_system_prompt()
        
        return SystemMessage(content=content)
    
    def _get_default_system_prompt(self) -> str:
        """Get default system prompt for programming assistant."""
        return """You are PilotCode, an AI programming assistant. Your goal is to help users write, analyze, and improve code.

## Core Capabilities

1. **Code Generation**: Write code in any language based on user requirements
2. **Code Analysis**: Review code for bugs, performance issues, best practices  
3. **File Operations**: Read, write, and edit files in the workspace
4. **Shell Execution**: Run commands, scripts, and build tools

## Available Tools

- **FileRead**: Read file contents to understand existing code - ALWAYS USE THIS to read files before analyzing or modifying them
- **FileWrite**: Create new files with generated code
- **FileEdit**: Modify existing files with precise changes
- **Glob**: Find files matching patterns (e.g., "*.py") - After finding files, you MUST read them with FileRead
- **Grep**: Search text in files across the codebase
- **Bash**: Execute shell commands, run tests, build projects
- **WebSearch**: Search for documentation and examples

## CRITICAL INSTRUCTIONS

1. **ALWAYS READ FILES** - When asked to analyze code, you MUST:
   - First use Glob to find relevant files
   - Then use FileRead to read the content of EACH file
   - Only after reading can you provide analysis

2. **MULTI-STEP WORKFLOW** - For complex tasks:
   - Step 1: Discover files (Glob/Bash)
   - Step 2: Read relevant files (FileRead)
   - Step 3: Execute commands as needed (Bash)
   - Step 4: Provide comprehensive response based on actual file contents

3. **Use tools proactively** - Actually write files and run commands, don't just describe them
4. **Read before writing** - Check existing files before modifying them
5. **TEST YOUR CODE** - When asked to "测试" (test), you MUST use Bash to run the code:
   - For Python: `python filename.py` or `python -m pytest`
   - For tests: Run the actual test command
   - Do NOT just read the code and say "看起来可以运行" - actually run it!
6. **Be specific** - Make precise, targeted file changes
7. **Show your work** - Explain what you're doing

8. **PARALLEL TOOL CALLS** - When a user asks for multiple things in one sentence, make ALL necessary tool calls at once:
   - "查看目录并读取代码" -> Call Glob AND FileRead together
   - "查找并测试代码" -> Call Grep AND Bash together
   - "分析项目结构" -> Call Glob AND multiple FileRead together

## Example Workflow for Code Analysis

User: "分析这个项目的代码"

Your response should be:
1. Use Glob to find files: `Glob(pattern="*.py")`
2. After getting file list, use FileRead for each file: `FileRead(path="app.py")`
3. Continue reading all relevant files
4. Only then provide analysis based on actual file contents

DO NOT just list files and say "这些文件存在". You MUST read them.

## Example: Multiple Tasks in One Sentence

User: "查看 blog_app 目录有哪些 Python 文件并读取 app.py"

Your response should be (make both calls at once):
- Glob(pattern="blog_app/*.py")  
- FileRead(path="blog_app/app.py")

## Example: Testing Code (CRITICAL)

User: "测试这个代码" or "analyze and test"

Your response MUST include:
1. Read the code files first
2. **RUN THE CODE** using Bash to actually test it:
   - `Bash(command="python app.py")` 
   - `Bash(command="python -m pytest")`
   - Or run the appropriate test command

DON'T STOP after reading files. You MUST execute the code to test it!"""
    
    def _tools_to_api_format(self, tools: Tools) -> list[dict[str, Any]]:
        """Convert tools to API format."""
        result = []
        
        # Static descriptions for built-in tools
        static_descriptions = {
            "Bash": "Execute bash commands in the working directory. Use for running code, tests, git commands, etc.",
            "FileRead": "Read the contents of a file. ALWAYS use this to read files before analyzing or modifying them.",
            "FileWrite": "Create a new file with the specified content. Will fail if file already exists (read first).",
            "FileEdit": "Edit an existing file by replacing specific content. Use for precise changes.",
            "Glob": "Find files matching a pattern (e.g., '*.py', 'src/**/*.js'). After finding files, you MUST read them with FileRead.",
            "Grep": "Search for text patterns in files across the codebase. Useful for finding specific code.",
            "AskUser": "Ask the user a question when you need clarification or additional information.",
            "TodoWrite": "Manage a todo list. Use to track tasks and progress.",
            "WebSearch": "Search the web for documentation, examples, or current information.",
            "WebFetch": "Fetch the content of a specific webpage.",
            "Agent": "Spawn a sub-agent to handle a specific task independently.",
            "TaskCreate": "Create a background task for long-running operations.",
            "TaskList": "List all background tasks and their status.",
            "TaskGet": "Get details about a specific background task.",
            "TaskStop": "Stop a running background task.",
            "TaskUpdate": "Update task progress or status.",
            "Config": "Read or write configuration settings.",
            "LSP": "Use Language Server Protocol for code intelligence (go to definition, find references, etc.)",
            "NotebookEdit": "Edit Jupyter notebook files (.ipynb).",
            "PowerShell": "Execute PowerShell commands (cross-platform support).",
        }
        
        for tool in tools:
            # Use static description if available, otherwise try to get from tool
            if tool.name in static_descriptions:
                description = static_descriptions[tool.name]
            elif isinstance(tool.description, str):
                description = tool.description
            else:
                # Fallback for callable descriptions
                description = f"{tool.name} tool for file operations and code assistance"
            
            tool_def = {
                "name": tool.name,
                "description": description,
                "input_schema": tool.input_schema.model_json_schema() if hasattr(tool.input_schema, 'model_json_schema') else {"type": "object"}
            }
            result.append(tool_def)
        return result
    
    def _convert_to_api_messages(self, messages: list[MessageType]) -> list[APIMessage]:
        """Convert internal messages to API format."""
        api_messages = []
        
        # Track pending tool calls that need to be attached to assistant message
        # Using ToolCall objects as expected by model_client
        pending_tool_calls: list[ToolCall] = []
        
        for i, msg in enumerate(messages):
            if isinstance(msg, SystemMessage):
                api_messages.append(APIMessage(role="system", content=msg.content))
            elif isinstance(msg, UserMessage):
                # Flush any pending tool calls before user message
                if pending_tool_calls:
                    api_messages.append(APIMessage(
                        role="assistant",
                        content="",
                        tool_calls=pending_tool_calls
                    ))
                    pending_tool_calls = []
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                api_messages.append(APIMessage(role="user", content=content))
            elif isinstance(msg, AssistantMessage):
                # Flush pending tool calls if any
                if pending_tool_calls:
                    api_messages.append(APIMessage(
                        role="assistant",
                        content=msg.content or "",
                        tool_calls=pending_tool_calls
                    ))
                    pending_tool_calls = []
                else:
                    content = msg.content if isinstance(msg.content, str) else str(msg.content)
                    api_messages.append(APIMessage(role="assistant", content=content))
            elif isinstance(msg, ToolUseMessage):
                # Accumulate tool calls to attach to next assistant message
                pending_tool_calls.append(ToolCall(
                    id=msg.tool_use_id,
                    name=msg.name,
                    arguments=msg.input
                ))
            elif isinstance(msg, ToolResultMessage):
                # Flush pending tool calls before tool result
                if pending_tool_calls:
                    api_messages.append(APIMessage(
                        role="assistant",
                        content="",
                        tool_calls=pending_tool_calls
                    ))
                    pending_tool_calls = []
                api_messages.append(APIMessage(
                    role="tool",
                    content=msg.content if isinstance(msg.content, str) else json.dumps(msg.content),
                    tool_call_id=msg.tool_use_id,
                    name=msg.tool_use_id
                ))
        
        # Flush any remaining pending tool calls
        if pending_tool_calls:
            api_messages.append(APIMessage(
                role="assistant",
                content="",
                tool_calls=pending_tool_calls
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
    
    def count_tokens(self) -> int:
        """Count tokens in current conversation.
        
        Uses the token estimator service for accurate counting.
        """
        return self._token_estimator.estimate_messages([
            {"role": getattr(m, "type", "unknown"), "content": str(m.content)}
            for m in self.messages
        ])
    
    def get_token_budget(self) -> dict[str, Any]:
        """Get current token budget status."""
        return self._token_estimator.get_budget_status(
            self.count_tokens(),
            self.config.max_tokens
        )
    
    def track_cost(self, tokens: int, cost_usd: float) -> None:
        """Track cost for this session.
        
        This accumulates into app_state for reporting.
        """
        if self.config.get_app_state:
            state = self.config.get_app_state()
            state.total_tokens += tokens
            state.total_cost_usd += cost_usd
            if self.config.set_app_state:
                self.config.set_app_state(lambda s: state)
    
    async def smart_compact(self) -> CompressionResult | None:
        """Intelligently compress conversation using summarization.
        
        Returns compression result or None if not needed.
        """
        if not self.config.auto_compact:
            return None
        
        token_count = self.count_tokens()
        if token_count < self.config.max_tokens:
            return None
        
        # Use smart compression
        result = await self._context_compressor.compress(
            self.messages,
            summarizer=None  # Could pass Brief tool here
        )
        
        if result.summary or result.removed_indices:
            self.messages = [
                m for i, m in enumerate(self.messages)
                if i not in result.removed_indices
            ]
            # If we have a summary, prepend it
            if result.summary:
                from .types.message import SystemMessage
                self.messages.insert(1, SystemMessage(
                    content=f"[Earlier conversation]: {result.summary}"
                ))
        
        return result
    
    def auto_compact_if_needed(self) -> bool:
        """Auto-compact conversation if token count exceeds limit.
        
        Returns True if compaction was performed.
        
        This is the synchronous fallback that uses simple compaction.
        For smart compression with summarization, use smart_compact().
        """
        if not self.config.auto_compact:
            return False
        
        token_count = self.count_tokens()
        if token_count < self.config.max_tokens:
            return False
        
        # Use simple priority-based compaction
        compressed = self._context_compressor.simple_compact(
            self.messages,
            keep_recent=6
        )
        
        if len(compressed) < len(self.messages):
            self.messages = compressed
            return True
        return False
    
    def clear_history(self) -> None:
        """Clear conversation history."""
        self.messages.clear()
    
    def save_session(self, path: str) -> None:
        """Save conversation session to disk."""
        import os
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        data = {
            "version": 1,
            "cwd": self.config.cwd,
            "custom_system_prompt": self.config.custom_system_prompt,
            "max_turns": self.config.max_turns,
            "messages": serialize_messages(self.messages),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    def load_session(self, path: str) -> bool:
        """Load conversation session from disk.
        
        Returns True if loaded successfully.
        """
        import os
        if not os.path.exists(path):
            return False
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.messages = deserialize_messages(data.get("messages", []))
        self.config.cwd = data.get("cwd", self.config.cwd)
        if data.get("custom_system_prompt"):
            self.config.custom_system_prompt = data["custom_system_prompt"]
        self.config.max_turns = data.get("max_turns", self.config.max_turns)
        return True


def create_query_engine(config: QueryEngineConfig) -> QueryEngine:
    """Create a query engine."""
    return QueryEngine(config)
