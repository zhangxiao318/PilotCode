"""REPL for PilotCode - Programming Assistant with Tool Support."""

import asyncio
import contextvars
import hashlib
import json
import os
import py_compile
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.status import Status
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style

from ..tools.registry import get_all_tools
from ..tools.base import ToolUseContext
from ..commands.base import process_user_input, CommandContext
from ..query_engine import QueryEngine, QueryEngineConfig
from ..state.app_state import get_default_app_state, AppState
from ..state.store import Store, set_global_store
from ..utils.config import get_global_config
from ..types.message import AssistantMessage, ToolUseMessage
from ..permissions import get_tool_executor
from ..utils.model_client import get_model_client, Message

# Context variable to prevent nested environment-diagnosis dead loops
_env_diagnosis_ctx: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "env_diagnosis_active", default=False
)


class REPL:
    """Programming Assistant REPL with full tool support."""

    # Default max iterations for tool calls (configurable via env var)
    DEFAULT_MAX_ITERATIONS = 100

    WRITE_TOOLS = {
        "FileEdit",
        "FileWrite",
        "ApplyPatch",
        "NotebookEdit",
        "CronCreate",
        "CronDelete",
        "CronUpdate",
    }

    def __init__(
        self, auto_allow: bool = False, max_iterations: int | None = None, read_only: bool = False
    ):
        self.console = Console()
        self.store = Store(get_default_app_state())
        set_global_store(self.store)

        # Allow override via parameter or environment variable
        if max_iterations is not None:
            self.max_iterations = max_iterations
        else:
            env_limit = os.environ.get("PILOTCODE_MAX_ITERATIONS")
            self.max_iterations = int(env_limit) if env_limit else self.DEFAULT_MAX_ITERATIONS

        get_global_config()
        self.store.set_state(lambda s: s)

        self.session = PromptSession(
            message="❯ ", style=Style.from_dict({"prompt": "#00aa00 bold"})
        )

        # Enable tools (filter out write tools in read-only mode)
        tools = get_all_tools()
        if read_only:
            tools = [t for t in tools if t.name not in self.WRITE_TOOLS]

        def _on_notify(event_type: str, payload: dict) -> None:
            if event_type == "auto_compact":
                saved = payload.get("tokens_saved", 0)
                cleared = payload.get("tool_results_cleared", 0)
                if payload.get("fallback"):
                    self.console.print(
                        f"[dim]🔄 Auto-compacted context (fallback, ~{saved} tokens saved)[/dim]"
                    )
                elif cleared > 0:
                    self.console.print(
                        f"[dim]🔄 Auto-compacted context ({cleared} old tool results cleared, ~{saved} tokens saved)[/dim]"
                    )
                else:
                    self.console.print(
                        f"[dim]🔄 Auto-compacted context (~{saved} tokens saved)[/dim]"
                    )

        global_cfg = get_global_config()
        self.query_engine = QueryEngine(
            QueryEngineConfig(
                cwd=self.store.get_state().cwd,
                tools=tools,
                get_app_state=self.store.get_state,
                set_app_state=lambda f: self.store.set_state(f),
                auto_compact=True,
                on_notify=_on_notify,
                auto_review=global_cfg.auto_review,
                max_review_iterations=global_cfg.max_review_iterations,
            )
        )

        # Set up tool executor with our console
        self.tool_executor = get_tool_executor(self.console)

        # Auto-allow mode for testing
        self.auto_allow = auto_allow
        if auto_allow:
            # Grant all permissions automatically
            from ..permissions import get_permission_manager, PermissionLevel, ToolPermission

            pm = get_permission_manager()
            for tool in tools:
                pm._permissions[tool.name] = ToolPermission(
                    tool_name=tool.name, level=PermissionLevel.ALWAYS_ALLOW
                )
            self.console.print(
                "[dim]⚡ Auto-allow mode enabled - all tool executions will be allowed[/dim]\n"
            )

        self.running = True
        self.loop_guard = LoopGuard()

    def _notify_user(self, event_type: str, payload: dict) -> None:
        """Display a system notification to the user.

        Unified entry point for user-facing notices (e.g., max iterations,
        context warnings) across all UI modes.
        """
        if event_type == "max_iterations_reached":
            max_iters = payload.get("max_iterations", self.DEFAULT_MAX_ITERATIONS)
            self.console.print(
                f"[yellow]⏹️  Reached maximum tool iterations ({max_iters}). "
                f"Task paused. Send another message to continue.[/yellow]"
            )
        elif event_type == "context_warning":
            usage_pct = payload.get("usage_pct", 0)
            self.console.print(f"[yellow]⚠️  Context at {usage_pct}% — approaching limit.[/yellow]")
        elif event_type == "permission_denied":
            self.console.print("[red]⛔ Tool execution denied by user. Task stopped.[/red]")
        elif event_type == "loop_detected":
            reason = payload.get("reason", "unknown")
            warning = (
                f"[SYSTEM WARNING] DETECTED LOOP: {reason}. "
                "You have been repeating the same tool calls. STOP exploring and "
                "produce your final answer or code changes immediately. "
                "Do NOT call the same tools again."
            )
            self.console.print(f"[yellow]{warning}[/yellow]")
        else:
            # Generic fallback
            self.console.print(f"[dim]{payload.get('message', '')}[/dim]")

    def print_header(self) -> None:
        """Print welcome header."""
        self.console.print(
            Panel.fit(
                "[bold cyan]PilotCode[/bold cyan] [dim]v0.2.0[/dim]\n"
                "[cyan]AI Programming Assistant[/cyan]\n"
                "[dim]Type /help for commands, or ask me to write code![/dim]",
                border_style="cyan",
            )
        )
        self.console.print("\n[bold green]💡 Tips:[/bold green]")
        self.console.print("  • 'Create a Python script that...'")
        self.console.print("  • 'Fix the bug in this code...'")
        self.console.print("  • 'Write tests for...'")
        self.console.print("  • Tools: FileRead, FileWrite, FileEdit, Bash, Glob, Grep")
        self.console.print("  • I will ask for permission before making changes\n")

    async def handle_command(self, input_text: str) -> bool:
        """Handle slash commands."""
        context = CommandContext(cwd=self.store.get_state().cwd, query_engine=self.query_engine)
        is_command, result = await process_user_input(input_text, context)
        if is_command:
            self.console.print(result)
            return True
        return False

    # ------------------------------------------------------------------
    # Four-layer rendering framework
    # ------------------------------------------------------------------

    def _render_status(self, event_type: str, **kwargs) -> None:
        """Status Layer: persistent state indicators.

        Currently rendered inline via progress text; will be extended
        to a dedicated status bar when the Status Layer is populated.
        """
        # Placeholder: status is currently shown via Status() spinner in process_response.
        pass

    def _render_conversational_assistant(self, content: str, is_complete: bool) -> None:
        """Conversational Layer: assistant response text.

        When is_complete=False, content is streamed in real-time via
        stdout so the user sees the response as it generates.
        When is_complete=True, the full response is rendered as Markdown.
        """
        if not content:
            return
        if is_complete:
            self.console.print()
            self.console.print(Markdown(content))
            self.console.print()
            sys.stdout.flush()
        else:
            # Real-time streaming: write raw text directly to avoid
            # Markdown parsing overhead and re-rendering artifacts.
            sys.stdout.write(content)
            sys.stdout.flush()

    def _render_conversational_tool_use(
        self,
        tool_name: str,
        tool_input: dict,
        iteration: int,
        max_iterations: int,
        tool_idx: int = 1,
        total_tools: int = 1,
    ) -> None:
        """Conversational Layer: tool call notification."""
        tool_progress = f"[turn {iteration}/{max_iterations}]"
        if total_tools > 1:
            tool_progress += f" [tool {tool_idx}/{total_tools}]"
        self.console.print(f"\n[dim][T] {tool_progress} {tool_name}[/dim]")

    def _render_conversational_tool_result(
        self, tool_name: str, success: bool, message: str
    ) -> None:
        """Conversational Layer: tool execution result."""
        if success:
            self.console.print(f"[dim]✓ {tool_name} completed[/dim]")
        else:
            self.console.print(f"[red]✗ {message}[/red]")

    def _render_system(self, event_type: str, **payload) -> None:
        """System Layer: ephemeral notices, warnings, errors.

        Delegates to the unified _notify_user method for consistency.
        """
        self._notify_user(event_type, payload)

    # ------------------------------------------------------------------

    async def process_response(self, prompt: str) -> None:
        """Process a prompt through the LLM with tool support."""
        full_content = ""
        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1
            pending_tools = []

            # -- Status Layer: show processing indicator --
            status_text = (
                f"[cyan]Thinking...[/cyan] [dim](turn {iteration}/{self.max_iterations})[/dim]"
            )
            has_streamed = False
            with Status(status_text, console=self.console, spinner="dots"):
                try:
                    async for result in self.query_engine.submit_message(prompt):
                        msg = result.message

                        # -- Conversational Layer: assistant streaming --
                        if isinstance(msg, AssistantMessage):
                            if isinstance(msg.content, str):
                                if result.is_complete:
                                    if msg.content and len(msg.content) >= len(full_content):
                                        full_content = msg.content
                                else:
                                    if msg.content:
                                        full_content += msg.content
                                        self._render_conversational_assistant(
                                            msg.content, is_complete=False
                                        )
                                        has_streamed = True

                        # -- Conversational Layer: tool use --
                        elif isinstance(msg, ToolUseMessage):
                            pending_tools.append(msg)

                except Exception as e:
                    # -- System Layer: error --
                    self._render_system("error", content=str(e))
                    return

            # -- Conversational Layer: flush assistant response --
            if full_content:
                if has_streamed:
                    # Already streamed in real-time; just ensure a clean newline
                    # and skip Markdown re-render to avoid duplicate output.
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    self.console.print()
                else:
                    self._render_conversational_assistant(full_content, is_complete=True)
                full_content = ""

            # -- Interactive + Conversational Layer: execute tools --
            if not pending_tools:
                break

            permission_denied = False
            for tool_idx, tool_msg in enumerate(pending_tools, 1):
                # OpenCode-style doom-loop detection: check at the moment of call
                doom_reason = self.loop_guard.check_call(tool_msg.name, tool_msg.input)
                if doom_reason:
                    self.loop_guard.loop_count += 1
                    self._render_system("loop_detected", reason=doom_reason)
                    warning = (
                        f"[SYSTEM WARNING] DETECTED LOOP: {doom_reason}. "
                        f"You have been repeating the same tool calls. STOP exploring and "
                        f"produce your final answer or code changes immediately. "
                        f"Do NOT call the same tools again."
                    )
                    self.query_engine.messages.append(AssistantMessage(content=warning))
                    # Block remaining tools in this round
                    for remaining_msg in pending_tools[tool_idx - 1 :]:
                        self.query_engine.add_tool_result(
                            remaining_msg.tool_use_id,
                            f"Blocked by loop guard: {doom_reason}",
                            is_error=True,
                        )
                    break

                self._render_conversational_tool_use(
                    tool_msg.name,
                    tool_msg.input,
                    iteration,
                    self.max_iterations,
                    tool_idx=tool_idx,
                    total_tools=len(pending_tools),
                )

                context = ToolUseContext(
                    get_app_state=self.store.get_state,
                    set_app_state=lambda f: self.store.set_state(f),
                    cwd=getattr(self.store.get_state(), "cwd", ""),
                )

                def _on_progress(data):
                    if isinstance(data, dict) and data.get("type") == "bash_output":
                        line = data.get("line", "")
                        is_progress = data.get("is_progress", False)
                        if is_progress:
                            import sys

                            sys.stdout.write(f"\r{line}")
                            sys.stdout.flush()
                        else:
                            self.console.print(line)

                exec_result = await self.tool_executor.execute_tool_by_name(
                    tool_msg.name, tool_msg.input, context, on_progress=_on_progress
                )

                # -- Permission denied: stop remaining tools and abort turn --
                if not exec_result.permission_granted:
                    self.query_engine.add_tool_result(
                        tool_msg.tool_use_id,
                        "Tool execution denied by user",
                        is_error=True,
                    )
                    self._render_system("permission_denied")
                    permission_denied = True
                    break

                result_content = ""
                if exec_result.success and exec_result.result:
                    result_content = (
                        str(exec_result.result.data) if exec_result.result.data else "Success"
                    )
                    self._render_conversational_tool_result(
                        tool_msg.name, success=True, message="completed"
                    )
                else:
                    result_content = exec_result.message
                    self._render_conversational_tool_result(
                        tool_msg.name, success=False, message=exec_result.message
                    )

                    # --- Environment diagnosis (interactive REPL mode) ---
                    if not getattr(self, "_env_diagnosis_fired", False):
                        from ..utils.env_diagnosis import (
                            looks_like_environment_error,
                            diagnose_and_fix_environment,
                        )

                        if looks_like_environment_error(result_content):
                            self._env_diagnosis_fired = True
                            fixed = await diagnose_and_fix_environment(
                                result_content,
                                self.store.get_state().cwd,
                                auto_allow=self.auto_allow,
                                interactive=True,
                            )
                            if fixed:
                                result_content += "\n[ENV FIX APPLIED] Environment issue was diagnosed and fixed automatically. You may retry the previous step."
                            else:
                                result_content += "\n[ENV FIX FAILED] Could not fix the environment issue automatically. You may need to fix it manually."

                self.query_engine.add_tool_result(
                    tool_msg.tool_use_id, result_content, is_error=not exec_result.success
                )
                sys.stdout.flush()

            if permission_denied:
                break

            # -- System Layer: loop detection --
            loop_reason = self.loop_guard.record(pending_tools)
            if loop_reason:
                self._render_system("loop_detected", reason=loop_reason)
                warning = (
                    f"[SYSTEM WARNING] DETECTED LOOP: {loop_reason}. "
                    f"You have been repeating the same tool calls. STOP exploring and "
                    f"produce your final answer or code changes immediately. "
                    f"Do NOT call the same tools again."
                )
                # Inject warning so the model sees it on the next turn
                self.query_engine.messages.append(AssistantMessage(content=warning))

            # -- Status Layer: turn budget prompts (injected into model context) --
            remaining = self.max_iterations - iteration
            if remaining <= 5:
                prompt = f"URGENT: You have only {remaining} tool-call rounds left. If you know the fix, APPLY IT NOW. If not, make your best edit and declare completion."
            elif remaining <= 15:
                prompt = f"REMINDER: {remaining} tool-call rounds remain. Focus on making the actual code changes, not further reading."
            else:
                prompt = "Please continue based on the tool results above."

        # -- System Layer: max iterations reached --
        if iteration >= self.max_iterations:
            self._render_system("max_iterations_reached", max_iterations=self.max_iterations)

        # Ensure content is visible above the prompt on Windows
        # Use standard print to ensure compatibility with prompt_toolkit
        print("\n" * 2, end="", flush=True)

    async def run(self) -> None:
        """Run the REPL."""
        self.print_header()

        while self.running:
            try:
                user_input = await self.session.prompt_async()
                user_input = user_input.strip()

                if not user_input:
                    continue

                if await self.handle_command(user_input):
                    continue

                await self.process_response(user_input)

            except KeyboardInterrupt:
                self.console.print("\n[yellow]Use /quit to exit[/yellow]")
                continue
            except EOFError:
                break
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")
                import traceback

                traceback.print_exc()
                continue

        self.console.print("\n[dim]Goodbye! 👋[/dim]")


def run_repl(auto_allow: bool = False, max_iterations: int | None = None) -> None:
    """Run the REPL.

    Args:
        auto_allow: Automatically allow all tool executions
        max_iterations: Maximum tool execution rounds per query (default: 50)
    """
    repl = REPL(auto_allow=auto_allow, max_iterations=max_iterations)
    try:
        asyncio.run(repl.run())
    except KeyboardInterrupt:
        print("\nGoodbye! 👋")


def assess_project_complexity(cwd: str) -> dict[str, Any]:
    """Quickly assess codebase size and language complexity via pathlib.

    Cross-platform replacement for the previous Linux find/wc based approach
    that failed silently on Windows.

    Returns dict with file_count, language_scores, loc_estimate, complexity_score.
    """
    result: dict[str, Any] = {
        "file_count": 0,
        "language_scores": {},
        "loc_estimate": 0,
        "complexity_score": 0.0,
    }

    try:
        root = Path(cwd).resolve()
        if not root.exists():
            return result

        lang_weights = {
            ".py": 1.0,
            ".js": 1.0,
            ".ts": 1.2,
            ".jsx": 1.2,
            ".tsx": 1.2,
            ".java": 1.3,
            ".go": 1.1,
            ".rb": 1.0,
            ".rs": 1.4,
            ".cpp": 1.5,
            ".cc": 1.5,
            ".c": 1.3,
            ".h": 1.0,
            ".hpp": 1.5,
        }

        skip_dirs = {
            "node_modules",
            ".git",
            "__pycache__",
            "venv",
            ".venv",
            "build",
            "dist",
            ".pytest_cache",
            ".mypy_cache",
            ".tox",
            ".egg-info",
            ".eggs",
            "site-packages",
        }

        file_count = 0
        lang_scores: dict[str, int] = {}
        loc_estimate = 0

        for item in root.rglob("*"):
            if not item.is_file():
                continue
            if any(part in skip_dirs for part in item.parts):
                continue
            try:
                rel_parts = item.relative_to(root).parts
            except ValueError:
                continue
            if len(rel_parts) > 3:
                continue

            ext = item.suffix.lower()
            if ext in lang_weights:
                file_count += 1
                key = ext.lstrip(".")
                lang_scores[key] = lang_scores.get(key, 0) + 1
                try:
                    with item.open("r", encoding="utf-8", errors="ignore") as fh:
                        for _ in range(5000):
                            line = fh.readline()
                            if not line:
                                break
                            loc_estimate += 1
                except Exception:
                    pass

        result["file_count"] = file_count
        result["language_scores"] = lang_scores
        result["loc_estimate"] = loc_estimate

        complexity = 0.0
        if file_count > 500:
            complexity += 2.0
        elif file_count > 200:
            complexity += 1.5
        elif file_count > 50:
            complexity += 0.8
        else:
            complexity += 0.3

        if loc_estimate > 100000:
            complexity += 2.0
        elif loc_estimate > 30000:
            complexity += 1.0
        elif loc_estimate > 10000:
            complexity += 0.5

        for ext, cnt in lang_scores.items():
            weight = lang_weights.get("." + ext, 1.0)
            if cnt > 50:
                complexity += 0.5 * weight
            elif cnt > 10:
                complexity += 0.2 * weight

        result["complexity_score"] = round(complexity, 2)
    except Exception:
        pass

    return result


def _extract_target_path(prompt: str) -> str | None:
    """Extract a filesystem path from the user prompt.

    Looks for absolute paths (Windows e.g. C:\\dir and Unix e.g. /home/dir)
    and relative paths. Returns the first plausible directory path found,
    or None if no path is detected.
    """
    import re

    # Windows absolute paths: e.g. E:\\test2, D:\\Source\\...
    win_path = re.search(r"[A-Za-z]:[\\/][^\s\"'\n]*", prompt)
    if win_path:
        path = win_path.group(0).replace("/", "\\")
        if os.path.isdir(path):
            return path

    # Unix absolute paths: e.g. /home/user/project, /tmp/foo
    unix_path = re.search(r"/[\w./-]+[^\s\"'\n]*", prompt)
    if unix_path:
        path = unix_path.group(0)
        if os.path.isdir(path):
            return path

    # Relative paths with common directory indicators
    rel_path = re.search(
        r"(?:目录|文件夹|folder|directory|path|dir)\s*[:：]?\s*([^\s\"'\n]+)", prompt, re.IGNORECASE
    )
    if rel_path:
        path = rel_path.group(1)
        if os.path.isdir(path):
            return path

    return None


def _compute_task_complexity(prompt: str, project_stats: dict[str, Any]) -> float:
    """Compute a composite complexity score (0-10 scale).

    Returns a high positive score for complex dev tasks, a high negative score
    for obviously non-dev tasks (greetings, Q&A), and mid-range for ambiguous.
    """
    score = project_stats.get("complexity_score", 0.0)

    prompt_lower = prompt.lower()

    # ---------- Non-development tasks: strongly signal DIRECT ----------
    direct_signals = [
        # Greetings / social
        "hello",
        "hi ",
        "hey",
        "你好",
        "您好",
        "哈喽",
        "在吗",
        "在么",
        "good morning",
        "good afternoon",
        "good evening",
        # General Q&A / explanation
        "explain",
        "what is",
        "what are",
        "how to",
        "how does",
        "how do",
        "tell me about",
        "describe",
        "overview",
        "summary",
        "什么是",
        "什么是",
        "怎么",
        "如何",
        "解释一下",
        "说明",
        "介绍",
        "谢谢",
        "感谢",
        "再见",
        "拜拜",
        # Simple help
        "help",
        "can you",
        "could you",
        "would you",
        "please",
        "帮忙",
        "帮我把",
        "帮我",
        "请",
        "能不能",
    ]
    for sig in direct_signals:
        if sig in prompt_lower:
            return -5.0  # Force DIRECT, skip everything else

    # ---------- Hard complexity signals ----------
    hard_keywords = [
        # English
        "refactor",
        "architecture",
        "restructure",
        "redesign",
        "implement",
        "add support",
        "introduce",
        "debug",
        "fix bug",
        "bug report",
        "regression",
        "cross-file",
        "multiple files",
        "across the codebase",
        # Chinese
        "重构",
        "架构",
        "重新设计",
        "实现",
        "添加功能",
        "引入",
        "调试",
        "修复 bug",
        "修复问题",
        "跨文件",
        "多个文件",
        "添加支持",
        "性能优化",
        "性能问题",
        "新功能",
        "开发",
        "编写",
        "集成",
        "api",
        "docker",
        "kubernetes",
        "k8s",
        "ci/cd",
    ]
    medium_keywords = [
        # English
        "update",
        "modify",
        "change behavior",
        "enhance",
        "improve",
        "optimize",
        "performance",
        "upgrade",
        "migrate",
        "analyze",
        "analyse",
        # Chinese
        "更新",
        "修改",
        "改进",
        "优化",
        "增强",
        "升级",
        "迁移",
        "改动",
        "调整",
        "变更",
        "完善",
        "测试",
        "写测试",
        "添加测试",
        "单元测试",
        "算法",
        "数据结构",
        "分析",
    ]
    easy_keywords = [
        # English
        "rename",
        "move",
        "extract",
        "simple",
        "single file",
        "update docstring",
        "add comment",
        "fix typo",
        "format",
        # Chinese
        "重命名",
        "移动",
        "提取",
        "简单",
        "单文件",
        "修复拼写",
        "格式化",
        "加注释",
        "改名字",
        "readme",
        "文档",
        "注释",
        "配置文件",
        "配置",
    ]

    for kw in hard_keywords:
        if kw in prompt_lower:
            score += 1.5
            break
    for kw in medium_keywords:
        if kw in prompt_lower:
            score += 0.8
            break
    for kw in easy_keywords:
        if kw in prompt_lower:
            score -= 0.5
            break

    # SWE-bench specific signals
    if "swe-bench" in prompt_lower or "test_" in prompt_lower or "tests/" in prompt_lower:
        score += 1.0

    return score


async def classify_task_complexity(prompt: str, cwd: str | None = None) -> str:
    """Classify whether the task needs planning mode (PLAN) or direct mode (DIRECT).

    Strategy:
      1. Fast heuristic rules for obvious cases (no LLM call).
      2. For ambiguous cases, use a lightweight LLM call as tie-breaker.
      3. Never let project size alone force PLAN — only the *task content* should.

    Returns:
        "PLAN"  -> multi-step, multi-file, or complex logic.
        "DIRECT"-> simple Q&A, greeting, explanation, or single edit.
    """
    effective_cwd = cwd if cwd else str(os.getcwd())

    # Try to detect a target directory/path mentioned in the prompt
    # and assess complexity of that path instead of the current cwd
    target_path = _extract_target_path(prompt) or effective_cwd
    project_stats = assess_project_complexity(target_path)
    composite_score = _compute_task_complexity(prompt, project_stats)

    # ---- Rule 1: Explicit non-dev tasks → DIRECT (no LLM) ----
    if composite_score <= -3.0:
        return "DIRECT"

    # ---- Rule 3: Clear dev complexity → PLAN (no LLM) ----
    if composite_score >= 2.5:
        return "PLAN"

    # ---- Rule 2: Very short, no code signals → DIRECT ----
    prompt_stripped = prompt.strip()
    if len(prompt_stripped) < 20 and not any(
        c in prompt_stripped for c in "._/=(){}[];:#$%&@!^*+-"
    ):
        return "DIRECT"

    # ---- Rule 4: Ambiguous middle ground → lightweight LLM ----
    classifier_prompt = (
        "You are a strict task router. Decide if this user request requires "
        "multi-step planning across multiple files (PLAN) or can be answered "
        "directly in a single turn (DIRECT).\n\n"
        f"Project size: {project_stats.get('file_count', 0)} source files.\n"
        f"User request ({len(prompt)} chars):\n{prompt}\n\n"
        "Rules:\n"
        "- DIRECT for: greetings, general Q&A, explanations, asking for help, "
        "single-file edits, reading a single file, simple formatting.\n"
        "- PLAN for: implementing features, refactoring, bug fixing across files, "
        "adding tests to multiple modules, architecture changes, "
        "analyzing or exploring large directories / projects, "
        "cross-file dependency analysis, codebase-wide searches.\n\n"
        "Answer with EXACTLY one word: PLAN or DIRECT. No punctuation."
    )

    client = get_model_client()
    messages = [
        Message(
            role="system",
            content="You classify coding tasks. Reply with exactly one word: PLAN or DIRECT.",
        ),
        Message(role="user", content=classifier_prompt),
    ]

    try:
        # client.chat_completion is an async generator; always iterate with async for
        chunks = []
        async for chunk in client.chat_completion(
            messages=messages,
            tools=None,
            temperature=0.0,
            stream=False,
        ):
            chunks.append(chunk)

        if not chunks:
            return "PLAN"

        content = ""
        response = chunks[0]
        if isinstance(response, dict):
            choices = response.get("choices", [{}])
            if choices:
                delta = choices[0].get("delta", {})
                if delta:
                    content = delta.get("content", "")
                else:
                    content = choices[0].get("message", {}).get("content", "")
        content = content.strip().upper()

        if "DIRECT" in content:
            return "DIRECT"
        return "PLAN"
    except Exception:
        return "PLAN"


async def _generate_structured_output(
    system_prompt: str,
    user_prompt: str,
    progress_callback: Callable[[str], None] | None = None,
) -> str:
    """Generate structured text output directly from the LLM without tool calls.

    Use this for Plan and Verify phases where the model should ONLY output
    structured text (e.g. JSON) and must NOT explore the codebase further.
    """
    if progress_callback:
        progress_callback("[LLM] Sending structured output request (no tools)")

    client = get_model_client()
    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_prompt),
    ]

    response_text = ""
    async for chunk in client.chat_completion(
        messages=messages,
        tools=None,
        temperature=0.0,
        stream=False,
    ):
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        content = delta.get("content", "")
        if content:
            response_text += content

    return response_text.strip()


class LoopGuard:
    """Detects repetitive tool-call patterns to break LLM loops.

    Works across all PilotCode modes: REPL, headless, TUI, and Web.

    Implements two detection strategies:
    1. Round-level detection (record): checks across turns for repeating sequences.
    2. Per-call detection (check_call): OpenCode-style consecutive identical call
       detection (threshold = 3), triggered at the moment a tool call is issued.
    """

    def __init__(self, window_size: int = 6):
        self.window_size = window_size
        self.round_fingerprints: list[tuple[str, ...]] = []
        self.loop_count: int = 0
        # OpenCode-style per-call history for real-time doom-loop detection
        self._call_history: list[tuple[str, str]] = []

    @staticmethod
    def _fingerprint(tool_msg: ToolUseMessage) -> str:
        import hashlib

        name = tool_msg.name
        input_str = json.dumps(tool_msg.input, sort_keys=True, default=str)
        return f"{name}:{hashlib.md5(input_str.encode()).hexdigest()[:8]}"

    @staticmethod
    def _hash_input(tool_input: dict[str, Any]) -> str:
        import hashlib

        input_str = json.dumps(tool_input, sort_keys=True, default=str)
        return hashlib.md5(input_str.encode()).hexdigest()[:8]

    def check_call(self, tool_name: str, tool_input: dict[str, Any]) -> str | None:
        """OpenCode-style per-call doom-loop detection.

        Records the call and checks whether the last 3 calls are the same tool
        with identical input.  Returns a reason string if a loop is detected.
        """
        h = self._hash_input(tool_input)
        self._call_history.append((tool_name, h))
        # Keep only the last 3 calls (OpenCode DOOM_LOOP_THRESHOLD = 3)
        if len(self._call_history) > 3:
            self._call_history.pop(0)
        if len(self._call_history) == 3:
            if self._call_history[0] == self._call_history[1] == self._call_history[2]:
                return f"tool '{tool_name}' called 3 times consecutively with identical input"
        return None

    def record(self, tool_calls: list[ToolUseMessage]) -> str | None:
        """Record a round and return loop reason if detected."""
        fp = tuple(self._fingerprint(t) for t in tool_calls)
        self.round_fingerprints.append(fp)
        if len(self.round_fingerprints) > self.window_size:
            self.round_fingerprints.pop(0)
        return self._detect()

    def reset(self) -> None:
        """Clear history (e.g. when user starts a new task)."""
        self.round_fingerprints.clear()
        self._call_history.clear()

    def _detect(self) -> str | None:
        recent = self.round_fingerprints
        if len(recent) < 3:
            return None

        flat = [fp for r in recent for fp in r]
        from collections import Counter

        counts = Counter(flat)

        # Rule 1: Same single tool called repeatedly with identical input
        for fp, cnt in counts.items():
            if cnt >= 3:
                return f"tool '{fp.split(':')[0]}' called {cnt} times with identical input"

        # Rule 2: Exact sequence repetition (ABAB, ABCABC)
        for period in (2, 3):
            if len(recent) >= period * 2:
                last = recent[-period:]
                prev = recent[-(period * 2) : -period]
                if last == prev:
                    return f"repeating {period}-round tool sequence"

        # Rule 3: Alternating between two patterns (A→B→A→B→A→B)
        if len(recent) >= 4:
            uniq = list(dict.fromkeys(recent))
            if len(uniq) == 2 and recent.count(uniq[0]) >= 2 and recent.count(uniq[1]) >= 2:
                return "alternating between two tool patterns"

        # Rule 4: Same tool called consecutively >=5 times with FEW unique inputs.
        # If all 5 calls have different parameters, it's normal exploration (e.g.
        # reading 5 different files, grepping 5 different keywords).
        # If only 1-2 unique parameters keep repeating, it's a loop.
        # Exclude exploration tools entirely — they are always legitimate.
        _exploration_tools = {
            "FileRead",
            "Glob",
            "Grep",
            "CodeSearch",
            "CodeIndex",
            "GitDiff",
            "GitStatus",
            "FileTree",
        }
        if len(flat) >= 5:
            last5_fp = flat[-5:]
            last5_tools = [f.split(":")[0] for f in last5_fp]
            tool_name = last5_tools[0]
            if (
                len(set(last5_tools)) == 1
                and tool_name not in _exploration_tools
                and len(set(last5_fp)) <= 2
            ):
                return (
                    f"tool '{tool_name}' called 5+ times consecutively with only "
                    f"{len(set(last5_fp))} unique input pattern(s) — likely stuck"
                )

        return None


async def run_headless(
    prompt: str,
    auto_allow: bool = False,
    json_mode: bool = False,
    max_iterations: int = 100,
    initial_messages: list | None = None,
    cwd: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
    read_only: bool = False,
    disable_env_diagnosis: bool = False,
    env_diagnosis_count: int = 0,
) -> dict[str, Any]:
    """Run a single prompt in headless mode and return structured output.

    Returns a dict with keys:
        - response: final assistant text
        - tool_calls: list of executed tools with results
        - success: bool
    """
    import json as json_mod
    from ..permissions import get_permission_manager, PermissionLevel, ToolPermission

    # Create initial state with correct cwd

    # Ensure cwd is valid (not None, not empty)
    effective_cwd = cwd if cwd else str(os.getcwd())
    initial_state = AppState(cwd=effective_cwd)
    store = Store(initial_state)
    set_global_store(store)

    working_dir = store.get_state().cwd

    write_tools = {
        "FileEdit",
        "FileWrite",
        "ApplyPatch",
        "NotebookEdit",
        "CronCreate",
        "CronDelete",
        "CronUpdate",
    }
    tools = get_all_tools()
    if read_only:
        tools = [t for t in tools if t.name not in write_tools]
    global_cfg = get_global_config()
    query_engine = QueryEngine(
        QueryEngineConfig(
            cwd=working_dir,
            tools=tools,
            get_app_state=store.get_state,
            set_app_state=lambda f: store.set_state(f),
            auto_compact=True,
            auto_review=global_cfg.auto_review,
            max_review_iterations=global_cfg.max_review_iterations,
        )
    )

    # Load initial messages if provided (for session continuity)
    if initial_messages:
        from ..types.message import deserialize_messages

        if isinstance(initial_messages[0], dict):
            query_engine.messages = deserialize_messages(initial_messages)
        else:
            query_engine.messages = initial_messages

    tool_executor = get_tool_executor()

    if auto_allow:
        pm = get_permission_manager()
        for tool in tools:
            pm._permissions[tool.name] = ToolPermission(
                tool_name=tool.name, level=PermissionLevel.ALWAYS_ALLOW
            )

    tool_calls_log: list[dict[str, Any]] = []
    response_text = ""
    success = True
    loop_guard = LoopGuard()

    try:
        current_prompt = prompt
        turn = 0
        for _ in range(max_iterations):
            turn += 1
            pending_tools: list[ToolUseMessage] = []

            async for result in query_engine.submit_message(
                current_prompt, options={"temperature": 0.0}
            ):
                msg = result.message
                if isinstance(msg, AssistantMessage):
                    if isinstance(msg.content, str):
                        if result.is_complete:
                            # Final message: use it if non-empty and longer than accumulated
                            # This handles case where accumulated content has more detail
                            if msg.content and len(msg.content) >= len(response_text):
                                response_text = msg.content
                            # else: keep accumulated response_text
                        else:
                            # Accumulate streaming content
                            if msg.content:
                                response_text += msg.content
                elif isinstance(msg, ToolUseMessage):
                    pending_tools.append(msg)

            if not pending_tools:
                break

            # Loop detection
            loop_reason = loop_guard.record(pending_tools)
            if loop_reason:
                loop_guard.loop_count += 1
                if progress_callback:
                    progress_callback(f"[LOOP GUARD] {loop_reason} — blocking tools")
                else:
                    print(f"[LOOP GUARD] {loop_reason} — blocking tools", flush=True)

                # Block all pending tools immediately and force final answer
                for tool_msg in pending_tools:
                    forced_result = (
                        f"[SYSTEM ERROR] LOOP DETECTED: {loop_reason}. "
                        f"Tool execution has been blocked. You MUST provide your final answer NOW "
                        f"without any more tool calls."
                    )
                    query_engine.add_tool_result(tool_msg.tool_use_id, forced_result, is_error=True)
                current_prompt = (
                    "CRITICAL: You are in a tool-call loop. All pending tool calls were blocked. "
                    "Summarize what you have done so far and declare completion if the fix is applied. "
                    "Do NOT call any more tools."
                )
                continue

            write_tool_names = {
                "FileEdit",
                "FileWrite",
                "ApplyPatch",
                "NotebookEdit",
                "CronCreate",
                "CronDelete",
                "CronUpdate",
            }
            for tool_idx, tool_msg in enumerate(pending_tools, 1):
                # OpenCode-style doom-loop detection: check at the moment of call
                doom_reason = loop_guard.check_call(tool_msg.name, tool_msg.input)
                if doom_reason:
                    loop_guard.loop_count += 1
                    if progress_callback:
                        progress_callback(f"[DOOM LOOP] {doom_reason} — blocking remaining tools")
                    else:
                        print(f"[DOOM LOOP] {doom_reason} — blocking remaining tools", flush=True)
                    for remaining_msg in pending_tools[tool_idx - 1 :]:
                        forced_result = (
                            f"[SYSTEM ERROR] DOOM LOOP DETECTED: {doom_reason}. "
                            f"Tool execution has been blocked."
                        )
                        query_engine.add_tool_result(
                            remaining_msg.tool_use_id, forced_result, is_error=True
                        )
                    current_prompt = (
                        "CRITICAL: You are in a tool-call loop. All pending tool calls were blocked. "
                        "Summarize what you have done so far and declare completion. "
                        "Do NOT call any more tools."
                    )
                    break

                if not json_mode:
                    tool_progress = f"[turn {turn}/{max_iterations}]"
                    if len(pending_tools) > 1:
                        tool_progress += f" [tool {tool_idx}/{len(pending_tools)}]"
                    progress_msg = f"[T] {tool_progress} {tool_msg.name}"
                    if progress_callback:
                        progress_callback(progress_msg)
                    else:
                        print(progress_msg, flush=True)

                # Enforce read-only mode at execution layer as well
                if read_only and tool_msg.name in write_tool_names:
                    result_content = (
                        f"Tool '{tool_msg.name}' is not available in read-only planning mode. "
                        "You can only use read-only tools (FileRead, Grep, Glob, CodeSearch, Bash, GitDiff, etc.)."
                    )
                    success = False
                    exec_result = None
                else:
                    context = ToolUseContext(
                        get_app_state=store.get_state,
                        set_app_state=lambda f: store.set_state(f),
                        cwd=getattr(store.get_state(), "cwd", ""),
                    )

                    def _on_progress_headless(data):
                        if isinstance(data, dict) and data.get("type") == "bash_output":
                            line = data.get("line", "")
                            if line and progress_callback:
                                progress_callback(f"[BASH] {line}")

                    exec_result = await tool_executor.execute_tool_by_name(
                        tool_msg.name, tool_msg.input, context, on_progress=_on_progress_headless
                    )
                    result_content = ""
                    if exec_result.success and exec_result.result:
                        result_content = (
                            str(exec_result.result.data) if exec_result.result.data else "Success"
                        )
                    else:
                        result_content = exec_result.message
                        success = False

                    # --- Environment diagnosis (headless mode) ---
                    # Skip if nested inside another diagnosis (prevents recursive dead loops)
                    already_diagnosing = _env_diagnosis_ctx.get()
                    if (
                        not already_diagnosing
                        and not disable_env_diagnosis
                        and env_diagnosis_count < 1
                    ):
                        from pilotcode.utils.env_diagnosis import (
                            looks_like_environment_error,
                            diagnose_and_fix_environment,
                        )

                        if looks_like_environment_error(result_content):
                            env_diagnosis_count += 1
                            fixed = await diagnose_and_fix_environment(
                                result_content,
                                working_dir,
                                auto_allow=auto_allow,
                                progress_callback=progress_callback,
                                interactive=False,
                            )
                            if fixed:
                                result_content += "\n[ENV FIX APPLIED] Environment issue was diagnosed and fixed automatically. You may retry the previous step."
                            else:
                                result_content += "\n[ENV FIX FAILED] Could not fix the environment issue automatically."

                tool_calls_log.append(
                    {
                        "tool": tool_msg.name,
                        "input": tool_msg.input,
                        "success": exec_result.success,
                        "result": result_content,
                    }
                )

                query_engine.add_tool_result(
                    tool_msg.tool_use_id, result_content, is_error=not exec_result.success
                )

            current_prompt = "Please continue based on the tool results above."
    except Exception as e:
        import traceback as _tb

        success = False
        response_text = f"Error: {e}"
        _error_type = type(e).__name__
        _traceback = _tb.format_exc()

    # Convert Pydantic messages to plain dicts for JSON serialization
    serializable_messages = []
    for msg in query_engine.messages:
        if hasattr(msg, "model_dump"):
            # Use mode='json' to convert UUID/datetime to strings
            serializable_messages.append(msg.model_dump(mode="json"))
        elif hasattr(msg, "dict"):
            d = msg.dict()
            # Convert UUID and datetime to strings
            for k, v in d.items():
                if hasattr(v, "__str__") and not isinstance(v, (str, int, float, bool, list, dict)):
                    d[k] = str(v)
            serializable_messages.append(d)
        elif isinstance(msg, dict):
            serializable_messages.append(msg)
        else:
            serializable_messages.append(
                {
                    "type": str(getattr(msg, "type", "unknown")),
                    "content": str(getattr(msg, "content", "")),
                }
            )

    output: dict[str, Any] = {
        "response": response_text,
        "tool_calls": tool_calls_log,
        "success": success,
        "messages": serializable_messages,  # Include full message history for session persistence
        "env_diagnosis_count": env_diagnosis_count,
    }
    if not success:
        output["error_type"] = locals().get("_error_type", "Unknown")
        output["traceback"] = locals().get("_traceback", "")

    if json_mode:
        print(json_mod.dumps(output, indent=2, default=str))
    else:
        print(response_text)

    return output


async def run_headless_with_planning(
    prompt: str,
    auto_allow: bool = False,
    json_mode: bool = False,
    max_iterations: int = 100,
    cwd: str | None = None,
    max_plan_attempts: int = 3,
    progress_callback: Callable[[str], None] | None = None,
    repo: str | None = None,
) -> dict[str, Any]:
    """Run headless mode with automatic task planning, execution, and verification.

    Args:
        max_iterations: Maximum tool-call rounds PER PLAN ITEM during execution.
            The total execution budget is multiplied by the number of planned items.

    Workflow:
        1. Planning: Generate a structured plan (JSON) from the prompt
        2. Execution: Run the main task with the plan injected
        3. Verification: Check if all planned changes are complete
        4. Loop: If incomplete, retry execution with missing items highlighted
    """

    def _extract_json(text: str) -> dict | None:
        text = text.strip()
        # 1. Try the whole text as JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 2. Try extracting from markdown code block
        code_block_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1).strip())
            except json.JSONDecodeError:
                pass
        # 3. Fall back to first { ... } pair
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None

    def _get_git_diff(work_dir: str) -> str:
        try:
            result = subprocess.run(
                ["git", "diff"],
                cwd=work_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            if result.returncode == 0:
                return result.stdout
        except Exception:
            pass
        # Auto-init git repo if not in one so git diff can track changes
        try:
            check = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if check.returncode != 0:
                subprocess.run(
                    ["git", "init"], cwd=work_dir, capture_output=True, text=True, timeout=10
                )
                subprocess.run(
                    ["git", "add", "-A"], cwd=work_dir, capture_output=True, text=True, timeout=10
                )
                subprocess.run(
                    ["git", "commit", "-m", "initial", "--allow-empty"],
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                result = subprocess.run(
                    ["git", "diff"],
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return result.stdout if result.returncode == 0 else ""
        except Exception:
            pass
        return ""

    effective_cwd = cwd if cwd else str(os.getcwd())

    def _log(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    # Instance-level env diagnosis counter (shared across all plan attempts)
    env_diagnosis_count = 0

    # ========================================================================
    # PHASE 1: EXPLORE (read-only)
    # ========================================================================
    _log("[AGENT] Phase 1/4: Exploring codebase (read-only)")
    explore_prompt = f"""\
You are an expert codebase explorer. Your job is to locate the bug and understand the relevant code.

=== CRITICAL: READ-ONLY MODE — NO FILE MODIFICATIONS ===
You CANNOT create, modify, or delete any files.

Task:
{prompt}

Instructions:
1. Use Glob/Grep to find relevant files quickly.
2. Read the key source files to understand the bug.
3. Identify: the exact file(s), function(s), and line(s) where the bug occurs.
4. Find all call sites that use the affected code.
5. Locate relevant test files.
6. Report your findings concisely but thoroughly.

Be efficient — use parallel tool calls where possible.
"""
    explore_result = await run_headless(
        explore_prompt,
        auto_allow=auto_allow,
        json_mode=False,
        max_iterations=12,
        cwd=effective_cwd,
        progress_callback=progress_callback,
        read_only=True,
        env_diagnosis_count=env_diagnosis_count,
    )
    env_diagnosis_count = explore_result.get("env_diagnosis_count", env_diagnosis_count)
    explore_summary = explore_result.get("response", "").strip()
    _log(f"[AGENT] Exploration complete ({len(explore_summary)} chars)")

    # ========================================================================
    # PHASE 2: PLAN (read-only)
    # ========================================================================
    _log("[AGENT] Phase 2/4: Designing implementation plan (read-only)")

    # Try to load cached plan from previous round
    cached_plan = _load_plan_from_cache(effective_cwd)
    if cached_plan:
        _log("[PLAN] Using cached plan from previous round")
        plan = cached_plan
    else:
        plan_prompt = f"""\
You are a software architect. Create a structured implementation plan BEFORE writing any code.

=== CRITICAL: READ-ONLY MODE — NO FILE MODIFICATIONS ===
You CANNOT create, modify, or delete any files.

Task:
{prompt}

Exploration Results:
{explore_summary}

Instructions:
1. Review the exploration results above.
2. Output your final answer as a JSON object with this exact structure:

{{
  "analysis": {{
    "root_cause": "One-sentence description of the true root cause",
    "affected_call_sites": ["file.py:line_or_function"],
    "relevant_tests": ["path/to/test_file.py"]
  }},
  "files_to_modify": [
    {{"file": "relative/path/to/file.py", "change": "Brief description of the exact change"}}
  ],
  "risks": ["Potential risk or side effect"],
  "reasoning": "One-paragraph summary of the strategy"
}}

Requirements:
- ONLY include files that MUST be changed.
- EVERY file MUST exist in the repository.
- affected_call_sites MUST list every place that calls or uses the changed code.
- Output ONLY the JSON object, with no markdown or extra text.
"""
        plan_text = await _generate_structured_output(
            system_prompt="You are a software architect. Output ONLY a JSON object. No markdown, no explanations outside the JSON.",
            user_prompt=plan_prompt,
            progress_callback=progress_callback,
        )
        plan = _extract_json(plan_text)

    if plan is None:
        _log(f"[PLAN] Could not parse plan. Raw text ({len(plan_text)} chars):")
        _log(plan_text[:1000])
        _log("[PLAN] Falling back to direct execution")
        fallback_budget = max(45, max_iterations)
        enriched_prompt = f"""\
{prompt}

--- Exploration & Planning Phase Discoveries ---
{explore_summary}

--- Instruction ---
Based on the discoveries above, proceed DIRECTLY to implement the fix. Do NOT repeat the same exploration. Make the code changes immediately.
"""
        fallback_result = await run_headless(
            enriched_prompt,
            auto_allow=auto_allow,
            json_mode=json_mode,
            max_iterations=fallback_budget,
            cwd=effective_cwd,
            progress_callback=progress_callback,
            env_diagnosis_count=env_diagnosis_count,
        )
        fallback_result["env_diagnosis_count"] = fallback_result.get(
            "env_diagnosis_count", env_diagnosis_count
        )
        return fallback_result

    # Validate plan: ensure referenced files exist in the repo
    is_valid, issues = _validate_plan(plan, effective_cwd)
    if not is_valid:
        for issue in issues:
            _log(f"[PLAN VALIDATION] {issue}")
        _log("[PLAN] Plan references non-existent files, falling back to direct execution")
        fallback_budget = max(45, max_iterations)
        enriched_prompt = f"""\
{prompt}

--- Exploration & Planning Phase Discoveries ---
The planning phase identified the following potential files, but some could not be verified in the repository:
{chr(10).join(issues)}

Proceed DIRECTLY to implement the fix. Make the code changes immediately.
"""
        fallback_result = await run_headless(
            enriched_prompt,
            auto_allow=auto_allow,
            json_mode=json_mode,
            max_iterations=fallback_budget,
            cwd=effective_cwd,
            progress_callback=progress_callback,
            env_diagnosis_count=env_diagnosis_count,
        )
        fallback_result["env_diagnosis_count"] = fallback_result.get(
            "env_diagnosis_count", env_diagnosis_count
        )
        return fallback_result

    # Persist valid plan to external cache
    _save_plan_to_cache(plan, effective_cwd)

    plan_items = plan.get("files_to_modify", [])
    _log(f"[PLAN] {len(plan_items)} files identified")
    for item in plan_items:
        _log(f"  - {item.get('file')}: {item.get('change')}")

    # ========================================================================
    # PHASE 3: EXECUTION
    # ========================================================================
    num_plan_items = len(plan_items)
    execution_max_iterations = (
        max(max_iterations, num_plan_items * 20) if num_plan_items > 0 else max_iterations
    )
    _log(f"[AGENT] Phase 3/4: Executing fix (budget: {execution_max_iterations} turns)")

    planned_files = [item.get("file") for item in plan_items if item.get("file")]
    planned_files_str = (
        "\n".join(f"  - {f}" for f in planned_files) if planned_files else "  (none specified)"
    )
    call_sites = plan.get("analysis", {}).get("affected_call_sites", [])
    call_sites_str = (
        "\n".join(f"  - {s}" for s in call_sites) if call_sites else "  (none specified)"
    )
    relevant_tests = plan.get("analysis", {}).get("relevant_tests", [])
    tests_str = (
        "\n".join(f"  - {t}" for t in relevant_tests) if relevant_tests else "  (none specified)"
    )

    execution_prompt_base = f"""\
{prompt}

Exploration Context:
{explore_summary[:2000]}

=== AUTHORIZED PLAN — FOLLOW EXACTLY ===
You MUST only modify files listed below. Do NOT create new files or modify unrelated files.

Files to modify:
{planned_files_str}

Affected call sites to verify:
{call_sites_str}

Relevant tests to run:
{tests_str}

Planned changes detail:
{json.dumps(plan, indent=2)}

CRITICAL WORKFLOW:
1. Read each planned file ONCE, then edit it immediately. NO additional exploration.
2. ONLY use FileEdit on files in the "Files to modify" list above.
3. When using FileEdit, copy the EXACT old_string from the file. Do NOT double-escape backslashes (e.g., use `\\s` not `\\\\s`, use `\\n` not `\\\\n`).
4. After editing a Python file, run `python3 -m py_compile <filepath>`.
5. After all edits, run `git diff` to verify ONLY planned files were changed.
6. Run relevant tests from the list above. If none are listed, run `python3 -m pytest` on the nearest test file.
   - If tests fail due to MISSING C extensions, ImportError, or broken local environment, DO NOT keep retrying. 
   - Just verify your changes with `git diff` and declare completion.
7. If tests fail due to actual logic bugs in YOUR changes, STOP and revise.
8. Only declare completion when the fix is verified.

CONSTRAINT: You have {execution_max_iterations} tool-call rounds. Do NOT waste turns reading files not in the plan.
"""

    current_prompt = execution_prompt_base
    best_result = None

    effective_max_attempts = max_plan_attempts
    attempt = 0
    previous_missing_count: int | None = None

    while attempt < effective_max_attempts:
        attempt += 1
        _log(f"[EXEC] Attempt {attempt}/{effective_max_attempts}")
        exec_result = await run_headless(
            current_prompt,
            auto_allow=auto_allow,
            json_mode=False,
            max_iterations=execution_max_iterations,
            cwd=effective_cwd,
            progress_callback=progress_callback,
            env_diagnosis_count=env_diagnosis_count,
        )
        env_diagnosis_count = exec_result.get("env_diagnosis_count", env_diagnosis_count)
        best_result = exec_result

        # ========================================================================
        # PHASE 4: VERIFICATION (read-only)
        # ========================================================================
        _log("[AGENT] Phase 4/4: Verifying fix (read-only)")
        current_diff = _get_git_diff(effective_cwd)
        planned_files = [item.get("file") for item in plan_items if item.get("file")]

        # Compute diff stats for quality checks
        diff_hunks = len(re.findall(r"^@@ ", current_diff, re.MULTILINE))
        diff_lines = current_diff.count("\n")
        has_double_escape = "\\\\" in current_diff
        # Count docstring/comment/whitespace-only changes
        docstring_changes = len(re.findall(r'^[\+\-].*"""|^[\+\-].*# ', current_diff, re.MULTILINE))
        whitespace_changes = len(re.findall(r"^[\+\-]\s*$|^[\+\-]\s+$", current_diff, re.MULTILINE))

        verification_prompt = f"""\
You are a verification specialist. Focus ONLY on the planned files listed below.

=== CRITICAL: READ-ONLY MODE — NO FILE MODIFICATIONS ===
You CANNOT modify any files in the project directory.

Task:
{prompt}

Planned files to check:
{chr(10).join(planned_files) if planned_files else "(none specified)"}

Planned Changes:
{json.dumps(plan, indent=2)}

Current git diff (ONLY check files in the plan):
```diff
{current_diff}
```

Diff Stats:
- Total lines changed: {diff_lines}
- Hunks: {diff_hunks}
- Docstring/comment only changes: {docstring_changes}
- Whitespace-only changes: {whitespace_changes}
- Double-escaped backslashes detected: {"YES — CRITICAL BUG" if has_double_escape else "No"}

Verification Steps (FOCUS on planned files only):
1. Were ALL planned files modified correctly?
2. Were any planned files NOT modified (missing changes)?
3. Were any NON-planned files modified (unintended changes)?
4. Were the call sites from the plan properly handled?
5. Is the diff suspiciously large with many docstring/whitespace changes? If so, list them as unintended_changes.
6. Are there double-escaped backslashes (\\\\) in the diff? If yes, mark complete=false and report it.
7. Output ONLY a JSON object:

{{
  "complete": true or false,
  "missing_changes": [
    {{"file": "relative/path/to/file.py", "issue": "What is missing or wrong"}}
  ],
  "unintended_changes": ["file.py - description of change that was not planned"],
  "summary": "Brief assessment"
}}

Output ONLY the JSON object.
"""
        verify_text = await _generate_structured_output(
            system_prompt="You are a verification specialist. Output ONLY a JSON object. No markdown, no explanations outside the JSON.",
            user_prompt=verification_prompt,
            progress_callback=progress_callback,
        )
        verification = _extract_json(verify_text)
        if verification is None:
            _log("[VERIFY] Could not parse verification, assuming complete")
            break

        missing = verification.get("missing_changes", [])
        print(
            f"[VERIFY] complete={verification.get('complete')}, summary={verification.get('summary')}"
        )
        for m in missing:
            print(f"  - MISSING: {m.get('file')}: {m.get('issue')}")

        if verification.get("complete", True):
            _log("[VERIFY] Fix verified as complete")
            break
        else:
            if missing:
                current_missing = len(missing)
                if previous_missing_count is not None and current_missing < previous_missing_count:
                    if effective_max_attempts < max(5, max_plan_attempts):
                        effective_max_attempts += 1
                        _log(
                            f"[VERIFY] Progress detected ({previous_missing_count} -> {current_missing} missing). Extending budget to {effective_max_attempts}."
                        )
                previous_missing_count = current_missing

                extra = "\n\n=== CRITICAL: PREVIOUS ATTEMPT FAILED VERIFICATION ===\n"
                extra += "You MUST fix ALL of the following issues in this attempt. Do NOT ignore them.\n\n"
                for m in missing:
                    extra += f"- FIX REQUIRED in {m.get('file')}: {m.get('issue')}\n"
                unintended = verification.get("unintended_changes", [])
                if unintended:
                    extra += "\n- REMOVE these unintended changes:\n"
                    for u in unintended:
                        extra += f"  - {u}\n"
                extra += (
                    "\nBefore declaring completion, ensure ALL verification issues are resolved.\n"
                )
                current_prompt = execution_prompt_base + extra
            else:
                _log("[VERIFY] No specific missing items listed, using best effort")
                break
    else:
        _log(f"[WARN] Max plan attempts ({effective_max_attempts}) reached")

    # Attach plan to result so callers (e.g. harness) can use it for review/test focus
    if best_result is not None and isinstance(best_result, dict):
        best_result["plan"] = plan
        best_result["explore_summary"] = explore_summary

    if json_mode:
        import json as json_mod

        print(json_mod.dumps(best_result, indent=2, default=str))

    return best_result


# ---------------------------------------------------------------------------
# Persistent headless execution: auto-retry when patch is empty or has syntax errors
# ---------------------------------------------------------------------------

_EMPTY_PATCH_PROMPT = """\
Your previous attempt did NOT produce any code changes (git diff is empty).

This means you either:
- Did not make any file edits
- Made edits but then reverted them
- Failed to locate the correct file to change

CRITICAL: You MUST make actual code changes. Do NOT just analyze and describe the fix.

Requirements:
1. Re-read the bug report carefully.
2. Use Grep/FileRead to locate the exact bug location.
3. Apply FileEdit to FIX the code.
4. Run `git diff` to confirm the patch is non-empty.
5. If you are unsure, make the most reasonable fix you can and declare completion.
"""

_SYNTAX_ERROR_PROMPT = """\
Your previous fix was applied but it introduces SYNTAX ERRORS:

{errors}

This means your edit corrupted the source file. You MUST fix the syntax before anything else.

Requirements:
1. Read the EXACT current state of the file(s) you modified.
2. Identify where the syntax error was introduced (mismatched brackets, wrong indentation, duplicate keywords, etc.).
3. Apply a CORRECTED edit that fixes the syntax while preserving the intended logic.
4. Run `python3 -m py_compile <filepath>` to verify the syntax is valid.
5. Run `git diff` to confirm your changes.
"""

_REVIEW_PROMPT = """\
You have produced a patch. Review it for COMPLETENESS before finishing.

Task:
1. Run `git diff` to see exactly what you changed.
2. For every file you modified, check if there are OTHER methods or call sites that should also be updated.
   - If you added a helper method, did you update all places that use the old behavior?
   - If you changed an API, did you update related methods (deconstruct, formfield, check, etc.)?
3. Run `python3 -m py_compile` on all modified Python files.
4. If anything is missing or broken, apply the fixes NOW.

Do NOT declare completion until you are confident the patch is complete and correct.
"""


def _get_git_diff(work_dir: str) -> str:
    try:
        result = subprocess.run(
            ["git", "diff"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout
    except Exception:
        pass
    # Auto-init git repo if not in one so git diff can track changes
    try:
        check = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if check.returncode != 0:
            subprocess.run(
                ["git", "init"], cwd=work_dir, capture_output=True, text=True, timeout=10
            )
            subprocess.run(
                ["git", "add", "-A"], cwd=work_dir, capture_output=True, text=True, timeout=10
            )
            subprocess.run(
                ["git", "commit", "-m", "initial", "--allow-empty"],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            result = subprocess.run(
                ["git", "diff"],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.stdout if result.returncode == 0 else ""
    except Exception:
        pass
    return ""


def _check_patch_syntax(work_dir: str, patch: str) -> tuple[bool, str]:
    """Check modified Python files for syntax errors. Returns (ok, error_message)."""
    if not patch:
        return True, ""
    files = set(re.findall(r"^diff --git a/(.+?) b/", patch, re.MULTILINE))
    errors = []
    for f in files:
        if not f.endswith(".py"):
            continue
        filepath = os.path.join(work_dir, f)
        if not os.path.exists(filepath):
            continue
        try:
            py_compile.compile(filepath, doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"{f}: {e}")
    if errors:
        return False, "\n".join(errors)
    return True, ""


def _is_patch_trivial(work_dir: str, patch: str) -> bool:
    """Heuristic: detect if a patch is just a minor tweak when a structural fix may be needed."""
    if not patch:
        return True
    lines = patch.splitlines()
    code_lines = [
        line
        for line in lines
        if (line.startswith("+") or line.startswith("-")) and not line.startswith(("+++", "---"))
    ]
    if len(code_lines) <= 3:
        return True

    added = [line for line in code_lines if line.startswith("+")]
    has_new_import = any("import " in line or "from " in line for line in added)
    has_new_symbol = any("def " in line or "class " in line for line in added)
    has_signature_change = any("def " in line for line in code_lines)
    has_new_file = bool(len(set(re.findall(r"^diff --git a/(.+?) b/", patch, re.MULTILINE))) > 1)

    if has_new_import or has_new_symbol or has_signature_change or has_new_file:
        return False
    return len(code_lines) <= 12


def _extract_discoveries_from_messages(messages: list[dict[str, Any]]) -> str:
    """Extract key file discoveries from tool call results in messages.

    Preserves critical exploration results across rounds so the model doesn't
    lose context about which files were read and what they contained.
    """
    if not messages:
        return ""
    discoveries: list[str] = []
    for msg in messages:
        role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
        if role == "tool":
            name = msg.get("name", "") if isinstance(msg, dict) else getattr(msg, "name", "")
            content = (
                msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            )
            if name in ("FileRead", "Grep", "CodeSearch", "Glob"):
                content_str = str(content)[:600].replace("\n", " ")
                discoveries.append(f"- [{name}] {content_str}")
    if not discoveries:
        return ""
    return "\n=== KEY DISCOVERIES FROM PREVIOUS ROUND ===\n" + "\n".join(discoveries[:8])


def _get_plan_cache_path(cwd: str) -> str:
    """Return external cache path for persisting plans outside the git workspace."""
    cache_dir = Path.home() / ".cache" / "pilotcode" / "plans"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.md5(cwd.encode()).hexdigest()[:16]
    return str(cache_dir / f"{cache_key}.json")


def _save_plan_to_cache(plan: dict, cwd: str) -> None:
    """Persist plan to external cache so it survives across rounds."""
    try:
        Path(_get_plan_cache_path(cwd)).write_text(json.dumps(plan, indent=2))
    except Exception:
        pass


def _load_plan_from_cache(cwd: str) -> dict | None:
    """Load previously cached plan if available."""
    try:
        path = _get_plan_cache_path(cwd)
        if os.path.exists(path):
            return json.loads(Path(path).read_text())
    except Exception:
        pass
    return None


def _validate_plan(plan: dict, cwd: str) -> tuple[bool, list[str]]:
    """Validate that all files referenced in the plan exist in the git repo.

    Returns (is_valid, list_of_issues).
    """
    issues: list[str] = []
    files_to_check: set[str] = set()

    for item in plan.get("files_to_modify", []):
        fpath = item.get("file", "")
        if fpath:
            files_to_check.add(fpath)

    for site in plan.get("analysis", {}).get("affected_call_sites", []):
        fpath = site.split(":")[0] if ":" in site else site
        if fpath and not ("/tests/" in fpath or "/test_" in fpath):
            files_to_check.add(fpath)

    if not files_to_check:
        return True, []

    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        tracked_files = set(result.stdout.splitlines()) if result.returncode == 0 else set()
    except Exception:
        tracked_files = set()

    for fpath in files_to_check:
        full_path = os.path.join(cwd, fpath)
        if fpath not in tracked_files and not os.path.exists(full_path):
            issues.append(f"File not found in repo: {fpath}")

    return len(issues) == 0, issues


def _compress_messages_for_retry(
    messages: list[dict[str, Any]],
    round_idx: int,
    patch_len: int,
    syntax_ok: bool,
    syntax_errors: str,
    improved: bool,
) -> list[dict[str, Any]]:
    """Compress a long conversation into a minimal history with a failure summary.

    Keeps only the system message and a synthesized user message that tells the LLM
    what was attempted in the previous round and why it failed, so the next round
    starts with clean context but retains the lesson.
    """
    if not messages:
        return []

    # Keep the first system message if present
    compressed = []
    first = messages[0]
    if isinstance(first, dict) and first.get("type") == "system":
        compressed.append(first)
    elif hasattr(first, "type") and getattr(first, "type", None) == "system":
        compressed.append(first)

    # Build a concise failure summary
    if patch_len == 0:
        outcome = "EMPTY PATCH"
    elif not syntax_ok:
        outcome = "SYNTAX ERROR"
    else:
        outcome = "INCOMPLETE FIX"

    summary_lines = [
        f"[Round {round_idx} Summary]",
        f"Attempt outcome: {outcome}",
    ]
    if patch_len > 0:
        summary_lines.append(f"Patch size: {patch_len} chars")
    if not syntax_ok:
        summary_lines.append(f"Syntax issues: {syntax_errors[:500]}")
    if improved:
        summary_lines.append("Progress was made compared to the previous round.")
    else:
        summary_lines.append("No clear progress compared to the previous round.")

    # Extract and preserve critical discoveries from tool calls
    discoveries = _extract_discoveries_from_messages(messages)
    if discoveries:
        summary_lines.append(discoveries)

    summary_lines.append(
        "You must now produce a CORRECT and COMPLETE fix. Avoid repeating the same mistakes."
    )

    summary_text = "\n".join(summary_lines)

    if compressed:
        msg_type = "user"
        if isinstance(compressed[0], dict):
            compressed.append({"type": msg_type, "content": summary_text})
        else:
            from ..types.message import UserMessage

            compressed.append(UserMessage(content=summary_text))
    else:
        from ..types.message import UserMessage

        compressed.append(UserMessage(content=summary_text))

    return compressed


async def run_headless_with_feedback(
    prompt: str,
    auto_allow: bool = False,
    json_mode: bool = False,
    max_iterations: int = 100,
    max_rounds: int = 3,
    cwd: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
    use_planning: bool = False,
) -> dict[str, Any]:
    """Run headless mode with automatic continuation on empty patch or syntax errors.

    After each round, we check:
      1. Is the git diff non-empty?
      2. Do the modified Python files compile?
      3. Is the patch making progress compared to the previous round?
    If checks fail, we feed the issue back to the LLM and run another round.
    If patch is improving, we extend the budget automatically.
    """
    effective_cwd = cwd if cwd else str(os.getcwd())
    best_result: dict[str, Any] = {
        "response": "",
        "tool_calls": [],
        "success": True,
        "messages": [],
    }
    current_prompt = prompt
    messages: list[dict[str, Any]] | None = None

    effective_max_rounds = max_rounds
    round_idx = 0
    previous_patch_len = 0
    previous_syntax_ok = True

    while round_idx < effective_max_rounds:
        round_idx += 1
        if progress_callback:
            progress_callback(f"[PERSIST] Round {round_idx}/{effective_max_rounds} starting")
        else:
            print(f"[PERSIST] Round {round_idx}/{effective_max_rounds} starting", flush=True)

        if use_planning:
            result = await run_headless_with_planning(
                current_prompt,
                auto_allow=auto_allow,
                json_mode=False,
                max_iterations=max_iterations,
                cwd=effective_cwd,
                progress_callback=progress_callback,
            )
        else:
            result = await run_headless(
                current_prompt,
                auto_allow=auto_allow,
                json_mode=False,
                max_iterations=max_iterations,
                initial_messages=messages,
                cwd=effective_cwd,
                progress_callback=progress_callback,
            )

        best_result = result
        messages = result.get("messages")

        patch = _get_git_diff(effective_cwd)
        patch_len = len(patch)
        syntax_ok, syntax_errors = _check_patch_syntax(effective_cwd, patch)

        # Detect improvement vs previous round
        improved = False
        if patch_len > previous_patch_len * 1.2:
            improved = True
        if not previous_syntax_ok and syntax_ok:
            improved = True

        previous_patch_len = patch_len
        previous_syntax_ok = syntax_ok

        # Check 1: empty patch
        if not patch:
            if round_idx >= effective_max_rounds:
                break
            if improved and effective_max_rounds < max(5, max_rounds):
                effective_max_rounds += 1
                if progress_callback:
                    progress_callback(
                        "[PERSIST] Response improved but still empty — extending budget"
                    )
                else:
                    print(
                        "[PERSIST] Response improved but still empty — extending budget", flush=True
                    )
            if progress_callback:
                progress_callback("[PERSIST] Empty patch detected — continuing")
            else:
                print("[PERSIST] Empty patch detected — continuing", flush=True)
            messages = _compress_messages_for_retry(
                messages or [], round_idx, patch_len, syntax_ok, syntax_errors, improved
            )
            current_prompt = _EMPTY_PATCH_PROMPT
            continue

        # Check 2: syntax errors
        if not syntax_ok:
            if round_idx >= effective_max_rounds:
                break
            if improved and effective_max_rounds < max(5, max_rounds):
                effective_max_rounds += 1
                if progress_callback:
                    progress_callback("[PERSIST] Progress on syntax — extending budget")
                else:
                    print("[PERSIST] Progress on syntax — extending budget", flush=True)
            if progress_callback:
                progress_callback("[PERSIST] Syntax errors detected — continuing")
            else:
                print("[PERSIST] Syntax errors detected — continuing", flush=True)
            messages = _compress_messages_for_retry(
                messages or [], round_idx, patch_len, syntax_ok, syntax_errors, improved
            )
            current_prompt = _SYNTAX_ERROR_PROMPT.format(errors=syntax_errors)
            continue

        # Check 3: review round (give LLM a chance to self-correct incomplete patches)
        if round_idx < effective_max_rounds:
            if progress_callback:
                progress_callback("[PERSIST] Patch syntax OK — triggering review round")
            else:
                print("[PERSIST] Patch syntax OK — triggering review round", flush=True)
            messages = _compress_messages_for_retry(
                messages or [], round_idx, patch_len, syntax_ok, syntax_errors, improved
            )
            current_prompt = _REVIEW_PROMPT
            continue

        # All checks passed
        if progress_callback:
            progress_callback(f"[PERSIST] Patch valid ({len(patch)} chars) — stopping")
        else:
            print(f"[PERSIST] Patch valid ({len(patch)} chars) — stopping", flush=True)
        break

    # Planning fallback: trivial patch for a task that likely needs structural change
    final_patch = _get_git_diff(effective_cwd)
    if final_patch and _is_patch_trivial(effective_cwd, final_patch) and not use_planning:
        if progress_callback:
            progress_callback(
                "[PERSIST] Patch looks trivial for this task — falling back to planning mode"
            )
        else:
            print(
                "[PERSIST] Patch looks trivial for this task — falling back to planning mode",
                flush=True,
            )
        plan_result = await run_headless_with_planning(
            prompt,
            auto_allow=auto_allow,
            json_mode=False,
            max_iterations=max_iterations,
            cwd=effective_cwd,
            progress_callback=progress_callback,
        )
        best_result = plan_result

    if json_mode:
        import json as json_mod

        print(json_mod.dumps(best_result, indent=2, default=str))

    return best_result
