"""Query engine for managing conversation with LLM."""

import asyncio
import json
import logging
import re
import uuid
from typing import Any, AsyncIterator, Callable
from dataclasses import dataclass, field

from .types.message import (
    MessageType,
    UserMessage,
    AssistantMessage,
    ToolUseMessage,
    ToolResultMessage,
    SystemMessage,
)
from .tools.base import Tools
from .state.app_state import AppState
from .utils.model_client import (
    ToolCall,
    get_model_client,
    ModelClient,
    ContextWindowError,
    RateLimitError,
    LLMError,
)
from .query.token_manager import TokenManager
from .services.stream_events import EventBus, StreamEvent
from .services.context_compression import CompressionResult
from .query.compaction_manager import CompactionManager
from .query.prompt_builder import PromptBuilder
from .query.message_parser import MessageParser
from .query.session_manager import SessionManager
from .query.per_turn_snapshot import PerTurnSnapshotTracker
from .services.knowhow_loader import KnowHowLoader
from .services.memory_dir import FastMemoryManager
from .permissions.permission_manager import get_permission_manager
from .services.tool_orchestrator import get_tool_orchestrator
from .utils.models_config import get_model_context_window, get_model_max_tokens

logger = logging.getLogger(__name__)


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
    compact_model: str | None = (
        None  # Lightweight model for compaction summarization (e.g., "qwen2.5-7b")
    )
    summarizer: Callable[[str], Any] | None = None  # Optional custom summarizer callable
    max_review_iterations: int = 3
    ultra_slim_tools: bool = False  # Strip param descriptions from tool schemas
    session_id: str | None = None  # For unified session persistence
    permission_mode: str = "default"  # Tool visibility filtering mode
    enable_thinking: bool | None = None  # None=auto, True=force on, False=force off


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
        # Unified session persistence ID
        self.session_id = config.session_id or f"cli_{uuid.uuid4().hex[:12]}"

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

        # Compaction management (extracted to CompactionManager)
        self._compaction_mgr = CompactionManager(
            messages_ref=self.messages,
            count_tokens_fn=self.count_tokens,
            usable_context=self._usable_context,
            auto_compact=config.auto_compact,
            on_notify=config.on_notify,
            summarizer=config.summarizer,
        )

        if config.cache_tool_results:
            self._tool_orchestrator = get_tool_orchestrator()
        else:
            self._tool_orchestrator = None

        # Prompt building (extracted to PromptBuilder)
        self._prompt_builder = PromptBuilder(
            cwd=config.cwd,
            custom_system_prompt=config.custom_system_prompt,
            get_app_state=config.get_app_state,
        )

        # Fast memory manager (Hermes Tier-1: frozen mid-session + consolidation)
        self._fast_memory = FastMemoryManager(config.cwd)

        # Token management (extracted to TokenManager)
        self._token_mgr = TokenManager(
            session_id=self.session_id,
            context_window=self.config.context_window,
            max_output_tokens=self._max_output_tokens,
            base_url=config.model_client.base_url if config.model_client else "",
            model_name=getattr(config.model_client, "model", "") if config.model_client else "",
            tools=self.config.tools or [],
            messages_ref=self.messages,
            build_system_fn=self._prompt_builder.build,
            get_runtime_fn=self._prompt_builder._get_runtime_context,
            get_app_state_fn=self.config.get_app_state,
            set_app_state_fn=self.config.set_app_state,
        )

        # Measure fresh-session token baseline
        self._token_mgr.measure_baseline()

        # KnowHow: auto-create template on first use
        _knowhow = KnowHowLoader(config.cwd)
        if not _knowhow.knowhow_path.exists():
            _knowhow._create_template()

        # Session persistence (extracted to SessionManager)
        self._session_mgr = SessionManager(
            session_id=self.session_id,
            config=self.config,
            messages_ref=self.messages,
        )

        # Post-edit review tracking
        self._changed_files: list[str] = []
        self._review_iteration_count: int = 0

        # Per-turn file snapshot tracking
        self._snapshot_tracker = PerTurnSnapshotTracker(config.cwd)

        # Reasoning history for loop detection (keeps last N reasoning contents)
        self._reasoning_history: list[str] = []
        self._max_reasoning_history: int = 5

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

    def _build_extra_body(self, prompt: str) -> dict[str, Any] | None:
        """Build provider-specific extra_body for API requests.

        Currently controls Qwen/DeepSeek thinking mode based on task complexity.
        """
        enable = self.config.enable_thinking
        if enable is None:
            # Auto-detect: enable thinking for complex tasks
            enable = self._should_enable_thinking(prompt)
        # If enable is set (either True or False) and client supports reasoning content, return it
        # If enable is not set (None), we still need to return None
        if enable is not None and getattr(self.client, "supports_reasoning_content", False):
            return {"enable_thinking": enable}
        return None

    def _should_enable_thinking(self, prompt: str) -> bool:
        """Heuristic: determine if thinking mode should be enabled.

        Enable for: bug fixes, refactoring, multi-step tasks, file edits.
        Disable for: greetings, simple queries, short prompts.
        """
        # Disable for very short prompts (likely greetings/simple queries)
        if not prompt or len(prompt.strip()) < 20:
            return False
        # Disable for known greeting patterns
        text_lower = prompt.strip().lower()
        greeting_keywords = {
            "hello",
            "hi",
            "hey",
            "你好",
            "您好",
            "嗨",
            "在吗",
            "在么",
            "who are you",
            "what are you",
            "introduce yourself",
            "你是谁",
            "你叫什么",
            "介绍一下",
        }
        if text_lower in greeting_keywords or any(
            text_lower.startswith(g) for g in greeting_keywords
        ):
            return False
        # Enable if there are pending file changes (likely complex task)
        if self._changed_files:
            return True
        # Enable for complex task keywords
        complex_keywords = [
            "bug",
            "fix",
            "error",
            "debug",
            "refactor",
            "重构",
            "修复",
            "bug",
            "design",
            "architecture",
            "架构",
            "设计",
            "implement",
            "实现",
            "编写",
            "create",
            "test",
            "测试",
            "verify",
            "验证",
            "optimize",
            "优化",
            "performance",
            "性能",
            "migrate",
            "迁移",
            "upgrade",
            "升级",
        ]
        if any(kw in text_lower for kw in complex_keywords):
            return True
        # Default: disable for simple queries, enable for everything else
        return False

    def _reflect_on_reasoning(self, reasoning: str) -> str | None:
        """Low-cost reflection on reasoning content using heuristic rules.

        Detects common reasoning defects without LLM calls:
        1. Guessing without verification plan
        2. Repeated retries without strategy change
        3. Jumping to fix without root cause analysis
        """
        if not reasoning:
            return None

        defects: list[str] = []
        reasoning_lower = reasoning.lower()

        # Pattern 1: Guessing without verification
        guess_markers = ["猜测", "guess", "大概", "可能", "也许", "should be", "probably"]
        if any(m in reasoning or m in reasoning_lower for m in guess_markers):
            verify_markers = ["验证", "test", "确认", "check", "verify", "证明"]
            if not any(m in reasoning or m in reasoning_lower for m in verify_markers):
                defects.append(
                    "You made a guess but didn't plan to verify it. "
                    "Please verify your assumption before acting."
                )

        # Pattern 2: Retry loop in reasoning
        retry_markers = ["再试", "retry", "try again", "again", "重新", "再来", "重试"]
        retry_count = sum(reasoning_lower.count(m) for m in retry_markers)
        if retry_count >= 3:
            defects.append(
                f"You've retried {retry_count} times with similar approaches. "
                "Consider a fundamentally different strategy."
            )

        # Pattern 3: Fix without root cause analysis
        fix_markers = ["fix", "修改", "修复", "patch", "改掉"]
        has_fix = any(m in reasoning_lower for m in fix_markers)
        root_cause_markers = [
            "root cause",
            "根因",
            "原因",
            "because",
            "why",
            "为什么",
            "分析",
            "analyze",
            " caused ",
            "导致",
        ]
        has_root_cause = any(m in reasoning or m in reasoning_lower for m in root_cause_markers)
        if has_fix and not has_root_cause:
            defects.append(
                "You jumped to a fix without analyzing the root cause. "
                "Please identify the true root cause first."
            )

        if defects:
            return "\n".join(f"{i + 1}. {d}" for i, d in enumerate(defects[:3]))
        return None

    def _detect_reasoning_loop(self, reasoning: str) -> str | None:
        """Detect if the model is stuck in a reasoning loop.

        Compares the current reasoning with the last 2 rounds using
        SequenceMatcher. If similarity exceeds the threshold for 3
        consecutive turns, the model is likely repeating the same
        thought pattern without progress.
        """
        if not reasoning or len(self._reasoning_history) < 2:
            return None
        from difflib import SequenceMatcher

        # Use first 500 chars for speed; reasoning loops usually repeat early
        curr = reasoning[:500]
        prev1 = self._reasoning_history[-1][:500]
        prev2 = self._reasoning_history[-2][:500]

        sim1 = SequenceMatcher(None, prev1, curr).ratio()
        sim2 = SequenceMatcher(None, prev2, curr).ratio()
        threshold = 0.75

        if sim1 > threshold and sim2 > threshold:
            return (
                "Your reasoning has been very similar for 3 consecutive turns. "
                "You may be stuck in a loop. Consider a completely different approach, "
                "such as reading more files, checking assumptions, or asking the user for clarification."
            )
        return None

    def _check_reasoning_action_consistency(
        self, reasoning: str, tool_calls: dict[int, dict]
    ) -> str | None:
        """Check if the model's reasoning matches its actual tool calls.

        Extracts file mentions from reasoning and compares against files
        targeted by FileEdit/FileWrite tool calls. Returns a warning
        message if there are mismatches, otherwise None.
        """
        import re

        # Extract file paths mentioned in reasoning
        # Match common patterns: "edit src/foo.py", "modify foo.py", "文件 src/foo.py"
        reasoning_files: set[str] = set()
        patterns = [
            # Verb + file path
            r"(?:edit|modify|change|update|read|write|创建|修改|编辑|读取)\s+[`\'\"]?([\w\-/\.]+\.(?:py|js|ts|jsx|tsx|java|go|rs|cpp|c|h|md|json|yaml|yml|toml))[`\'\"]?",
            # "and/or + file path" in lists
            r"(?:and|or|和|以及)\s+[`\'\"]?([\w\-/\.]+\.(?:py|js|ts|jsx|tsx|java|go|rs|cpp|c|h|md|json|yaml|yml|toml))[`\'\"]?",
            # Comma/space separated file paths
            r"[,，]\s+[`\'\"]?([\w\-/\.]+\.(?:py|js|ts|jsx|tsx|java|go|rs|cpp|c|h|md|json|yaml|yml|toml))[`\'\"]?",
            # Generic file/path mention
            r"(?:file|path)\s+[`\'\"]?([\w/\.\-]+\.[a-zA-Z0-9]+)[`\'\"]?",
        ]
        for pat in patterns:
            for m in re.finditer(pat, reasoning, re.IGNORECASE):
                reasoning_files.add(m.group(1))

        if not reasoning_files:
            return None

        # Extract file paths from actual tool calls
        actual_files: set[str] = set()
        for tc_data in tool_calls.values():
            try:
                args = json.loads(tc_data.get("arguments", "{}"))
            except json.JSONDecodeError:
                continue
            for key in ("file_path", "path", "filepath"):
                val = args.get(key)
                if val and isinstance(val, str):
                    actual_files.add(val)

        # Check for files mentioned in reasoning but not in tool calls
        missed = reasoning_files - actual_files
        if missed:
            files_str = ", ".join(sorted(missed)[:3])
            extra = f" (+{len(missed) - 3} more)" if len(missed) > 3 else ""
            return (
                f"You mentioned editing '{files_str}{extra}' in your reasoning "
                f"but did not include them in your tool calls."
            )
        return None

    def _get_git_changes(self) -> str:
        """Get a concise list of modified files from git for injection into system prompt."""
        try:
            import subprocess

            result = subprocess.run(
                ["git", "diff", "--name-only"],
                cwd=self.config.cwd,
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0:
                files = [f.strip() for f in result.stdout.split("\n") if f.strip()]
                if files:
                    return f"[Modified files]: {', '.join(files[:15])}" + (
                        f" (+{len(files) - 15} more)" if len(files) > 15 else ""
                    )
        except Exception:
            pass
        return ""

    def _get_snapshot_diff_summary(self) -> str:
        """Get per-turn file snapshot diff for injection into system prompt."""
        diff = self._snapshot_tracker.get_last_diff()
        if diff and diff.has_changes:
            summary = diff.to_summary(max_files=10)
            if summary:
                return f"[Changes since your last turn]: {summary}"
        return ""

    def _build_system_message(self) -> SystemMessage:
        """Build system message with runtime context. Delegated to PromptBuilder."""
        msg = self._prompt_builder.build()
        parts: list[str] = []
        snapshot = self._get_snapshot_diff_summary()
        if snapshot:
            parts.append(snapshot)
        changes = self._get_git_changes()
        if changes:
            parts.append(changes)
        if parts:
            msg.content = msg.content + "\n\n" + "\n".join(parts)
        return msg

    def _parse_content_tool_calls(self, content: str) -> list[dict[str, Any]]:
        """Parse XML/pseudo-XML tool calls from content. Delegated to MessageParser."""
        return MessageParser.parse_content_tool_calls(content)

    def _remove_xml_tool_calls(self, content: str) -> str:
        """Remove XML tool call blocks from content. Delegated to MessageParser."""
        return MessageParser.remove_xml_tool_calls(content)

    def _cleanup_orphaned_tool_calls(self) -> None:
        """Remove orphaned ToolUseMessages. Delegated to MessageParser."""
        MessageParser.cleanup_orphaned_tool_calls(self.messages)

    def _convert_to_api_messages(self, messages: list[MessageType]) -> list[dict[str, Any]]:
        """Convert internal messages to API format. Delegated to MessageParser."""
        return MessageParser.convert_to_api_messages(messages)

    def _get_visible_tools(self) -> Tools:
        """Return tools filtered by permission mode.

        Removes tools from the model's view when the permission mode
        indicates they should not be invoked (e.g. 'dontAsk' hides Bash).
        """
        tools = self.config.tools if self.config.tools else []
        if not tools:
            return []

        mode = self.config.permission_mode
        # Fast path: no filtering needed for permissive modes
        if mode in ("default", "acceptEdits", "bypassPermissions", "auto"):
            return tools

        try:
            pm = get_permission_manager()
            return [t for t in tools if pm.is_tool_visible(t.name, mode)]
        except Exception:
            return tools

    def _tools_to_api_format(self, tools: Tools) -> list[dict[str, Any]]:
        """Convert tools to slim OpenAI function-calling schema.

        Uses ultra_slim mode when config.ultra_slim_tools is True,
        which strips ALL parameter descriptions (~50% smaller schemas).
        Safe for strong models that understand parameter semantics from names alone.
        """
        ultra = self.config.ultra_slim_tools
        return [tool.to_openai_schema(ultra_slim=ultra) for tool in tools]

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

        # End previous turn and capture file snapshot diff.
        # This must happen before building the system message so that
        # _get_snapshot_diff_summary() can report changes from the
        # previous turn's tool executions.
        self._snapshot_tracker.end_turn()

        # Commit staged fast-memory updates at turn boundary (Hermes frozen-mid-session).
        # Updates staged during the previous turn are now persisted to disk,
        # and the next turn's system prompt will include the new content.
        try:
            commit_result = self._fast_memory.commit_at_turn_boundary()
            if commit_result.get("consolidation_needed"):
                for fname in commit_result["consolidation_needed"]:
                    check = self._fast_memory.check_consolidation()
                    info = check.get(fname, {})
                    if info.get("needed"):
                        # Inject a lightweight system reminder about consolidation
                        consolidate_msg = (
                            f"[System notice] {fname} is at {info['current']}/{info['max']} chars. "
                            f"Consider consolidating outdated entries to stay within limits."
                        )
                        self.messages.append(SystemMessage(content=consolidate_msg))
        except Exception:
            # Non-blocking: memory commit failure should not break the turn
            pass

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
            await self._compaction_mgr.auto_compact_if_needed()

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

        # Clean up orphaned tool calls before sending to API.
        # A ToolUseMessage without a corresponding ToolResultMessage
        # violates the API invariant and causes 400 errors.
        self._cleanup_orphaned_tool_calls()

        # Build API messages
        # System message must ALWAYS be included — it is not retained by the LLM
        # across turns. Skipping it on subsequent turns causes the model to forget
        # critical instructions like language preference.
        api_messages: list[dict[str, Any]] = []
        system_msg = self._build_system_message()
        api_messages.append({"role": "system", "content": system_msg.content})

        # Inject relevant memories based on the current user query.
        # These are ephemeral — injected per-turn without polluting self.messages.
        if prompt:
            try:
                from .services.memory_recall import find_relevant_memories, format_memory_attachment

                relevant = find_relevant_memories(prompt, self.config.cwd, top_k=3)
                if relevant:
                    mem_context = format_memory_attachment(relevant)
                    if mem_context:
                        api_messages.append({"role": "system", "content": mem_context})
            except Exception:
                pass

        api_messages.extend(self._convert_to_api_messages(self.messages))

        # Get available tools, applying permission-based pre-filtering
        # so the model cannot see tools it's not allowed to use.
        tools = self._get_visible_tools()

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

            # Dynamic thinking mode control (Qwen/DeepSeek)
            extra_body = self._build_extra_body(prompt)

            try:
                async for chunk in self.client.chat_completion(
                    messages=api_messages,
                    tools=self._tools_to_api_format(tools) if tools else None,
                    stream=True,
                    temperature=options.get("temperature", 0.7),
                    extra_body=extra_body,
                ):
                    # Check for cancellation during streaming
                    try:
                        await asyncio.sleep(0)  # Yield control to allow cancellation
                    except asyncio.CancelledError:
                        raise

                    choices = chunk.get("choices") or []
                    choice = choices[0] if choices else {}
                    delta = choice.get("delta") or {}
                    finish_reason = choice.get("finish_reason")

                    # OpenCode-style: capture usage from the final stream chunk
                    usage = chunk.get("usage")
                    if usage and isinstance(usage, dict):
                        # Reasoning tokens (DeepSeek/Qwen3 thinking mode)
                        ctd = usage.get("completion_tokens_details") or {}
                        reasoning = ctd.get("reasoning_tokens", 0) if isinstance(ctd, dict) else 0

                        self._token_mgr.record_api_usage(usage)

                    # Handle reasoning content (DeepSeek thinking mode only)
                    if getattr(self.client, "supports_reasoning_content", False):
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
                    logger.warning(
                        "Context window exceeded (estimated %d tokens > %d usable), "
                        "force-compacting and retrying...",
                        self.count_tokens(),
                        self._usable_context,
                    )
                    # Force compaction: skip should_compact check, since our
                    # local token counting may underestimate vs the actual API.
                    await self._compaction_mgr.intelligent_compact(force=True)
                    # Double-check: always run fallback compaction chain too
                    self._compaction_mgr._force_emergency_compact()
                    api_messages = self._convert_to_api_messages(self.messages)
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
            except LLMError as exc:
                # DeepSeek thinking mode: reasoning_content must be passed back.
                # If we lost it during message processing, strip all reasoning
                # from history and retry without thinking mode.
                error_text = str(exc)
                if "reasoning_content" in error_text and any(
                    isinstance(m, AssistantMessage) and m.reasoning_content for m in self.messages
                ):
                    logger.warning(
                        "DeepSeek reasoning_content error — stripping reasoning from "
                        "history and retrying without thinking mode..."
                    )
                    cleared = 0
                    for msg in self.messages:
                        if isinstance(msg, AssistantMessage) and msg.reasoning_content:
                            msg.reasoning_content = None
                            cleared += 1
                    logger.info(
                        "Cleared reasoning_content from %d assistant messages, retrying...",
                        cleared,
                    )
                    continue
                # Not a reasoning_content error — re-raise with guidance
                logger.error("LLM API error (unrecoverable): %s", exc)
                yield QueryResult(
                    message=AssistantMessage(
                        content=f"API Error: {exc}\n\n"
                        "The model returned an error. You can try:\n"
                        "- Sending a shorter message\n"
                        "- Restarting the conversation with /clear\n"
                        "- Checking your API key and quota"
                    ),
                    is_complete=True,
                )
                return

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
                    reasoning_content=(
                        (accumulated_reasoning or None)
                        if getattr(self.client, "supports_reasoning_content", False)
                        else None
                    ),
                )
                # Reasoning-Action consistency check (方案2)
                if accumulated_reasoning and current_tool_call:
                    inconsistency = self._check_reasoning_action_consistency(
                        accumulated_reasoning, current_tool_call
                    )
                    if inconsistency:
                        assistant_msg.content = (
                            f"[Self-check: {inconsistency}]\n\n" + assistant_msg.content
                        )
                # Reasoning-based doom loop detection (方案3)
                if accumulated_reasoning:
                    loop_warning = self._detect_reasoning_loop(accumulated_reasoning)
                    if loop_warning:
                        assistant_msg.content = (
                            f"[Warning: {loop_warning}]\n\n" + assistant_msg.content
                        )
                # Low-cost reasoning reflection (方案5)
                if accumulated_reasoning:
                    reflection = self._reflect_on_reasoning(accumulated_reasoning)
                    if reflection:
                        assistant_msg.content = (
                            f"[Reflection]\n{reflection}\n\n" + assistant_msg.content
                        )
                    # Update history
                    self._reasoning_history.append(accumulated_reasoning)
                    if len(self._reasoning_history) > self._max_reasoning_history:
                        self._reasoning_history.pop(0)
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
                        self._snapshot_tracker.track_file(file_path)
                    break

        # Dynamic truncation based on available context budget.
        # OpenCode-style: use usable_context (context_window - max_output_tokens)
        # so we never steal headroom reserved for the model's reply.
        if isinstance(content, str) and self._usable_context > 0:
            tokens_before = self.count_tokens()
            ratio = tokens_before / self._usable_context

            if ratio < 0.5:
                # Plenty of room: allow up to 10 % of usable context
                max_tool_tokens = int(self._usable_context * 0.10)
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

        # Strip ANSI escape sequences to keep LLM context clean
        if isinstance(content, str) and content:
            content = re.sub(r"\x1b\[[0-9;]*m", "", content)

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

    def count_tokens(self) -> int:
        """Count tokens in current conversation. Delegated to TokenManager."""
        return self._token_mgr.count_tokens()

    def is_overflow(self) -> bool:
        """OpenCode-style context overflow detection. Delegated to TokenManager."""
        return self._token_mgr.is_overflow()

    def get_token_budget(self) -> dict[str, Any]:
        """Get current token budget status. Delegated to TokenManager."""
        return self._token_mgr.get_token_budget()

    def get_token_baseline(self) -> dict[str, Any] | None:
        """Get the measured token baseline for this session. Delegated to TokenManager."""
        return self._token_mgr.get_token_baseline()

    def get_token_baseline_report(self) -> str:
        """Get a human-readable token baseline report. Delegated to TokenManager."""
        return self._token_mgr.get_token_baseline_report()

    def track_cost(self, tokens: int, cost_usd: float) -> None:
        """Track cost for this session. Delegated to TokenManager."""
        return self._token_mgr.track_cost(tokens, cost_usd)

    async def smart_compact(self) -> CompressionResult | None:
        """Intelligently compress conversation using summarization. Delegated to CompactionManager."""
        return await self._compaction_mgr.smart_compact()

    async def auto_compact_if_needed(self) -> bool:
        """Auto-compact conversation if token count exceeds threshold. Delegated to CompactionManager."""
        return await self._compaction_mgr.auto_compact_if_needed()

    async def intelligent_compact(self, force: bool = False) -> dict[str, Any]:
        """Intelligently compact conversation using the five-layer pipeline. Delegated to CompactionManager."""
        return await self._compaction_mgr.intelligent_compact(force=force)

    def _force_emergency_compact(self) -> None:
        """Emergency compaction for ContextWindowError recovery. Delegated to CompactionManager."""
        self._compaction_mgr._force_emergency_compact()

    def clear_history(self) -> None:
        """Clear conversation history and all derived state."""
        self.messages.clear()
        self._changed_files.clear()
        self._review_iteration_count = 0
        self._reasoning_history.clear()
        # Reset token manager caches so the next count starts fresh
        self._token_mgr.reset_cache()
        # Reset compaction tracking
        self._compaction_mgr._last_compaction_token_count = 0
        self._compaction_mgr._compaction_count = 0

    def save_session(self, path: str) -> None:
        """Save conversation session to a single JSON file (legacy format). Delegated to SessionManager."""
        self._session_mgr.save_session(path)

    def load_session(self, path: str) -> bool:
        """Load conversation session from a single JSON file (legacy format). Delegated to SessionManager."""
        result = self._session_mgr.load_session(path)
        if result:
            self._token_mgr.reset_cache()
        return result

    def save_to_storage(self, name: str | None = None) -> bool:
        """Save session to unified incremental storage. Delegated to SessionManager."""
        return self._session_mgr.save_to_storage(name)

    def set_on_notify(self, callback: Callable[[str, dict[str, Any]], None] | None) -> None:
        """Update the on_notify callback for both config and CompactionManager.

        CompactionManager holds a reference captured at init time, so changing
        config.on_notify alone does not propagate. This method ensures both
        copies stay in sync.
        """
        self.config.on_notify = callback
        self._compaction_mgr._on_notify = callback

    def load_from_storage(self, session_id: str | None = None) -> bool:
        """Load session from unified incremental storage. Delegated to SessionManager."""
        success, sid, messages = self._session_mgr.load_from_storage(session_id)
        if not success:
            return False
        self.messages[:] = messages
        self.session_id = sid
        # Reset token caches since the conversation state has completely changed
        self._token_mgr._last_api_usage = None
        self._token_mgr._last_api_usage_hash = None
        self._token_mgr._last_precise_count = None
        self._token_mgr._last_precise_count_hash = None
        self._compaction_mgr._last_compaction_token_count = 0
        return True


def create_query_engine(config: QueryEngineConfig) -> QueryEngine:
    """Create a query engine."""
    return QueryEngine(config)
