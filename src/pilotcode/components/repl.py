"""REPL for PilotCode - Programming Assistant with Tool Support."""

import asyncio
import json
import os
import re
import subprocess
import sys
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


class REPL:
    """Programming Assistant REPL with full tool support."""

    # Default max iterations for tool calls (configurable via env var)
    DEFAULT_MAX_ITERATIONS = 25

    def __init__(self, auto_allow: bool = False, max_iterations: int | None = None):
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

        # Enable all tools
        tools = get_all_tools()
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

                # Add to query engine history
                self.query_engine.add_tool_result(
                    tool_msg.tool_use_id, result_content, is_error=not exec_result.success
                )
                # Ensure tool output is visible
                sys.stdout.flush()

            # Continue the conversation with tool results
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
    asyncio.run(repl.run())


async def classify_task_complexity(prompt: str) -> str:
    """Use a lightweight LLM call to classify whether the task needs planning.

    Returns:
        "PLAN" if the task likely involves multiple files or complex logic.
        "DIRECT" for simple, localized tasks.
    """
    classifier_prompt = (
        "You are a task router. Based on the user request, decide if this task "
        "requires multi-step planning before execution.\n\n"
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
        # Default to PLAN for any uncertainty
        return "PLAN"
    except Exception:
        # If classification fails, default to planning mode to be safe
        return "PLAN"


async def run_headless(
    prompt: str,
    auto_allow: bool = False,
    json_mode: bool = False,
    max_iterations: int = 25,
    initial_messages: list | None = None,
    cwd: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
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

    tools = get_all_tools()
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

    try:
        current_prompt = prompt
        turn = 0
        for _ in range(max_iterations):
            turn += 1
            pending_tools: list[ToolUseMessage] = []

            async for result in query_engine.submit_message(current_prompt):
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
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
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

    # Step 1: Planning
    planning_prompt = f"""\
You are analyzing a task. Create a precise, structured plan for completing it.

Task:
{prompt}

Instructions:
1. Explore the workspace if needed using available tools.
2. Identify EVERY file that needs to be changed.
3. For each file, describe the exact change needed in one sentence.
4. Output your final answer as a JSON object with this exact structure:

{{
  "files_to_modify": [
    {{
      "file": "relative/path/to/file.py",
      "change": "Brief description of the exact change"
    }}
  ],
  "reasoning": "One-paragraph summary of the strategy"
}}

Requirements:
- ONLY include files that MUST be changed.
- Output ONLY the JSON object, with no markdown or extra text.
"""

    plan_result = await run_headless(
        planning_prompt,
        auto_allow=auto_allow,
        json_mode=False,
        max_iterations=20,
        cwd=effective_cwd,
    )
    plan = _extract_json(plan_result.get("response", ""))
    if plan is None:
        _log("[PLAN] Could not parse plan, falling back to direct execution")
        return await run_headless(
            prompt, auto_allow=auto_allow, json_mode=json_mode, max_iterations=max_iterations, cwd=effective_cwd
        )

    plan_items = plan.get('files_to_modify', [])
    _log(f"[PLAN] {len(plan_items)} files identified")
    for item in plan_items:
        _log(f"  - {item.get('file')}: {item.get('change')}")

    # Scale execution budget per plan item
    num_plan_items = len(plan_items)
    execution_max_iterations = max(max_iterations, num_plan_items * max_iterations) if num_plan_items > 0 else max_iterations
    _log(f"[EXEC] Budget: {execution_max_iterations} tool-call rounds ({max_iterations} per plan item × {num_plan_items} items)")

    # Step 2-4: Execution + Verification loop
    execution_prompt_base = f"""\
{prompt}

Planned Changes:
{json.dumps(plan, indent=2)}

CRITICAL WORKFLOW:
1. Edit files ONE AT A TIME according to the plan.
2. After each Python file edit, run `python -m py_compile <filepath>`.
3. After all edits, run `git diff` to verify completeness.
4. Only declare completion when the checklist is fully satisfied.
"""

    current_prompt = execution_prompt_base
    best_result = None

    for attempt in range(1, max_plan_attempts + 1):
        _log(f"[EXEC] Attempt {attempt}/{max_plan_attempts}")
        exec_result = await run_headless(
            current_prompt,
            auto_allow=auto_allow,
            json_mode=False,
            max_iterations=execution_max_iterations,
            cwd=effective_cwd,
        )
        best_result = exec_result

        # Step 3: Verification
        current_diff = _get_git_diff(effective_cwd)
        verification_prompt = f"""\
We attempted to fix a task. Review the current state and determine if it is complete.

Task:
{prompt}

Planned Changes:
{json.dumps(plan, indent=2)}

Current git diff:
```diff
{current_diff}
```

Task:
1. Compare the git diff against the planned changes.
2. Identify any missing or incorrect modifications.
3. Output ONLY a JSON object:

{{
  "complete": true or false,
  "missing_changes": [
    {{
      "file": "relative/path/to/file.py",
      "issue": "What is missing or wrong"
    }}
  ],
  "summary": "Brief assessment"
}}

Output ONLY the JSON object.
"""

        verify_result = await run_headless(
            verification_prompt,
            auto_allow=auto_allow,
            json_mode=False,
            max_iterations=15,
            cwd=effective_cwd,
        )
        verification = _extract_json(verify_result.get("response", ""))
        if verification is None:
            _log("[VERIFY] Could not parse verification, assuming complete")
            break

        print(f"[VERIFY] complete={verification.get('complete')}, summary={verification.get('summary')}")
        for missing in verification.get("missing_changes", []):
            print(f"  - MISSING: {missing.get('file')}: {missing.get('issue')}")

        if verification.get("complete", True):
            _log("[VERIFY] Fix verified as complete")
            break
        else:
            missing = verification.get("missing_changes", [])
            if missing:
                extra = "\n\nREMINDERS FROM PREVIOUS ATTEMPT:\n"
                for m in missing:
                    extra += f"- {m.get('file')}: {m.get('issue')}\n"
                current_prompt = execution_prompt_base + extra
            else:
                _log("[VERIFY] No specific missing items listed, using best effort")
                break
    else:
        _log(f"[WARN] Max plan attempts ({max_plan_attempts}) reached")

    if json_mode:
        import json as json_mod
        print(json_mod.dumps(best_result, indent=2, default=str))

    return best_result
