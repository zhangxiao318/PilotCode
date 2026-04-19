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

# Context variable to prevent nested environment-diagnosis dead loops
_env_diagnosis_ctx: contextvars.ContextVar[bool] = contextvars.ContextVar("env_diagnosis_active", default=False)

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


class REPL:
    """Programming Assistant REPL with full tool support."""

    # Default max iterations for tool calls (configurable via env var)
    DEFAULT_MAX_ITERATIONS = 25

    WRITE_TOOLS = {
        "FileEdit", "FileWrite", "ApplyPatch", "NotebookEdit",
        "CronCreate", "CronDelete", "CronUpdate",
    }

    def __init__(self, auto_allow: bool = False, max_iterations: int | None = None, read_only: bool = False):
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
        self.query_engine = QueryEngine(
            QueryEngineConfig(
                cwd=self.store.get_state().cwd,
                tools=tools,
                get_app_state=self.store.get_state,
                set_app_state=lambda f: self.store.set_state(f),
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

    async def process_response(self, prompt: str) -> None:
        """Process a prompt through the LLM with tool support."""
        full_content = ""
        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1
            pending_tools = []

            # Show status with progress indicator
            status_text = (
                f"[cyan]Thinking...[/cyan] [dim](turn {iteration}/{self.max_iterations})[/dim]"
            )
            with Status(status_text, console=self.console, spinner="dots"):
                try:
                    async for result in self.query_engine.submit_message(prompt):
                        msg = result.message

                        if isinstance(msg, AssistantMessage):
                            if isinstance(msg.content, str):
                                if result.is_complete:
                                    # Final message: use it if non-empty, otherwise keep accumulated
                                    # If final message is shorter than accumulated, use accumulated
                                    # (handles case where accumulated has more detail)
                                    if msg.content and len(msg.content) >= len(full_content):
                                        full_content = msg.content
                                    # else: keep accumulated full_content
                                else:
                                    # Streaming: accumulate content
                                    if msg.content:
                                        full_content += msg.content

                        elif isinstance(msg, ToolUseMessage):
                            pending_tools.append(msg)

                except Exception as e:
                    self.console.print(f"[red]Error: {e}[/red]")
                    return

            # Display the assistant's response
            if full_content:
                self.console.print()
                self.console.print(Markdown(full_content))
                full_content = ""  # Reset for next iteration
                # Ensure output is flushed and visible before showing prompt
                self.console.print()  # Extra blank line for readability
                sys.stdout.flush()  # Force flush on Windows
            # else: no content to display

            # Execute pending tools
            if not pending_tools:
                # No tools to execute, we're done
                break

            for tool_idx, tool_msg in enumerate(pending_tools, 1):
                tool_progress = f"[turn {iteration}/{self.max_iterations}]"
                if len(pending_tools) > 1:
                    tool_progress += f" [tool {tool_idx}/{len(pending_tools)}]"
                self.console.print(f"\n[dim][T] {tool_progress} {tool_msg.name}[/dim]")

                # Execute with permission
                context = ToolUseContext(
                    get_app_state=self.store.get_state,
                    set_app_state=lambda f: self.store.set_state(f),
                )

                exec_result = await self.tool_executor.execute_tool_by_name(
                    tool_msg.name, tool_msg.input, context
                )

                # Add result to conversation
                result_content = ""
                if exec_result.success and exec_result.result:
                    result_content = (
                        str(exec_result.result.data) if exec_result.result.data else "Success"
                    )
                    self.console.print(f"[dim]✓ {tool_msg.name} completed[/dim]")
                else:
                    result_content = exec_result.message
                    self.console.print(f"[red]✗ {exec_result.message}[/red]")

                    # --- Environment diagnosis (interactive REPL mode) ---
                    if not getattr(self, '_env_diagnosis_fired', False):
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

                # Add to query engine history
                self.query_engine.add_tool_result(
                    tool_msg.tool_use_id, result_content, is_error=not exec_result.success
                )
                # Ensure tool output is visible
                sys.stdout.flush()

            # Loop detection
            loop_reason = self.loop_guard.record(pending_tools)
            if loop_reason:
                warning = (
                    f"[SYSTEM WARNING] DETECTED LOOP: {loop_reason}. "
                    f"You have been repeating the same tool calls. STOP exploring and "
                    f"produce your final answer or code changes immediately. "
                    f"Do NOT call the same tools again."
                )
                self.console.print(f"[yellow]{warning}[/yellow]")
                # Inject warning so the model sees it on the next turn
                self.query_engine.messages.append(
                    AssistantMessage(content=warning)
                )

            # Continue the conversation with tool results
            remaining = max_iterations - iteration
            if remaining <= 5:
                prompt = f"URGENT: You have only {remaining} tool-call rounds left. If you know the fix, APPLY IT NOW. If not, make your best edit and declare completion."
            elif remaining <= 15:
                prompt = f"REMINDER: {remaining} tool-call rounds remain. Focus on making the actual code changes, not further reading."
            else:
                prompt = "Please continue based on the tool results above."

        if iteration >= self.max_iterations:
            self.console.print(
                f"[yellow]⚠️ Reached maximum tool execution rounds ({self.max_iterations})[/yellow]"
            )
            self.console.print(
                "[dim]💡 Tip: Set PILOTCODE_MAX_ITERATIONS=50 to increase limit[/dim]"
            )

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
        max_iterations: Maximum tool execution rounds per query (default: 25)
    """
    repl = REPL(auto_allow=auto_allow, max_iterations=max_iterations)
    try:
        asyncio.run(repl.run())
    except KeyboardInterrupt:
        print("\nGoodbye! 👋")


def assess_project_complexity(cwd: str) -> dict[str, Any]:
    """Quickly assess codebase size and language complexity via shell commands.

    Returns dict with file_count, language_scores, loc_estimate, complexity_score.
    """
    result: dict[str, Any] = {
        "file_count": 0,
        "language_scores": {},
        "loc_estimate": 0,
        "complexity_score": 0.0,
    }

    try:
        # Count total source files (exclude common non-source dirs)
        cmd = (
            f"find '{cwd}' -maxdepth 3 -type f "
            r"\( -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.jsx' -o -name '*.tsx' "
            r"-o -name '*.java' -o -name '*.cpp' -o -name '*.cc' -o -name '*.c' -o -name '*.h' "
            r"-o -name '*.go' -o -name '*.rs' -o -name '*.rb' \) "
            r"! -path '*/node_modules/*' ! -path '*/.git/*' ! -path '*/__pycache__/*' "
            r"! -path '*/venv/*' ! -path '*/.venv/*' ! -path '*/build/*' "
            r"| wc -l"
        )
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        file_count = int(proc.stdout.strip()) if proc.returncode == 0 else 0
        result["file_count"] = file_count

        # Language breakdown with weights (higher = more complex)
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
        lang_scores: dict[str, int] = {}
        for ext in lang_weights:
            cmd = f"find '{cwd}' -maxdepth 3 -type f -name '*{ext}' ! -path '*/node_modules/*' ! -path '*/.git/*' | wc -l"
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            cnt = int(proc.stdout.strip()) if proc.returncode == 0 else 0
            if cnt > 0:
                lang_scores[ext.lstrip('.')] = cnt
        result["language_scores"] = lang_scores

        # LOC estimate via wc -l on top-level source files (fast approximation)
        cmd = (
            f"find '{cwd}' -maxdepth 3 -type f "
            r"\( -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.java' "
            r"-o -name '*.cpp' -o -name '*.cc' -o -name '*.c' -o -name '*.go' -o -name '*.rs' \) "
            r"! -path '*/node_modules/*' ! -path '*/.git/*' ! -path '*/__pycache__/*' "
            r"-exec cat {{}} + 2>/dev/null | wc -l"
        )
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        loc = int(proc.stdout.strip()) if proc.returncode == 0 else 0
        result["loc_estimate"] = loc

        # Compute a composite complexity score
        complexity = 0.0
        if file_count > 500:
            complexity += 2.0
        elif file_count > 200:
            complexity += 1.5
        elif file_count > 50:
            complexity += 0.8
        else:
            complexity += 0.3

        if loc > 100000:
            complexity += 2.0
        elif loc > 30000:
            complexity += 1.0
        elif loc > 10000:
            complexity += 0.5

        for ext, cnt in lang_scores.items():
            weight = lang_weights.get('.' + ext, 1.0)
            if cnt > 50:
                complexity += 0.5 * weight
            elif cnt > 10:
                complexity += 0.2 * weight

        result["complexity_score"] = round(complexity, 2)
    except Exception:
        # If assessment fails, return conservative defaults
        pass

    return result


def _compute_task_complexity(prompt: str, project_stats: dict[str, Any]) -> float:
    """Compute a composite complexity score (0-10 scale)."""
    score = project_stats.get("complexity_score", 0.0)

    prompt_lower = prompt.lower()

    # Task-type keywords
    hard_keywords = [
        "refactor", "architecture", "restructure", "redesign",
        "implement", "add support", "introduce",
        "debug", "fix bug", "bug report", "regression",
        "cross-file", "multiple files", "across the codebase",
    ]
    medium_keywords = [
        "update", "modify", "change behavior", "enhance",
        "improve", "optimize", "performance",
    ]
    easy_keywords = [
        "rename", "move", "extract", "simple", "single file",
        "update docstring", "add comment", "fix typo",
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
    """Use project scale + LLM to classify whether the task needs planning.

    Returns:
        "PLAN" if the task likely involves multiple files or complex logic.
        "DIRECT" for simple, localized tasks.
    """
    effective_cwd = cwd if cwd else str(os.getcwd())
    project_stats = assess_project_complexity(effective_cwd)
    composite_score = _compute_task_complexity(prompt, project_stats)

    # Fast path: very small projects with low scores -> DIRECT
    if composite_score < 1.5 and project_stats.get("file_count", 0) < 30:
        return "DIRECT"

    # Fast path: large projects or high scores -> PLAN without LLM overhead
    if composite_score >= 3.0 or project_stats.get("file_count", 0) > 150:
        return "PLAN"

    # Use LLM as a tie-breaker for mid-range scores
    classifier_prompt = (
        "You are a task router. Based on the user request, decide if this task "
        "requires multi-step planning before execution.\n\n"
        f"Project stats: {json.dumps(project_stats)}\n\n"
        "User request:\n"
        f"{prompt}\n\n"
        "Answer with ONLY one word: PLAN or DIRECT.\n"
        "- PLAN: The task likely involves multiple files, complex logic, debugging "
        "across the codebase, or bug fixing.\n"
        "- DIRECT: The task is simple, localized, or can be done in a single edit."
    )

    client = get_model_client()
    messages = [
        Message(role="system", content="You classify coding tasks. Reply with exactly one word: PLAN or DIRECT."),
        Message(role="user", content=classifier_prompt),
    ]

    try:
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

        content = chunks[0].get("choices", [{}])[0].get("delta", {}).get("content", "")
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
    """

    def __init__(self, window_size: int = 6):
        self.window_size = window_size
        self.round_fingerprints: list[tuple[str, ...]] = []
        self.loop_count: int = 0

    @staticmethod
    def _fingerprint(tool_msg: ToolUseMessage) -> str:
        import hashlib
        name = tool_msg.name
        input_str = json.dumps(tool_msg.input, sort_keys=True, default=str)
        return f"{name}:{hashlib.md5(input_str.encode()).hexdigest()[:8]}"

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

    def _detect(self) -> str | None:
        recent = self.round_fingerprints
        if len(recent) < 4:
            return None

        flat = [fp for r in recent for fp in r]
        from collections import Counter
        counts = Counter(flat)

        # Rule 1: Same single tool called repeatedly with identical input
        for fp, cnt in counts.items():
            if cnt >= 4:
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
            "FileRead", "Glob", "Grep", "CodeSearch", "CodeIndex",
            "GitDiff", "GitStatus", "FileTree",
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
    max_iterations: int = 25,
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
    from ..state.app_state import AppState

    # Ensure cwd is valid (not None, not empty)
    effective_cwd = cwd if cwd else str(os.getcwd())
    initial_state = AppState(cwd=effective_cwd)
    store = Store(initial_state)
    set_global_store(store)

    working_dir = store.get_state().cwd

    write_tools = {
        "FileEdit", "FileWrite", "ApplyPatch", "NotebookEdit",
        "CronCreate", "CronDelete", "CronUpdate",
    }
    tools = get_all_tools()
    if read_only:
        tools = [t for t in tools if t.name not in write_tools]
    query_engine = QueryEngine(
        QueryEngineConfig(
            cwd=working_dir,
            tools=tools,
            get_app_state=store.get_state,
            set_app_state=lambda f: store.set_state(f),
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

            async for result in query_engine.submit_message(current_prompt, options={"temperature": 0.0}):
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
                    query_engine.add_tool_result(
                        tool_msg.tool_use_id, forced_result, is_error=True
                    )
                current_prompt = (
                    "CRITICAL: You are in a tool-call loop. All pending tool calls were blocked. "
                    "Summarize what you have done so far and declare completion if the fix is applied. "
                    "Do NOT call any more tools."
                )
                continue

            write_tool_names = {
                "FileEdit", "FileWrite", "ApplyPatch", "NotebookEdit",
                "CronCreate", "CronDelete", "CronUpdate",
            }
            for tool_idx, tool_msg in enumerate(pending_tools, 1):
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
                        get_app_state=store.get_state, set_app_state=lambda f: store.set_state(f)
                    )
                    exec_result = await tool_executor.execute_tool_by_name(
                        tool_msg.name, tool_msg.input, context
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
                    if not already_diagnosing and not disable_env_diagnosis and env_diagnosis_count < 1:
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
        success = False
        response_text = f"Error: {e}"

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

    output = {
        "response": response_text,
        "tool_calls": tool_calls_log,
        "success": success,
        "messages": serializable_messages,  # Include full message history for session persistence
        "env_diagnosis_count": env_diagnosis_count,
    }

    if json_mode:
        print(json_mod.dumps(output, indent=2, default=str))
    else:
        print(response_text)

    return output


async def run_headless_with_planning(
    prompt: str,
    auto_allow: bool = False,
    json_mode: bool = False,
    max_iterations: int = 25,
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
                timeout=30,
            )
            return result.stdout if result.returncode == 0 else ""
        except Exception:
            return ""

    effective_cwd = cwd if cwd else str(os.getcwd())

    def _log(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

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
        fallback_result["env_diagnosis_count"] = fallback_result.get("env_diagnosis_count", env_diagnosis_count)
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
        fallback_result["env_diagnosis_count"] = fallback_result.get("env_diagnosis_count", env_diagnosis_count)
        return fallback_result

    # Persist valid plan to external cache
    _save_plan_to_cache(plan, effective_cwd)

    plan_items = plan.get('files_to_modify', [])
    _log(f"[PLAN] {len(plan_items)} files identified")
    for item in plan_items:
        _log(f"  - {item.get('file')}: {item.get('change')}")

    # ========================================================================
    # PHASE 3: EXECUTION
    # ========================================================================
    num_plan_items = len(plan_items)
    execution_max_iterations = max(max_iterations, num_plan_items * 20) if num_plan_items > 0 else max_iterations
    _log(f"[AGENT] Phase 3/4: Executing fix (budget: {execution_max_iterations} turns)")

    planned_files = [item.get("file") for item in plan_items if item.get("file")]
    planned_files_str = "\n".join(f"  - {f}" for f in planned_files) if planned_files else "  (none specified)"
    call_sites = plan.get("analysis", {}).get("affected_call_sites", [])
    call_sites_str = "\n".join(f"  - {s}" for s in call_sites) if call_sites else "  (none specified)"
    relevant_tests = plan.get("analysis", {}).get("relevant_tests", [])
    tests_str = "\n".join(f"  - {t}" for t in relevant_tests) if relevant_tests else "  (none specified)"

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
3. When using FileEdit, copy the EXACT old_string from the file. Do NOT double-escape backslashes (e.g., use `\s` not `\\s`, use `\n` not `\\n`).
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
        diff_hunks = len(re.findall(r'^@@ ', current_diff, re.MULTILINE))
        diff_lines = current_diff.count('\n')
        has_double_escape = '\\\\' in current_diff
        # Count docstring/comment/whitespace-only changes
        docstring_changes = len(re.findall(r'^[\+\-].*"""|^[\+\-].*# ', current_diff, re.MULTILINE))
        whitespace_changes = len(re.findall(r'^[\+\-]\s*$|^[\+\-]\s+$', current_diff, re.MULTILINE))

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
- Double-escaped backslashes detected: {'YES — CRITICAL BUG' if has_double_escape else 'No'}

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
        print(f"[VERIFY] complete={verification.get('complete')}, summary={verification.get('summary')}")
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
                        _log(f"[VERIFY] Progress detected ({previous_missing_count} -> {current_missing} missing). Extending budget to {effective_max_attempts}.")
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
                extra += "\nBefore declaring completion, ensure ALL verification issues are resolved.\n"
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
            timeout=30,
        )
        return result.stdout if result.returncode == 0 else ""
    except Exception:
        return ""


def _check_patch_syntax(work_dir: str, patch: str) -> tuple[bool, str]:
    """Check modified Python files for syntax errors. Returns (ok, error_message)."""
    if not patch:
        return True, ""
    files = set(re.findall(r'^diff --git a/(.+?) b/', patch, re.MULTILINE))
    errors = []
    for f in files:
        if not f.endswith('.py'):
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
    code_lines = [l for l in lines if (l.startswith('+') or l.startswith('-')) and not l.startswith(('+++', '---'))]
    if len(code_lines) <= 3:
        return True

    added = [l for l in code_lines if l.startswith('+')]
    has_new_import = any('import ' in l or 'from ' in l for l in added)
    has_new_symbol = any('def ' in l or 'class ' in l for l in added)
    has_signature_change = any('def ' in l for l in code_lines)
    has_new_file = bool(len(set(re.findall(r'^diff --git a/(.+?) b/', patch, re.MULTILINE))) > 1)

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
            content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
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
    max_iterations: int = 25,
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
    best_result: dict[str, Any] = {"response": "", "tool_calls": [], "success": True, "messages": []}
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
                    progress_callback("[PERSIST] Response improved but still empty — extending budget")
                else:
                    print("[PERSIST] Response improved but still empty — extending budget", flush=True)
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
            progress_callback("[PERSIST] Patch looks trivial for this task — falling back to planning mode")
        else:
            print("[PERSIST] Patch looks trivial for this task — falling back to planning mode", flush=True)
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
