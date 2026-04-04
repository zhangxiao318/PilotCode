"""REPL for PilotCode - Programming Assistant with Tool Support."""

import asyncio
import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.status import Status
from rich.text import Text
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style

from ..tools.registry import get_all_tools
from ..tools.base import ToolUseContext
from ..commands.base import process_user_input, CommandContext
from ..query_engine import QueryEngine, QueryEngineConfig
from ..state.app_state import get_default_app_state
from ..state.store import Store, set_global_store
from ..utils.config import get_global_config
from ..types.message import AssistantMessage, ToolUseMessage
from ..permissions import get_tool_executor, PermissionLevel


class REPL:
    """Programming Assistant REPL with full tool support."""
    
    def __init__(self, auto_allow: bool = False):
        self.console = Console()
        self.store = Store(get_default_app_state())
        set_global_store(self.store)
        
        config = get_global_config()
        self.store.set_state(lambda s: s)
        
        self.session = PromptSession(
            message="❯ ",
            style=Style.from_dict({'prompt': '#00aa00 bold'})
        )
        
        # Enable all tools
        tools = get_all_tools()
        self.query_engine = QueryEngine(QueryEngineConfig(
            cwd=self.store.get_state().cwd,
            tools=tools,
            get_app_state=self.store.get_state,
            set_app_state=lambda f: self.store.set_state(f)
        ))
        
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
                    tool_name=tool.name,
                    level=PermissionLevel.ALWAYS_ALLOW
                )
            self.console.print("[dim]⚡ Auto-allow mode enabled - all tool executions will be allowed[/dim]\n")
        
        self.running = True
        
    def print_header(self) -> None:
        """Print welcome header."""
        self.console.print(Panel.fit(
            "[bold cyan]PilotCode[/bold cyan] [dim]v0.2.0[/dim]\n"
            "[cyan]AI Programming Assistant[/cyan]\n"
            "[dim]Type /help for commands, or ask me to write code![/dim]",
            border_style="cyan"
        ))
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
        max_iterations = 10
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            pending_tools = []
            
            # Show status
            with Status("[cyan]Thinking...[/cyan]", console=self.console, spinner="dots"):
                try:
                    async for result in self.query_engine.submit_message(prompt):
                        msg = result.message
                        
                        if isinstance(msg, AssistantMessage) and msg.content:
                            if isinstance(msg.content, str):
                                if result.is_complete:
                                    full_content = msg.content
                                else:
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
            
            # Execute pending tools
            if not pending_tools:
                # No tools to execute, we're done
                break
            
            for tool_msg in pending_tools:
                self.console.print(f"\n[dim]🔧 Tool: {tool_msg.name}[/dim]")
                
                # Execute with permission
                context = ToolUseContext(
                    get_app_state=self.store.get_state,
                    set_app_state=lambda f: self.store.set_state(f)
                )
                
                exec_result = await self.tool_executor.execute_tool_by_name(
                    tool_msg.name,
                    tool_msg.input,
                    context
                )
                
                # Add result to conversation
                result_content = ""
                if exec_result.success and exec_result.result:
                    result_content = str(exec_result.result.data) if exec_result.result.data else "Success"
                    self.console.print(f"[dim]✓ {tool_msg.name} completed[/dim]")
                else:
                    result_content = exec_result.message
                    self.console.print(f"[red]✗ {exec_result.message}[/red]")
                
                # Add to query engine history
                self.query_engine.add_tool_result(
                    tool_msg.tool_use_id,
                    result_content,
                    is_error=not exec_result.success
                )
            
            # Continue the conversation with tool results
            prompt = "Please continue based on the tool results above."
        
        if iteration >= max_iterations:
            self.console.print("[yellow]⚠️ Reached maximum tool execution rounds[/yellow]")
            
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


def run_repl(auto_allow: bool = False) -> None:
    """Run the REPL."""
    repl = REPL(auto_allow=auto_allow)
    asyncio.run(repl.run())


async def run_headless(
    prompt: str,
    auto_allow: bool = False,
    json_mode: bool = False,
    max_iterations: int = 10,
) -> dict[str, Any]:
    """Run a single prompt in headless mode and return structured output.
    
    Returns a dict with keys:
        - response: final assistant text
        - tool_calls: list of executed tools with results
        - success: bool
    """
    import json as json_mod
    from ..permissions import get_permission_manager, PermissionLevel, ToolPermission
    
    store = Store(get_default_app_state())
    set_global_store(store)
    
    tools = get_all_tools()
    query_engine = QueryEngine(QueryEngineConfig(
        cwd=store.get_state().cwd,
        tools=tools,
        get_app_state=store.get_state,
        set_app_state=lambda f: store.set_state(f)
    ))
    
    tool_executor = get_tool_executor()
    
    if auto_allow:
        pm = get_permission_manager()
        for tool in tools:
            pm._permissions[tool.name] = ToolPermission(
                tool_name=tool.name,
                level=PermissionLevel.ALWAYS_ALLOW
            )
    
    tool_calls_log: list[dict[str, Any]] = []
    response_text = ""
    success = True
    
    try:
        current_prompt = prompt
        for _ in range(max_iterations):
            pending_tools: list[ToolUseMessage] = []
            
            async for result in query_engine.submit_message(current_prompt):
                msg = result.message
                if isinstance(msg, AssistantMessage) and isinstance(msg.content, str):
                    if result.is_complete:
                        response_text = msg.content
                    else:
                        response_text += msg.content
                elif isinstance(msg, ToolUseMessage):
                    pending_tools.append(msg)
            
            if not pending_tools:
                break
            
            for tool_msg in pending_tools:
                context = ToolUseContext(
                    get_app_state=store.get_state,
                    set_app_state=lambda f: store.set_state(f)
                )
                exec_result = await tool_executor.execute_tool_by_name(
                    tool_msg.name,
                    tool_msg.input,
                    context
                )
                result_content = ""
                if exec_result.success and exec_result.result:
                    result_content = str(exec_result.result.data) if exec_result.result.data else "Success"
                else:
                    result_content = exec_result.message
                    success = False
                
                tool_calls_log.append({
                    "tool": tool_msg.name,
                    "input": tool_msg.input,
                    "success": exec_result.success,
                    "result": result_content,
                })
                
                query_engine.add_tool_result(
                    tool_msg.tool_use_id,
                    result_content,
                    is_error=not exec_result.success
                )
            
            current_prompt = "Please continue based on the tool results above."
    except Exception as e:
        success = False
        response_text = f"Error: {e}"
    
    output = {
        "response": response_text,
        "tool_calls": tool_calls_log,
        "success": success,
    }
    
    if json_mode:
        print(json_mod.dumps(output, indent=2))
    else:
        print(response_text)
    
    return output
