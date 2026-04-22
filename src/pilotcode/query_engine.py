"""Query engine for managing conversation with LLM."""

import asyncio
import json
from typing import Any, AsyncIterator, Callable
from dataclasses import dataclass, field

from .types.message import (
    MessageType,
    UserMessage,
    AssistantMessage,
    ToolUseMessage,
    ToolResultMessage,
    SystemMessage,
    serialize_messages,
    deserialize_messages,
)
from .tools.base import Tools
from .state.app_state import AppState
from .utils.model_client import Message as APIMessage, ToolCall, get_model_client
from .services.token_estimation import get_token_estimator
from .services.context_compression import get_context_compressor, CompressionResult
from .services.intelligent_compact import (
    IntelligentContextCompactor,
    CompactConfig,
)
from .services.tool_orchestrator import get_tool_orchestrator
from .utils.models_config import get_model_context_window


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
    auto_compact: bool = True
    max_tokens: int = 0  # 0 = auto-detect from model config
    cache_tool_results: bool = False
    on_notify: Callable[[str, dict[str, Any]], None] | None = None


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

        # Auto-detect max_tokens from model context window if not set
        if self.config.max_tokens <= 0:
            ctx = get_model_context_window()
            self.config.max_tokens = ctx

        # Initialize services
        self._token_estimator = get_token_estimator()
        self._context_compressor = get_context_compressor()

        # Create a dedicated compactor instance configured with our max_tokens
        compact_config = CompactConfig()
        if self.config.max_tokens > 0:
            # Use max(1, ...) to avoid 0 which triggers auto-detection in the compactor
            compact_config.compact_threshold = max(1, int(self.config.max_tokens * 0.8))
            compact_config.critical_threshold = max(1, int(self.config.max_tokens * 0.95))
        self._intelligent_compactor = IntelligentContextCompactor(config=compact_config)

        if config.cache_tool_results:
            self._tool_orchestrator = get_tool_orchestrator()
        else:
            self._tool_orchestrator = None

        # Compaction tracking
        self._last_compaction_message_count = 0
        self._compaction_count = 0

    def _build_system_message(self) -> SystemMessage:
        """Build system message with runtime context."""
        if self.config.custom_system_prompt:
            content = self.config.custom_system_prompt
        else:
            content = self._get_default_system_prompt()

        # Add runtime context (OS, cwd, etc.)
        context = self._get_runtime_context()
        if context:
            content = context + "\n\n" + content

        return SystemMessage(content=content)

    def _get_runtime_context(self) -> str:
        """Get runtime context (OS, cwd, etc.) for system prompt."""
        import os
        import sys
        import platform

        context_lines = ["## Runtime Environment"]

        # OS information
        os_name = platform.system()
        os_version = platform.release()
        context_lines.append(f"- **OS**: {os_name} {os_version}")
        context_lines.append(f"- **Platform**: {sys.platform}")

        # Current working directory
        cwd = self.config.cwd or os.getcwd()
        context_lines.append(f"- **Current Directory**: {cwd}")

        # Shell information
        if sys.platform == "win32":
            shell = os.environ.get("COMSPEC", "cmd.exe")
            context_lines.append(f"- **Default Shell**: {shell}")
            context_lines.append(
                "- **Command Notes**: Use Windows commands (e.g., `dir`, `cd`, `type`)"
            )
        else:
            shell = os.environ.get("SHELL", "/bin/bash")
            context_lines.append(f"- **Default Shell**: {shell}")
            context_lines.append("- **Command Notes**: Use Unix commands (e.g., `ls`, `cd`, `cat`)")

        return "\n".join(context_lines)

    def _get_default_system_prompt(self) -> str:
        """Get default system prompt for programming assistant."""
        return """You are PilotCode, an AI programming assistant. Your goal is to help users write, analyze, and improve code.

When users ask about current time/date (e.g., '现在几点了', 'what time is it'), you MUST use the Bash tool to get the accurate time:
- For time: `Bash(command="date")` or `Bash(command="date '+%Y-%m-%d %H:%M:%S'")`
- For timezone: `Bash(command="date +%Z")`
Do NOT rely on any time information in the system prompt as it may be outdated.

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
- **CodeSearch**: Intelligent code search using symbols, semantics, or regex. FOR LARGE PROJECTS, USE THIS FIRST to narrow down relevant files before using FileRead/Grep.
- **CodeIndex**: Build or update the codebase index for fast CodeSearch.
- **Bash**: Execute shell commands, run tests, build projects
- **WebSearch**: Search for documentation and examples

## CRITICAL INSTRUCTIONS

1. **USE CODESEARCH FIRST** - When looking for code in a project with more than ~50 files:
   - ALWAYS start with `CodeSearch` (symbol or semantic search) to locate relevant functions/classes.
   - Use `CodeSearch` with `search_type="symbol"` for exact symbol names (e.g. `FilePathField`, `merge`).
   - Use `CodeSearch` with `search_type="semantic"` for concepts (e.g. "media merge conflict").
   - Only fall back to `Glob` or `Grep` if `CodeSearch` returns nothing useful.

2. **ALWAYS READ FILES** - Once you've narrowed down the files with CodeSearch/Glob/Grep:
   - Use `FileRead` to read the content of EACH relevant file before modifying it.
   - Only after reading can you provide analysis.

3. **MULTI-STEP WORKFLOW** - For complex tasks:
   - Step 1: Discover files (`CodeSearch` > `Glob`/`Grep`)
   - Step 2: Read relevant files (`FileRead`)
   - Step 3: Execute commands as needed (`Bash`)
   - Step 4: Provide comprehensive response based on actual file contents

3. **Use tools proactively** - Actually write files and run commands, don't just describe them
4. **Read before writing** - Check existing files before modifying them
5. **TEST YOUR CODE** - When asked to "测试" (test), you MUST use Bash to run the code:
   - For Python: `python filename.py` or `python -m pytest`
   - For tests: Run the actual test command
   - Do NOT just read the code and say "看起来可以运行" - actually run it!
6. **Be specific** - Make precise, targeted file changes
7. **Show your work** - Explain what you're doing
8. **USE EXACT FILE PATHS** - When rewriting or updating an existing file, you MUST use the EXACT original file path. Do NOT create files with '_new', '_backup', '_fixed', or any other suffixes. Always write directly to the target file path.

8. **PARALLEL TOOL CALLS** - When a user asks for multiple things in one sentence, make ALL necessary tool calls at once:
   - "查看目录并读取代码" -> Call Glob AND FileRead together
   - "查找并测试代码" -> Call Grep AND Bash together
   - "分析项目结构" -> Call Glob AND multiple FileRead together

9. **MERGE/CONCATENATE FILES** - To combine multiple files into one:
   - Unix/Linux: `Bash(command="cat file1.txt file2.txt > output.txt")`
   - Windows: `Bash(command="type file1.txt file2.txt > output.txt")`

10. **WRITE PYTHON SCRIPTS FOR COMPLEX TASKS** - When no tool exists for a task, or tools are not installed:
    - Write a Python script to perform the task using FileWrite
    - Execute the script using Bash: `Bash(command="python script.py")`
    - Examples: complex data processing, file format conversion, API calls without curl, custom algorithms, etc.
    - Clean up temporary scripts after execution if no longer needed

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

## Example: Merge/Concatenate Files

User: "把 file1.txt 和 file2.txt 合并到 output.txt"

Your response should be:
1. Read both files: `FileRead(path="file1.txt")` and `FileRead(path="file2.txt")`
2. Then write merged content: `FileWrite(path="output.txt", content=file1_content + "\n" + file2_content)`

OR use Bash (platform-specific):
- Unix: `Bash(command="cat file1.txt file2.txt > output.txt")`
- Windows: `Bash(command="type file1.txt file2.txt > output.txt")`

## Example: Writing Python Script for Complex Task

User: "Convert all JSON files in the data folder to CSV format"

Your response should be:
1. Write a Python script using FileWrite to handle the conversion:
   ```
   FileWrite(path="convert_json_to_csv.py", content='''
   import json
   import csv
   import os
   from pathlib import Path

   data_dir = Path("data")
   for json_file in data_dir.glob("*.json"):
       with open(json_file, 'r') as f:
           data = json.load(f)
       
       csv_file = json_file.with_suffix('.csv')
       with open(csv_file, 'w', newline='') as f:
           if data and len(data) > 0:
               writer = csv.DictWriter(f, fieldnames=data[0].keys())
               writer.writeheader()
               writer.writerows(data)
       print(f"Converted {json_file} -> {csv_file}")
   ''')
   ```
2. Execute the script: `Bash(command="python convert_json_to_csv.py")`

## Example: Testing Code (CRITICAL)

User: "测试这个代码" or "analyze and test"

Your response MUST include:
1. Read the code files first
2. **RUN THE CODE** using Bash to actually test it:
   - `Bash(command="python app.py")` 
   - `Bash(command="python -m pytest")`
   - Or run the appropriate test command

DON'T STOP after reading files. You MUST execute the code to test it!

## Code Editing Best Practices (CRITICAL)

When editing code files, you MUST follow these rules to avoid syntax errors and incomplete fixes:

1. **EXACT MATCH for FileEdit** - The `old_string` parameter must match the file content EXACTLY, including all spaces, tabs, and newlines. If unsure, read the file again.
2. **Verify indentation** - Python is indentation-sensitive. Double-check that your replacement maintains or correctly changes the indentation level.
3. **Validate Python syntax after editing** - After any `.py` file edit, immediately run `Bash(command="python -m py_compile <filepath>")` to verify the file is syntactically valid.
4. **Use checklists for multi-file changes** - If a task requires changes in multiple files, explicitly list the files, edit them one by one, and check each off before declaring completion.
5. **Review with git diff** - Before finishing, run `Bash(command="git diff")` to review all changes and ensure nothing was accidentally modified or left out.
6. **Rollback on failure** - If a syntax check fails or an edit looks wrong, fix it immediately. Do not leave broken code in the workspace.
7. **Test local changes with correct import path** - When running tests after editing source code (especially for libraries with a `src/` layout), ensure the local modified version is loaded instead of a system-installed package. Use `PYTHONPATH=src python -m pytest` or `python -m pip install -e .` before testing."""

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
            "CodeIndex": "Index the codebase for intelligent search. Run this first when working with a new repository.",
            "CodeSearch": "Search code using semantic (natural language), symbol, or regex search.",
            "CodeContext": "Build code context for a query using RAG. Use this to understand large codebases.",
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
                "input_schema": (
                    tool.input_schema.model_json_schema()
                    if hasattr(tool.input_schema, "model_json_schema")
                    else {"type": "object"}
                ),
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
                    api_messages.append(
                        APIMessage(role="assistant", content="", tool_calls=pending_tool_calls)
                    )
                    pending_tool_calls = []
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                api_messages.append(APIMessage(role="user", content=content))
            elif isinstance(msg, AssistantMessage):
                # Flush pending tool calls if any
                if pending_tool_calls:
                    api_messages.append(
                        APIMessage(
                            role="assistant",
                            content=msg.content or "",
                            tool_calls=pending_tool_calls,
                        )
                    )
                    pending_tool_calls = []
                else:
                    content = msg.content if isinstance(msg.content, str) else str(msg.content)
                    api_messages.append(APIMessage(role="assistant", content=content))
            elif isinstance(msg, ToolUseMessage):
                # Accumulate tool calls to attach to next assistant message
                pending_tool_calls.append(
                    ToolCall(id=msg.tool_use_id, name=msg.name, arguments=msg.input)
                )
            elif isinstance(msg, ToolResultMessage):
                # Flush pending tool calls before tool result
                if pending_tool_calls:
                    api_messages.append(
                        APIMessage(role="assistant", content="", tool_calls=pending_tool_calls)
                    )
                    pending_tool_calls = []
                api_messages.append(
                    APIMessage(
                        role="tool",
                        content=(
                            msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
                        ),
                        tool_call_id=msg.tool_use_id,
                        name=msg.tool_use_id,
                    )
                )

        # Flush any remaining pending tool calls
        if pending_tool_calls:
            api_messages.append(
                APIMessage(role="assistant", content="", tool_calls=pending_tool_calls)
            )

        return api_messages

    async def submit_message(
        self, prompt: str, options: dict[str, Any] | None = None
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

        # Auto-compact if needed before sending to API
        if self.config.auto_compact:
            self.auto_compact_if_needed()

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
            stream=True,
            temperature=options.get("temperature", 0.7),
        ):
            # Check for cancellation during streaming
            try:
                await asyncio.sleep(0)  # Yield control to allow cancellation
            except asyncio.CancelledError:
                raise
            
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
                id=tc_data.get("id", ""), name=tc_data.get("name", ""), arguments=arguments
            )
            pending_tool_calls.append(tool_call)

            tool_use_msg = ToolUseMessage(
                tool_use_id=tool_call.id, name=tool_call.name, input=tool_call.arguments
            )
            self.messages.append(tool_use_msg)
            yield QueryResult(message=tool_use_msg, is_complete=False)

    # Threshold for truncating individual tool results at ingestion time.
    # Results longer than this are truncated to _TOOL_RESULT_TRUNC_LEN.
    _TOOL_RESULT_MAX_LEN: int = 4000
    _TOOL_RESULT_TRUNC_LEN: int = 2000

    def add_tool_result(self, tool_use_id: str, content: str, is_error: bool = False) -> None:
        """Add a tool result to the conversation history.

        Long results (>4KB) are truncated to ~2KB to prevent a single
        tool output from exploding the context window.  The full result
        is still available locally (e.g. in tool orchestrator cache).

        Call this after executing a tool, then call submit_message again
        to let the LLM continue with the tool result.
        """
        if isinstance(content, str) and len(content) > self._TOOL_RESULT_MAX_LEN:
            content = (
                content[: self._TOOL_RESULT_TRUNC_LEN]
                + f"\n... [truncated, {len(content)} chars total]"
            )

        tool_result_msg = ToolResultMessage(
            tool_use_id=tool_use_id, content=content, is_error=is_error
        )
        self.messages.append(tool_result_msg)

    def abort(self) -> None:
        """Abort current query."""
        self.abort_event.set()

    def count_tokens(self) -> int:
        """Count tokens in current conversation.

        Uses the token estimator service for accurate counting.
        """
        api_messages = []
        for m in self.messages:
            # Get content based on message type
            if hasattr(m, "content"):
                content = str(m.content)
            elif hasattr(m, "name") and hasattr(m, "input"):
                # ToolUseMessage - serialize name and input
                content = f"Tool: {m.name}\nInput: {m.input}"
            else:
                content = str(m)

            api_messages.append({"role": getattr(m, "type", "unknown"), "content": content})

        return self._token_estimator.estimate_messages(api_messages)

    def get_token_budget(self) -> dict[str, Any]:
        """Get current token budget status."""
        return self._token_estimator.get_budget_status(self.count_tokens(), self.config.max_tokens)

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

        Triggers at 80% of max_tokens to leave headroom.

        Returns compression result or None if not needed.
        """
        token_count = self.count_tokens()
        threshold = int(self.config.max_tokens * 0.8)
        if token_count < threshold:
            return None

        # Use smart compression
        result = await self._context_compressor.compress(
            self.messages, summarizer=None  # Could pass Brief tool here
        )

        if result.summary or result.removed_indices:
            self.messages = [
                m for i, m in enumerate(self.messages) if i not in result.removed_indices
            ]
            # If we have a summary, prepend it
            if result.summary:
                from .types.message import SystemMessage

                self.messages.insert(
                    1, SystemMessage(content=f"[Earlier conversation]: {result.summary}")
                )

        return result

    def auto_compact_if_needed(self) -> bool:
        """Auto-compact conversation if token count exceeds threshold.

        Returns True if compaction was performed.

        Uses intelligent compaction which clears old tool result content
        while preserving conversation structure and key context.
        Falls back to simple compaction if intelligent compaction doesn't
        effectively reduce token usage.

        If compaction is performed and ``on_auto_compact`` is configured,
        the callback is invoked with compaction statistics.
        """
        if not self.config.auto_compact:
            return False

        # Cooldown: don't re-compact if no new messages since last compaction
        current_msg_count = len(self.messages)
        if current_msg_count <= self._last_compaction_message_count:
            return False

        tokens_before = self.count_tokens()
        result = self.intelligent_compact()

        if result.get("compacted", False):
            tokens_after = self.count_tokens()
            if tokens_after < tokens_before:
                if self.config.on_notify:
                    self.config.on_notify(
                        "auto_compact",
                        {
                            "tokens_before": tokens_before,
                            "tokens_after": tokens_after,
                            "tokens_saved": tokens_before - tokens_after,
                            "tool_results_cleared": result.get("tool_results_cleared", 0),
                            "compaction_count": result.get("compaction_count", 0),
                            "fallback": False,
                        },
                    )
                self._last_compaction_message_count = len(self.messages)
                return True

        # Fallback: if still over threshold, use simple compaction
        threshold = int(self.config.max_tokens * 0.8)
        if self.count_tokens() < threshold:
            return False

        compressed = self._context_compressor.simple_compact(self.messages, keep_recent=6)
        if len(compressed) < len(self.messages):
            self.messages = compressed
            tokens_after = self.count_tokens()
            if self.config.on_notify:
                self.config.on_notify(
                    "auto_compact",
                    {
                        "tokens_before": tokens_before,
                        "tokens_after": tokens_after,
                        "tokens_saved": tokens_before - tokens_after,
                        "tool_results_cleared": 0,
                        "compaction_count": self._compaction_count,
                        "fallback": True,
                    },
                )
            self._last_compaction_message_count = len(self.messages)
            return True
        return False

    def intelligent_compact(self) -> dict[str, Any]:
        """Intelligently compact conversation using ClaudeCode-style compaction.

        This method:
        1. Clears old tool results but keeps markers
        2. Summarizes conversation context
        3. Preserves recent message history

        Returns:
            Compaction statistics
        """
        from .types.message import SystemMessage

        token_count = self.count_tokens()

        # Check if compaction is needed
        if not self._intelligent_compactor.should_compact(self.messages, token_count):
            return {
                "compacted": False,
                "reason": "Compaction not needed",
                "token_count": token_count,
            }

        # Generate summary before compaction
        summary = self._intelligent_compactor.generate_structured_summary(
            self.messages, include_files=True, include_errors=True
        )

        # Perform compaction
        result = self._intelligent_compactor.compact_messages(self.messages, token_count)

        # Update messages from compaction result
        if result.messages:
            self.messages = list(result.messages)

        # Add summary as system message if we cleared content
        if result.tool_results_cleared > 0:
            summary_text = f"""[Conversation Context Summary]
Project: {summary.get('primary_request', 'N/A')[:100]}
Files examined: {', '.join(summary.get('files_examined', []))}
Files modified: {', '.join(summary.get('files_modified', []))}
Errors: {len(summary.get('errors_encountered', []))}
"""
            # Insert after system message or at beginning
            if self.messages and isinstance(self.messages[0], SystemMessage):
                self.messages.insert(1, SystemMessage(content=summary_text))
            else:
                self.messages.insert(0, SystemMessage(content=summary_text))

        self._compaction_count += 1

        return {
            "compacted": True,
            "original_messages": result.original_messages,
            "compacted_messages": len(self.messages),
            "original_tokens": result.original_tokens,
            "compacted_tokens": result.compacted_tokens,
            "tool_results_cleared": result.tool_results_cleared,
            "compaction_count": self._compaction_count,
        }

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
