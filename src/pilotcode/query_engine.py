"""Query engine for managing conversation with LLM."""

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any, AsyncIterator, Callable
from dataclasses import dataclass, field


@dataclass
class TokenUsage:
    """OpenCode-style token usage breakdown.

    Mirrors LanguageModelV2Usage from the AI SDK:
    - prompt_tokens: total input tokens (includes cached)
    - completion_tokens: total output tokens
    - total_tokens: prompt + completion
    - cache_read_tokens: prompt cache read (e.g. Anthropic prompt caching)
    - cache_write_tokens: prompt cache write (e.g. Anthropic cache creation)
    - reasoning_tokens: thinking/reasoning tokens inside completion
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0

    @property
    def adjusted_prompt_tokens(self) -> int:
        """Prompt tokens excluding cache read/write (for cost calculation)."""
        return max(0, self.prompt_tokens - self.cache_read_tokens - self.cache_write_tokens)

    @property
    def output_tokens(self) -> int:
        """Non-reasoning completion tokens."""
        return max(0, self.completion_tokens - self.reasoning_tokens)


logger = logging.getLogger(__name__)

from .types.message import (
    MessageType,
    UserMessage,
    AssistantMessage,
    ToolUseMessage,
    ToolResultMessage,
    SystemMessage,
    serialize_messages,
    deserialize_messages,
    to_api_format,
)
from .tools.base import Tools
from .state.app_state import AppState
from .utils.model_client import (
    ToolCall,
    get_model_client,
    ModelClient,
    ContextWindowError,
    RateLimitError,
)
from .services.token_estimation import get_token_estimator
from .services.precise_tokenizer import get_precise_tokenizer
from .services.stream_events import EventBus, StreamEvent
from .services.context_compression import get_context_compressor, CompressionResult
from .services.intelligent_compact import (
    IntelligentContextCompactor,
    CompactConfig,
)
from .services.tool_orchestrator import get_tool_orchestrator
from .utils.models_config import get_model_context_window, get_model_max_tokens


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
    context_window: int = 0  # 0 = auto-detect from model config
    cache_tool_results: bool = False
    on_notify: Callable[[str, dict[str, Any]], None] | None = None
    auto_review: bool = False
    model_client: ModelClient | None = None  # Custom model client (for multi-model routing)
    max_review_iterations: int = 3


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
        self.client = config.model_client if config.model_client is not None else get_model_client()
        self.abort_event = asyncio.Event()

        # Auto-detect context_window and max_output_tokens from backend
        if self.config.context_window <= 0:
            self.config.context_window = get_model_context_window()
        self._max_output_tokens = get_model_max_tokens()
        if self._max_output_tokens <= 0:
            self._max_output_tokens = 4096
        # Cap at OpenCode-style OUTPUT_TOKEN_MAX (32K) so we don't over-reserve
        self._max_output_tokens = min(self._max_output_tokens, 32_000)

        # OpenCode-style usable context = context_window - max_output_tokens
        # This ensures we always leave headroom for the model to generate output.
        self._usable_context = max(1, self.config.context_window - self._max_output_tokens)

        # Initialize services
        # OpenCode-style: pass backend URL so the estimator can use precise tokenizers
        self._token_estimator = get_token_estimator(
            base_url=config.model_client.base_url if config.model_client else "",
            model_name=getattr(config.model_client, "model", "") if config.model_client else "",
        )
        self._precise_tokenizer = get_precise_tokenizer(
            base_url=config.model_client.base_url if config.model_client else "",
            model_name=getattr(config.model_client, "model", "") if config.model_client else "",
        )
        self._context_compressor = get_context_compressor()

        # Create a dedicated compactor instance configured with usable context
        compact_config = CompactConfig()
        if self._usable_context > 0:
            compact_config.compact_threshold = max(1, int(self._usable_context * 0.85))
            compact_config.critical_threshold = max(1, int(self._usable_context * 0.98))
        self._intelligent_compactor = IntelligentContextCompactor(config=compact_config)

        if config.cache_tool_results:
            self._tool_orchestrator = get_tool_orchestrator()
        else:
            self._tool_orchestrator = None

        # Compaction tracking (token-based cooldown is more reliable)
        self._last_compaction_token_count: int = 0
        self._compaction_count = 0

        # OpenCode-style: cache the most recent API-reported usage so we can
        # use ground-truth token counts instead of pure heuristics.
        self._last_api_usage: TokenUsage | None = None
        self._last_api_usage_hash: str | None = None

        # Precise tokenizer caching: avoid hammering /tokenize on every
        # stream event.  We cache the result for a few seconds unless the
        # conversation state changes.
        self._last_precise_count: int | None = None
        self._last_precise_count_at: float = 0.0
        self._last_precise_count_hash: str | None = None
        self.MIN_PRECISE_INTERVAL: float = 5.0

        # Post-edit review tracking
        self._changed_files: list[str] = []
        self._review_iteration_count: int = 0

        # OpenCode-style event bus for fine-grained stream observation
        self._event_bus = EventBus()

    @property
    def event_bus(self) -> EventBus:
        """Expose the internal event bus for external consumers (REPL, TUI, Headless, Web)."""
        return self._event_bus

    def change_cwd(self, cwd: str) -> None:
        """Change working directory and sync to app_state.

        Tools resolve relative paths via ToolUseContext.get_app_state(),
        so updating config.cwd alone is insufficient. This helper ensures
        both config and app_state stay in sync.
        """
        self.config.cwd = cwd
        if self.config.set_app_state:
            self.config.set_app_state(lambda s: setattr(s, "cwd", cwd) or s)

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
            context_lines.append(
                "- **IMPORTANT**: Each Bash/PowerShell call runs in a separate subprocess. "
                "`cd` changes ARE tracked across calls, including compound commands like "
                "`cd .. && cd test`. The current directory shown above is persistent."
            )
        else:
            shell = os.environ.get("SHELL", "/bin/bash")
            context_lines.append(f"- **Default Shell**: {shell}")
            context_lines.append("- **Command Notes**: Use Unix commands (e.g., `ls`, `cd`, `cat`)")
            context_lines.append(
                "- **IMPORTANT**: Each Bash call runs in a separate subprocess. "
                "`cd` changes ARE tracked across calls. The current directory shown above is persistent."
            )

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

    def _parse_content_tool_calls(self, content: str) -> list[dict[str, Any]]:
        """Parse XML/pseudo-XML tool calls embedded in assistant content.

        Some local models (vLLM, Ollama with certain backends) output tool calls
        as pseudo-XML in the content field instead of using the standard
        OpenAI 'tool_calls' delta field. This method extracts them as a fallback.

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
        # e.g. <function=Bash> <parameter=command> cd </tool_call>
        if not tool_calls:
            pattern3 = r"<function=(\w+)>\s*(.*?)\s*</tool_call>"
            for match in re.finditer(pattern3, content, re.DOTALL):
                tool_name = match.group(1)
                params_block = match.group(2)

                arguments: dict[str, Any] = {}
                # Try <parameter=key>value</parameter> first
                param_pattern = r"<parameter=(\w+)>(.*?)(?:</parameter>|\s*</tool_call>|$)"
                for pmatch in re.finditer(param_pattern, params_block, re.DOTALL):
                    arguments[pmatch.group(1)] = pmatch.group(2).strip()

                # Also try bare key=value pairs inside
                if not arguments:
                    kv_pattern = r"(\w+)\s*=\s*([^\s<]+|<[^>]+>)"
                    for kvmatch in re.finditer(kv_pattern, params_block):
                        arguments[kvmatch.group(1)] = kvmatch.group(2).strip()

                if tool_name:
                    tool_calls.append({"name": tool_name, "arguments": arguments})

        return tool_calls

    def _remove_xml_tool_calls(self, content: str) -> str:
        """Remove XML/pseudo-XML tool call blocks from content."""
        # Pattern 1
        cleaned = re.sub(
            r"<tool_call>\s*<function=\w+>\s*.*?\s*</function>\s*</tool_call>",
            "",
            content,
            flags=re.DOTALL,
        )
        # Pattern 2
        cleaned = re.sub(
            r"<tool_call>\s*<name>\w+</name>\s*<arguments>.*?</arguments>\s*</tool_call>",
            "",
            cleaned,
            flags=re.DOTALL,
        )
        # Pattern 3: incomplete XML without wrapper
        cleaned = re.sub(
            r"<function=\w+>\s*.*?\s*</tool_call>",
            "",
            cleaned,
            flags=re.DOTALL,
        )
        return cleaned.strip()

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

    def _convert_to_api_messages(self, messages: list[MessageType]) -> list[dict[str, Any]]:
        """Convert internal messages to API format.

        Delegates to types.message.to_api_format() which handles the critical
        invariant: AssistantMessage + following ToolUseMessages must be merged
        into a SINGLE API assistant message (content + tool_calls).
        """
        return to_api_format(messages)

    # Greeting patterns that can be handled locally without calling the API
    _GREETING_PATTERNS_CN = {
        "你好",
        "您好",
        "嗨",
        "哈喽",
        "在吗",
        "在么",
        "你是谁",
        "你叫什么",
        "介绍一下你自己",
        "你是做什么的",
    }
    _GREETING_PATTERNS_EN = {
        "hello",
        "hi",
        "hey",
        "hiya",
        "greetings",
        "who are you",
        "what are you",
        "introduce yourself",
    }

    def _detect_language(self, text: str) -> str:
        """Detect if text is primarily Chinese or English."""
        for ch in text:
            if "\u4e00" <= ch <= "\u9fff":
                return "cn"
        return "en"

    def _is_greeting(self, prompt: str) -> bool:
        """Check if the prompt is a simple greeting that can be handled locally."""
        text = prompt.strip().lower()
        all_patterns = self._GREETING_PATTERNS_CN | self._GREETING_PATTERNS_EN
        if text in all_patterns:
            return True
        if len(text) <= 10 and "\n" not in text:
            for pattern in all_patterns:
                if text.startswith(pattern):
                    return True
        return False

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

        # Reset review counter on new user input
        if prompt:
            self._review_iteration_count = 0

        # Fast path: handle simple greetings locally without API call
        if self._is_greeting(prompt):
            lang = self._detect_language(prompt)
            if lang == "cn":
                reply = (
                    "你好！我是 **PilotCode**，你的 AI 编程助手。\n\n"
                    "我可以帮你：\n\n"
                    "- 编写、阅读和编辑代码\n"
                    "- 分析和调试程序\n"
                    "- 执行 shell 命令和搜索代码库\n"
                    "- 规划和拆分复杂任务\n\n"
                    "告诉我你想做什么吧！"
                )
            else:
                reply = (
                    "Hello! I'm **PilotCode**, your AI programming assistant.\n\n"
                    "I can help you with:\n\n"
                    "- Writing, reading, and editing code\n"
                    "- Analyzing and debugging programs\n"
                    "- Running shell commands and searching your codebase\n"
                    "- Planning and breaking down complex tasks\n\n"
                    "Just tell me what you'd like to work on!"
                )
            assistant_msg = AssistantMessage(content=reply)
            self.messages.append(assistant_msg)
            yield QueryResult(message=assistant_msg, is_complete=False)
            yield QueryResult(message=assistant_msg, is_complete=True)
            return

        # Auto-compact if needed before sending to API
        if self.config.auto_compact:
            self.auto_compact_if_needed()

        # Auto-review after batch edits (interactive modes only)
        if (
            self.config.auto_review
            and self._changed_files
            and self._review_iteration_count < self.config.max_review_iterations
        ):
            yield QueryResult(
                message=SystemMessage(content="🔍 Auto-reviewing changes..."),
                is_complete=False,
            )

            from .services.post_edit_validator import PostEditValidator

            validator = PostEditValidator(model_client=self.client)
            result = await validator.review_and_test(self._changed_files)

            review_text = result["review_result"]
            test_text = result["test_result"]
            issues_found = result["issues_found"]
            redesign_prompt = result.get("redesign_prompt")

            review_msg_content = f"""[Auto-review result]

{review_text}

[Test result]
{test_text}"""

            if not issues_found and result["test_env_ready"]:
                review_msg_content += "\n\n✅ All checks passed."
            elif not issues_found and not result["test_env_ready"]:
                review_msg_content += "\n\n⚠️ Review passed but no test environment detected."
            else:
                review_msg_content += "\n\n❌ Issues found. Please fix them before proceeding."

            if self._review_iteration_count >= self.config.max_review_iterations - 1:
                review_msg_content += (
                    "\n\n[Max review iterations reached. Manual review recommended.]"
                )

            review_msg = SystemMessage(content=review_msg_content)
            self.messages.append(review_msg)
            yield QueryResult(message=review_msg, is_complete=True)

            # P0: If tests failed, insert explicit redesign instructions
            if (
                redesign_prompt
                and self._review_iteration_count < self.config.max_review_iterations - 1
            ):
                redesign_msg = SystemMessage(content=redesign_prompt)
                self.messages.append(redesign_msg)
                yield QueryResult(message=redesign_msg, is_complete=True)

            self._review_iteration_count += 1
            self._changed_files = []

        # Build API messages
        api_messages: list[dict[str, Any]] = []
        if len(self.messages) == 1:
            system_msg = self._build_system_message()
            api_messages.append({"role": "system", "content": system_msg.content})

        api_messages.extend(self._convert_to_api_messages(self.messages))

        # Get available tools
        tools = self.config.tools if self.config.tools else []

        # Detect DeepSeek for provider-specific handling
        is_deepseek = "deepseek" in getattr(self.client, "base_url", "").lower()

        # Stream response with automatic context-window recovery
        _context_attempt = 0
        _rate_limit_retry = 0
        _max_rate_limit_retries = 3
        while _context_attempt < 2:
            accumulated_content = ""
            accumulated_reasoning = ""  # DeepSeek thinking mode content
            pending_tool_calls: list[ToolCall] = []
            current_tool_call: dict[int, dict] = {}  # Accumulate tool call parts
            suppress_streaming = False  # Set to True when XML tool calls appear in content

            try:
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

                    # OpenCode-style: capture usage from the final stream chunk
                    usage = chunk.get("usage")
                    if usage and isinstance(usage, dict):
                        # Extract detailed token usage (cache, reasoning, etc.)
                        prompt_tok = usage.get("prompt_tokens", 0)
                        comp_tok = usage.get("completion_tokens", 0)
                        total_tok = usage.get("total_tokens", 0)

                        # Cache details (OpenAI-style prompt_tokens_details)
                        ptd = usage.get("prompt_tokens_details") or {}
                        cache_read = ptd.get("cached_tokens", 0) if isinstance(ptd, dict) else 0

                        # Anthropic-style cache creation tokens
                        cache_write = usage.get("cache_creation_input_tokens", 0)

                        # Reasoning tokens (DeepSeek/Qwen3 thinking mode)
                        ctd = usage.get("completion_tokens_details") or {}
                        reasoning = ctd.get("reasoning_tokens", 0) if isinstance(ctd, dict) else 0

                        self._last_api_usage = TokenUsage(
                            prompt_tokens=prompt_tok,
                            completion_tokens=comp_tok,
                            total_tokens=total_tok or (prompt_tok + comp_tok),
                            cache_read_tokens=cache_read,
                            cache_write_tokens=cache_write,
                            reasoning_tokens=reasoning,
                        )
                        self._last_api_usage_hash = self._compute_state_hash()

                    # Handle reasoning content (DeepSeek thinking mode only)
                    if is_deepseek:
                        reasoning = delta.get("reasoning_content")
                        if reasoning:
                            accumulated_reasoning += reasoning
                            await self._event_bus.emit(StreamEvent.reasoning_delta(reasoning))

                    # Handle content
                    content = delta.get("content")
                    if content:
                        accumulated_content += content
                        # If accumulated content starts containing XML tool-call markers,
                        # stop streaming individual chunks to avoid showing raw XML tags.
                        if not suppress_streaming and (
                            "<tool_call" in accumulated_content
                            or "<function=" in accumulated_content
                        ):
                            suppress_streaming = True
                        if not suppress_streaming:
                            partial_msg = AssistantMessage(content=content)
                            yield QueryResult(message=partial_msg, is_complete=False)
                            await self._event_bus.emit(StreamEvent.text_delta(content))

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
                        await self._event_bus.emit(
                            StreamEvent.finish_step(finish_reason=finish_reason)
                        )
                        break
            except ContextWindowError as exc:
                await self._event_bus.emit(StreamEvent.error(exc))
                if _context_attempt == 0:
                    logger.warning("Context window exceeded, auto-compacting and retrying...")
                    self.intelligent_compact()
                    if self.count_tokens() > self._usable_context:
                        self.auto_compact_if_needed()
                    api_messages = self._convert_to_api_messages(self.messages)
                    if len(self.messages) == 1:
                        system_msg = self._build_system_message()
                        api_messages.insert(0, {"role": "system", "content": system_msg.content})
                    _context_attempt += 1
                    continue
                raise
            except RateLimitError as exc:
                await self._event_bus.emit(StreamEvent.error(exc))
                if _rate_limit_retry < _max_rate_limit_retries:
                    wait = exc.retry_after or (2**_rate_limit_retry)
                    logger.warning(
                        "Rate limited (429), waiting %.1fs before retry %d/%d...",
                        wait,
                        _rate_limit_retry + 1,
                        _max_rate_limit_retries,
                    )
                    await asyncio.sleep(wait)
                    _rate_limit_retry += 1
                    continue
                raise

            # Fallback: parse XML-style tool calls from content if API didn't return standard tool_calls
            # MUST parse before stripping XML, otherwise content is empty for parsing.
            if not current_tool_call and accumulated_content:
                xml_tools = self._parse_content_tool_calls(accumulated_content)
                if xml_tools:
                    for i, tc in enumerate(xml_tools):
                        current_tool_call[i] = {
                            "id": f"xml_tool_{i}_{uuid.uuid4().hex[:6]}",
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        }

            # Strip any XML-style tool calls from displayed content unconditionally
            if accumulated_content and (
                "<tool_call" in accumulated_content or "<function=" in accumulated_content
            ):
                accumulated_content = self._remove_xml_tool_calls(accumulated_content)

            # Final assistant message
            if accumulated_content or accumulated_reasoning or current_tool_call:
                assistant_msg = AssistantMessage(
                    content=accumulated_content,
                    reasoning_content=(accumulated_reasoning or None) if is_deepseek else None,
                )
                self.messages.append(assistant_msg)
                yield QueryResult(message=assistant_msg, is_complete=True)
                await self._event_bus.emit(StreamEvent.text_end())

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
                await self._event_bus.emit(
                    StreamEvent.tool_call_start(
                        tool_call_id=tool_call.id,
                        tool_name=tool_call.name,
                        tool_input=tool_call.arguments,
                    )
                )

            break

    def add_tool_result(self, tool_use_id: str, content: str, is_error: bool = False) -> None:
        """Add a tool result to the conversation history.

        Full tool results are preserved; context compaction (if enabled)
        is handled in submit_message() before sending to the API.

        Call this after executing a tool, then call submit_message again
        to let the LLM continue with the tool result.
        """
        # Track file changes for post-edit review
        tool_name = ""
        for msg in reversed(self.messages):
            if isinstance(msg, ToolUseMessage) and msg.tool_use_id == tool_use_id:
                tool_name = msg.name
                break
        if tool_name in ("FileEdit", "FileWrite", "ApplyPatch"):
            for msg in reversed(self.messages):
                if isinstance(msg, ToolUseMessage) and msg.tool_use_id == tool_use_id:
                    file_path = self._extract_file_path(msg)
                    if file_path and file_path not in self._changed_files:
                        self._changed_files.append(file_path)
                    break

        # Dynamic truncation based on available context budget.
        # OpenCode-style: use usable_context (context_window - max_output_tokens)
        # so we never steal headroom reserved for the model's reply.
        if isinstance(content, str) and self._usable_context > 0:
            tokens_before = self.count_tokens()
            ratio = tokens_before / self._usable_context

            if ratio < 0.5:
                # Plenty of room: allow up to 20 % of usable context
                max_tool_tokens = int(self._usable_context * 0.20)
            elif ratio < 0.85:
                # Getting tight: allow half of remaining space
                max_tool_tokens = max(2_000, int((self._usable_context - tokens_before) * 0.5))
            elif ratio < 1.0:
                # Very tight: keep tool result small
                max_tool_tokens = 2_000
            else:
                # Already over budget: emergency micro-cap
                max_tool_tokens = 500

            # Rough chars-per-token estimate (~3.5 for mixed content)
            max_chars = max(500, int(max_tool_tokens * 3.5))

            if len(content) > max_chars:
                truncated = len(content) - max_chars
                if is_error:
                    # Errors: prioritize the tail where the actual error details live,
                    # but keep some head for context.
                    head_len = int(max_chars * 0.3)
                    tail_len = max_chars - head_len
                    content = (
                        content[:head_len]
                        + f"\n\n[...truncated {truncated} chars; exceeds context budget ({max_tool_tokens} tokens allowed)]\n\n"
                        + content[-tail_len:]
                    )
                else:
                    # Normal output: keep both head and tail so the LLM can see
                    # the beginning of the output and any summary/error at the end.
                    half = max_chars // 2
                    content = (
                        content[:half]
                        + f"\n\n[...truncated {truncated} chars; exceeds context budget ({max_tool_tokens} tokens allowed)]\n\n"
                        + content[-half:]
                    )

        tool_result_msg = ToolResultMessage(
            tool_use_id=tool_use_id, content=content, is_error=is_error
        )
        self.messages.append(tool_result_msg)

    def _extract_file_path(self, tool_msg: ToolUseMessage) -> str | None:
        """Extract file path from FileEdit/FileWrite/ApplyPatch tool input."""
        input_data = tool_msg.input if isinstance(tool_msg.input, dict) else {}
        for key in ("path", "file_path", "filepath"):
            val = input_data.get(key)
            if val and isinstance(val, str):
                return val
        return None

    def abort(self) -> None:
        """Abort current query."""
        self.abort_event.set()

    def _compute_state_hash(self) -> str:
        """Return a cheap hash of current conversation state.

        Used to detect whether new messages have arrived since the last
        API call or precise token count.
        """
        parts: list[str] = []
        for m in self.messages:
            if hasattr(m, "content"):
                parts.append(f"{getattr(m, 'role', 'user')}:{m.content}")
            elif hasattr(m, "name") and hasattr(m, "input"):
                parts.append(f"tool:{m.name}:{m.input}")
            else:
                parts.append(str(m))
        if self.config.tools:
            try:
                parts.append(
                    json.dumps(
                        [t.to_dict() if hasattr(t, "to_dict") else t for t in self.config.tools],
                        sort_keys=True,
                    )
                )
            except Exception:
                pass
        return str(hash("|".join(parts)))

    def _count_with_precise_tokenizer(self) -> int | None:
        """Try to count tokens using the precise backend tokenizer.

        Sends the full message list (system + messages + tools) to the
        backend's /tokenize endpoint when available.
        """
        try:
            # Build full API message list including system prompt
            api_msgs: list[dict[str, Any]] = []
            system_msg = self._build_system_message()
            api_msgs.append({"role": "system", "content": system_msg.content})

            for m in self.messages:
                if hasattr(m, "content"):
                    api_msgs.append({"role": getattr(m, "role", "user"), "content": str(m.content)})
                elif hasattr(m, "name") and hasattr(m, "input"):
                    api_msgs.append(
                        {
                            "role": "assistant",
                            "content": f"Tool: {m.name}\nInput: {m.input}",
                        }
                    )

            # Build tools list if any are configured
            api_tools: list[dict[str, Any]] | None = None
            if self.config.tools:
                api_tools = []
                for tool in self.config.tools:
                    try:
                        import json

                        # Ensure each tool is a plain dict
                        if hasattr(tool, "to_dict"):
                            api_tools.append(tool.to_dict())
                        elif isinstance(tool, dict):
                            api_tools.append(tool)
                        else:
                            api_tools.append(json.loads(json.dumps(tool, default=str)))
                    except Exception:
                        continue
                if not api_tools:
                    api_tools = None

            # Try precise message+tools tokenization first (vLLM supports this)
            count = self._precise_tokenizer.count_messages_with_tools(api_msgs, tools=api_tools)
            if count is not None:
                return count

            # Fallback: count text components individually, then add tools
            total = 0
            system_msg = self._build_system_message()
            total += self._precise_tokenizer.count_text(
                system_msg.content
            ) or self._token_estimator.estimate(system_msg.content)
            for m in self.messages:
                content = str(getattr(m, "content", getattr(m, "name", "")))
                total += self._precise_tokenizer.count_text(
                    content
                ) or self._token_estimator.estimate(content)

            if api_tools:
                for tool in api_tools:
                    try:
                        import json

                        schema = json.dumps(tool, ensure_ascii=False)
                        total += self._precise_tokenizer.count_text(
                            schema
                        ) or self._token_estimator.estimate(schema)
                    except Exception:
                        total += 500
            return total
        except Exception:
            return None

    def _heuristic_count_tokens(self) -> int:
        """Pure heuristic token count (fallback when API usage is unavailable)."""
        total = 0

        # Count system prompt (always sent on first message, or prepended)
        system_msg = self._build_system_message()
        total += self._token_estimator.estimate(system_msg.content)
        total += 4  # message overhead

        # Count conversation messages
        for m in self.messages:
            if hasattr(m, "content"):
                content = str(m.content)
            elif hasattr(m, "name") and hasattr(m, "input"):
                content = f"Tool: {m.name}\nInput: {m.input}"
            else:
                content = str(m)

            total += self._token_estimator.estimate(content)
            total += 4  # message overhead

        # Count tool definitions (sent with every request if tools enabled)
        tools = self.config.tools if self.config.tools else []
        if tools:
            for tool in tools:
                try:
                    import json

                    schema = json.dumps(tool, ensure_ascii=False)
                    total += self._token_estimator.estimate(schema)
                except Exception:
                    total += 500  # fallback estimate per tool

        return total

    def count_tokens(self) -> int:
        """Count tokens in current conversation.

        OpenCode-style priority:
        1. Use API-reported usage from the most recent turn (ground truth).
        2. Use precise backend tokenizer (/tokenize, transformers, tiktoken).
        3. Fall back to heuristic estimation.

        Caching logic:
        - If API usage exists and conversation state hasn't changed,
          return the cached API total immediately.
        - If API usage exists but new messages arrived (e.g. streaming),
          return API total + heuristic estimate for the delta.  This avoids
          calling /tokenize on every stream chunk.
        - If no API usage yet, rate-limit precise tokenizer calls to
          once every ``MIN_PRECISE_INTERVAL`` seconds.
        """
        current_hash = self._compute_state_hash()

        # Priority 1: API-reported usage is the most authoritative.
        if self._last_api_usage:
            api_total = self._last_api_usage.total_tokens
            if current_hash == self._last_api_usage_hash:
                # Conversation unchanged since last API call → ground truth.
                return api_total
            # New messages arrived (streaming, tool results, etc.).
            # Estimate only the delta with heuristics rather than re-tokenizing
            # the entire conversation.
            return max(api_total, self._heuristic_count_tokens())

        # Priority 2: Try precise tokenizer, but rate-limit to avoid
        # hammering the backend with /tokenize requests.
        now = time.monotonic()
        if (
            self._last_precise_count is not None
            and current_hash == self._last_precise_count_hash
            and (now - self._last_precise_count_at) < self.MIN_PRECISE_INTERVAL
        ):
            return self._last_precise_count

        precise = self._count_with_precise_tokenizer()
        if precise is not None:
            self._last_precise_count = precise
            self._last_precise_count_at = now
            self._last_precise_count_hash = current_hash
            return precise

        # Priority 3: Heuristic fallback
        return self._heuristic_count_tokens()

    def is_overflow(self) -> bool:
        """OpenCode-style context overflow detection.

        Matches the exact logic from OpenCode's session/overflow.ts:

            count  = total_tokens
            reserved = min(COMPACTION_BUFFER, max_output_tokens)
            usable   = context_window - max_output_tokens
            overflow = count >= usable

        Returns True if the conversation has reached or exceeded the usable
        input context (i.e. there is no longer guaranteed headroom for the
        model to generate its full max_output_tokens).
        """
        count = self.count_tokens()
        reserved = min(20_000, self._max_output_tokens)
        usable = self.config.context_window - reserved
        if usable <= 0:
            usable = self._usable_context
        return count >= usable

    def get_token_budget(self) -> dict[str, Any]:
        """Get current token budget status."""
        return self._token_estimator.get_budget_status(self.count_tokens(), self._usable_context)

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

        Triggers at 85% of usable context to leave headroom for output.

        Returns compression result or None if not needed.
        """
        token_count = self.count_tokens()
        threshold = int(self._usable_context * 0.85)
        if token_count < threshold:
            return None

        # Use smart compression
        result = await self._context_compressor.compress(
            self.messages,
            summarizer=None,  # Could pass Brief tool here
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

        OpenCode-style overflow detection:
        - ``usable = context_window - max_output_tokens``
        - Compaction triggers at 85% of usable space
        - Critical compaction at 98% of usable space

        Uses intelligent compaction which clears old tool result content
        while preserving conversation structure and key context.
        Falls back to simple compaction if intelligent compaction doesn't
        effectively reduce token usage.
        """
        if not self.config.auto_compact:
            return False

        token_count = self.count_tokens()
        # OpenCode-style: usable = context - max_output_tokens
        threshold = int(self._usable_context * 0.85)
        critical = int(self._usable_context * 0.98)
        if token_count < threshold:
            return False

        # Cooldown: don't re-compact if token count hasn't grown since last compaction
        # (token-based cooldown is more reliable than message-count-based)
        # EXCEPTION: always compact if we're over critical threshold or context window
        if token_count <= getattr(self, "_last_compaction_token_count", 0):
            if token_count < critical:
                return False

        # Log compaction trigger details for debugging
        logger.debug(
            "auto_compact triggered: tokens=%d threshold=%d critical=%d usable=%d context_window=%d max_output=%d msg_count=%d",
            token_count,
            threshold,
            critical,
            self._usable_context,
            self.config.context_window,
            self._max_output_tokens,
            len(self.messages),
        )

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
                self._last_compaction_token_count = self.count_tokens()
                return True

        # Fallback 1: simple compaction (keep system + recent)
        if self.count_tokens() < threshold:
            return False

        keep_recent = 4 if token_count > critical else 6
        compressed = self._context_compressor.simple_compact(self.messages, keep_recent=keep_recent)
        did_compact = False
        if len(compressed) < len(self.messages):
            self.messages = compressed
            did_compact = True

        # Fallback 2: if still over critical threshold, aggressive truncation.
        # Preserve system messages and the most recent user message so the LLM
        # doesn't "forget" its role or the current task objective.
        if self.count_tokens() > critical and len(self.messages) > 3:
            from .types.message import SystemMessage, UserMessage

            to_preserve: set[int] = set()
            # Always preserve system messages
            for i, msg in enumerate(self.messages):
                if isinstance(msg, SystemMessage):
                    to_preserve.add(i)
            # Always preserve the most recent user message (task objective)
            for i in range(len(self.messages) - 1, -1, -1):
                if isinstance(self.messages[i], UserMessage):
                    to_preserve.add(i)
                    break
            # Fill remaining slots with most recent non-preserved messages
            recent: list[int] = []
            slots = max(0, 2 - len(to_preserve))
            for i in range(len(self.messages) - 1, -1, -1):
                if i not in to_preserve and len(recent) < slots:
                    recent.append(i)
            # Combine and preserve original order
            kept = sorted(to_preserve | set(recent))
            self.messages = [self.messages[i] for i in kept]
            did_compact = True

        # Fallback 3: if still over threshold, truncate message content
        if self.count_tokens() > threshold:
            from .types.message import UserMessage, AssistantMessage, ToolResultMessage

            # When we have very few messages but massive tokens, the huge content
            # is likely in the most recent message. In critical mode with <=3 msgs,
            # we must be willing to truncate even the most recent message.
            allow_truncate_recent = len(self.messages) <= 3 and self.count_tokens() > critical

            for i, msg in enumerate(self.messages):
                # Skip the most recent message unless we're in critical emergency mode
                if i >= len(self.messages) - 1 and not allow_truncate_recent:
                    continue
                content = getattr(msg, "content", "")
                text = content if isinstance(content, str) else str(content)
                if len(text) > 2000:
                    truncated_text = text[:1500] + f"\n\n[...truncated from {len(text)} chars]"
                    if isinstance(msg, UserMessage):
                        self.messages[i] = UserMessage(content=truncated_text)
                        did_compact = True
                    elif isinstance(msg, AssistantMessage):
                        self.messages[i] = AssistantMessage(content=truncated_text)
                        did_compact = True
                    elif isinstance(msg, ToolResultMessage):
                        self.messages[i] = ToolResultMessage(
                            tool_use_id=msg.tool_use_id,
                            content=truncated_text,
                            is_error=msg.is_error,
                        )
                        did_compact = True

        if did_compact:
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
            self._last_compaction_token_count = self.count_tokens()
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
Project: {summary.get("primary_request", "N/A")[:100]}
Files examined: {", ".join(summary.get("files_examined", []))}
Files modified: {", ".join(summary.get("files_modified", []))}
Errors: {len(summary.get("errors_encountered", []))}
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
