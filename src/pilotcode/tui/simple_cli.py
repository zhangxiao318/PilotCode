#!/usr/bin/env python3
"""
Simple CLI UI for PilotCode - No TUI dependencies.
Uses standard input/output for maximum compatibility.
"""

import asyncio
import sys
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

# Ensure pilotcode can be imported
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from pilotcode.query_engine import QueryEngine, QueryResult
from pilotcode.types.message import UserMessage, AssistantMessage, ToolUseMessage, ToolResultMessage
from pilotcode.utils.config import get_global_config, GlobalConfig
from pilotcode.commands.base import process_user_input
from pilotcode.tools.base import ToolUseContext as CommandContext


@dataclass
class SessionState:
    """Simple session state."""
    cwd: str = "."
    auto_allow: bool = False
    messages: list = field(default_factory=list)


class SimpleCLI:
    """Simple command-line interface for PilotCode."""
    
    def __init__(self, model_name: str = "kimi-k2-0713-preview", auto_allow: bool = False):
        self.config = get_global_config()
        self.query_engine: Optional[QueryEngine] = None
        self.auto_allow = auto_allow
        self.session_file: Optional[str] = None
        
        # Initialize query engine
        try:
            from pilotcode.query_engine import QueryEngineConfig
            from pilotcode.tools.registry import get_all_tools
            from pilotcode.permissions import get_tool_executor
            from pilotcode.permissions.permission_manager import (
                ToolPermission, PermissionLevel, get_permission_manager
            )
            
            tools = get_all_tools()
            config = QueryEngineConfig(
                cwd=str(Path.cwd()),
                tools=tools
            )
            self.query_engine = QueryEngine(config=config)
            
            # Set up tool executor
            self.tool_executor = get_tool_executor()
            
            # Set up auto-allow if requested
            if auto_allow:
                pm = get_permission_manager()
                for tool in tools:
                    pm._permissions[tool.name] = ToolPermission(
                        tool_name=tool.name,
                        level=PermissionLevel.ALWAYS_ALLOW
                    )
            
        except Exception as e:
            print(f"❌ Failed to initialize: {e}")
            sys.exit(1)
    
    def print_welcome(self):
        """Print welcome message."""
        print("=" * 60)
        print("  PilotCode v0.2.0 - Your AI Programming Assistant")
        print("=" * 60)
        print()
        print("Commands:")
        print("  /help     - Show available commands")
        print("  /save     - Save session to file")
        print("  /load     - Load session from file")
        print("  /clear    - Clear conversation history")
        print("  /quit     - Exit application")
        print()
        if self.auto_allow:
            print("⚠️  Auto-allow mode: All tool executions will be allowed")
            print()
        print("Type your message or a command (press Ctrl+C to quit)")
        print("-" * 60)
    
    def print_help(self):
        """Print help information."""
        print()
        print("Available Commands:")
        print("  /help           Show this help message")
        print("  /save [file]    Save conversation to file (default: session.json)")
        print("  /load [file]    Load conversation from file")
        print("  /clear          Clear conversation history")
        print("  /quit or /exit  Exit the application")
        print()
        print("Tips:")
        print("  • Use @filename to reference files in your queries")
        print("  • The AI can read, write, and analyze code files")
        print("  • Type your questions in natural language")
        print()
    
    def ask_permission(self, tool_name: str, params: dict) -> bool:
        """Ask user for permission to execute a tool."""
        if self.auto_allow:
            return True
        
        print()
        print(f"🔧 Tool Request: {tool_name}")
        
        # Show relevant params
        if 'path' in params:
            print(f"   Path: {params['path']}")
        if 'command' in params:
            print(f"   Command: {params['command']}")
        
        # Simple Y/n prompt
        while True:
            try:
                response = input("Allow execution? [Y/n]: ").strip().lower()
                if response in ('', 'y', 'yes'):
                    return True
                elif response in ('n', 'no'):
                    return False
                else:
                    print("Please enter 'y' or 'n'")
            except (EOFError, KeyboardInterrupt):
                return False
    
    async def handle_command(self, text: str) -> bool:
        """Handle slash commands. Returns True to continue, False to exit."""
        parts = text.split()
        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        if cmd == '/quit' or cmd == '/exit':
            print("Goodbye! 👋")
            return False
        
        elif cmd == '/help':
            self.print_help()
        
        elif cmd == '/clear':
            # Clear conversation in query engine
            if self.query_engine:
                # Re-initialize to clear history
                self.query_engine = QueryEngine(
                    model_name=self.query_engine.model_name,
                    api_key=None,
                    config=None
                )
            print("✅ Conversation history cleared")
        
        elif cmd == '/save':
            filename = args[0] if args else 'session.json'
            try:
                self.query_engine.save_session(filename)
                print(f"✅ Session saved to {filename}")
            except Exception as e:
                print(f"❌ Failed to save: {e}")
        
        elif cmd == '/load':
            filename = args[0] if args else 'session.json'
            try:
                if Path(filename).exists():
                    self.query_engine.load_session(filename)
                    print(f"✅ Session loaded from {filename}")
                    # Show loaded messages count
                    msg_count = len(self.query_engine.messages)
                    print(f"   {msg_count} messages restored")
                else:
                    print(f"❌ File not found: {filename}")
            except Exception as e:
                print(f"❌ Failed to load: {e}")
        
        else:
            print(f"❌ Unknown command: {cmd}")
            print("   Type /help for available commands")
        
        return True
    
    async def process_query(self, text: str):
        """Process a user query through the LLM with tool support."""
        if not self.query_engine:
            print("❌ Query engine not initialized")
            return
        
        # Check if it's a local command first
        if text.startswith('/'):
            context = CommandContext(cwd=str(Path.cwd()))
            is_command, result = await process_user_input(text, context)
            if is_command:
                if isinstance(result, str):
                    print(result)
                return
        
        print()
        print("🤖 Thinking...")
        print()
        
        try:
            iteration = 0
            max_iterations = 5
            current_prompt = text
            
            while iteration < max_iterations:
                iteration += 1
                accumulated_response = ""
                pending_tools = []
                
                # Process through query engine with streaming
                async for result in self.query_engine.submit_message(current_prompt):
                    msg = result.message
                    
                    if isinstance(msg, UserMessage):
                        # User message - skip
                        continue
                    
                    elif isinstance(msg, AssistantMessage):
                        # Accumulate assistant message content
                        if msg.content:
                            accumulated_response += msg.content
                        
                        # Only print when message is complete
                        if result.is_complete and accumulated_response:
                            print()
                            print("📝 Response:")
                            print(accumulated_response)
                            print()
                    
                    elif isinstance(msg, ToolUseMessage):
                        # Collect tool use requests
                        pending_tools.append(msg)
                        print(f"🔧 Tool requested: {msg.name}")
                
                # If no tools to execute, we're done
                if not pending_tools:
                    break
                
                # Execute all pending tools
                for tool_msg in pending_tools:
                    tool_name = tool_msg.name
                    params = tool_msg.input if isinstance(tool_msg.input, dict) else {}
                    
                    # Ask for permission
                    if not self.ask_permission(tool_name, params):
                        print("⛔ Tool execution denied")
                        self.query_engine.add_tool_result(tool_msg.tool_use_id, "Tool execution denied by user", is_error=True)
                        continue
                    
                    # Execute tool
                    cmd = params.get('command', 'N/A')
                    print(f"🔧 Executing {tool_name}: {cmd[:50]}...")
                    
                    try:
                        from pilotcode.tools.base import ToolUseContext
                        
                        ctx = ToolUseContext()
                        result = await self.tool_executor.execute_tool_by_name(
                            tool_name,
                            params,
                            ctx
                        )
                        
                        # Extract output from result
                        if result.success and result.result:
                            # Tool result has data attribute with actual output
                            if hasattr(result.result, 'data'):
                                tool_data = result.result.data
                                if hasattr(tool_data, 'stdout'):
                                    output = tool_data.stdout
                                else:
                                    output = str(tool_data)
                            else:
                                output = str(result.result)
                        else:
                            output = result.message or "Tool execution failed"
                        
                        print(f"  Output: {output[:80]}...")
                        self.query_engine.add_tool_result(tool_msg.tool_use_id, output, is_error=False)
                    except Exception as e:
                        self.query_engine.add_tool_result(tool_msg.tool_use_id, str(e), is_error=True)
                        print(f"❌ Error: {e}")
                
                # Continue loop to get LLM response with tool results
                # Use empty string to continue without adding new user message
                current_prompt = ""
        
        except Exception as e:
            print(f"❌ Error processing query: {e}")
    
    async def run(self):
        """Main run loop."""
        self.print_welcome()
        
        while True:
            try:
                # Get user input
                print()
                user_input = input("You: ").strip()
                
                if not user_input:
                    continue
                
                # Handle commands
                if user_input.startswith('/'):
                    should_continue = await self.handle_command(user_input)
                    if not should_continue:
                        break
                    continue
                
                # Process query
                await self.process_query(user_input)
            
            except KeyboardInterrupt:
                print("\n\nGoodbye! 👋")
                break
            except EOFError:
                print("\nGoodbye! 👋")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="PilotCode - AI Programming Assistant")
    parser.add_argument("--model-name", default="kimi-k2-0713-preview",
                       help="Model name to use")
    parser.add_argument("--auto-allow", action="store_true",
                       help="Auto-allow all tool executions")
    
    args = parser.parse_args()
    
    cli = SimpleCLI(
        model_name=args.model_name,
        auto_allow=args.auto_allow
    )
    
    try:
        asyncio.run(cli.run())
    except KeyboardInterrupt:
        print("\nGoodbye! 👋")


if __name__ == "__main__":
    main()
