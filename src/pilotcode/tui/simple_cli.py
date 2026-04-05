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
from pilotcode.types.message import UserMessage, AssistantMessage, ToolUseMessage, ToolResultMessage, SystemMessage
from pilotcode.utils.config import get_global_config, GlobalConfig
from pilotcode.commands.base import process_user_input
from pilotcode.tools.base import ToolUseContext as CommandContext
from pilotcode.services.session_context import (
    get_session_context_manager, 
    reset_session_context,
    SessionContextManager
)
from pilotcode.services.context_compression import get_context_compressor


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
        
        # Initialize session context manager for maintaining project context
        self.session_context = get_session_context_manager()
        
        # Context compression threshold
        self.compression_threshold = 20  # Compress after 20 messages
        
        # Initialize query engine
        try:
            from pilotcode.query_engine import QueryEngineConfig
            from pilotcode.tools.registry import get_all_tools
            from pilotcode.permissions import get_tool_executor
            from pilotcode.permissions.permission_manager import (
                ToolPermission, PermissionLevel, get_permission_manager
            )
            from pilotcode.state.app_state import get_default_app_state
            from pilotcode.state.store import Store, set_global_store
            
            # Initialize store for state management
            app_state = get_default_app_state()
            self.store = Store(app_state)
            set_global_store(self.store)
            
            tools = get_all_tools()
            config = QueryEngineConfig(
                cwd=str(Path.cwd()),
                tools=tools,
                get_app_state=self.store.get_state,
                set_app_state=lambda f: self.store.set_state(f)
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
    
    def is_local_model(self) -> bool:
        """Check if using a local model (e.g., Ollama) that doesn't need API key.
        
        Returns:
            True if using a local model.
        """
        model = self.config.default_model or ""
        base_url = self.config.base_url or ""
        
        # Check for local model indicators
        local_indicators = [
            "ollama",
            "localhost",
            "127.0.0.1",
            ":11434",  # Ollama default port
        ]
        
        for indicator in local_indicators:
            if indicator in model.lower() or indicator in base_url.lower():
                return True
        
        return False
    
    async def test_api_connection(self) -> tuple[bool, str]:
        """Test LLM API connection by sending an actual request.
        
        Returns:
            Tuple of (success, message/error)
        """
        from pilotcode.utils.model_client import get_model_client, Message
        
        try:
            client = get_model_client()
            # Send a simple test message
            messages = [Message(role="user", content="Hi")]
            
            response_content = ""
            async for chunk in client.chat_completion(messages, stream=True, max_tokens=10):
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content")
                if content:
                    response_content += content
            
            # If we got any response, API is working
            if len(response_content) > 0:
                return True, response_content.strip()
            else:
                return False, "Empty response from model"
            
        except Exception as e:
            error_msg = str(e)
            if "authentication" in error_msg.lower() or "unauthorized" in error_msg.lower():
                return False, "Authentication failed - check your API key"
            elif "connection" in error_msg.lower():
                return False, "Connection failed - check network and base URL"
            else:
                return False, f"API error: {error_msg}"
    
    def print_welcome(self):
        """Print welcome message and test API connection."""
        print("=" * 60)
        print("  PilotCode v0.2.0 - Your AI Programming Assistant")
        print("=" * 60)
        
        # Check if using local model
        is_local = self.is_local_model()
        
        if is_local:
            print()
            print(f"🖥️  Local model detected: {self.config.default_model}")
            print(f"   Base URL: {self.config.base_url}")
        else:
            # Check if API key looks valid for cloud models
            api_key = self.config.api_key or ""
            if not api_key or api_key in ("sk-placeholder", "", "test-api-key") or len(api_key) < 20:
                print()
                print("⚠️  Warning: API key not configured or invalid!")
                print("   Run: ./pilotcode configure")
                print()
                return
        
        # Test API connection with actual request
        print()
        print("🔄 Testing LLM API connection...")
        
        try:
            import asyncio
            api_working, message = asyncio.run(self.test_api_connection())
            
            if not api_working:
                print()
                print("❌ API connection failed!")
                print(f"   Model: {self.config.default_model}")
                print(f"   Base URL: {self.config.base_url}")
                print(f"   Error: {message}")
                print()
                
                if is_local:
                    print("Please check:")
                    print("  1. Your local model server is running")
                    print("  2. The base URL is correct")
                    print(f"     Example: ollama run {self.config.default_model}")
                else:
                    print("Please check:")
                    print("  1. Your API key is correct")
                    print("  2. Your network connection")
                    print("  3. The model service is available")
                
                print()
                print("To reconfigure, run: ./pilotcode configure")
                print()
                sys.exit(1)
            else:
                print(f"✅ API connection successful ({self.config.default_model})")
                if not is_local:
                    print(f"   Response preview: {message[:50]}...")
                print()
                
        except Exception as e:
            print(f"⚠️  Could not test API: {e}")
            print()
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
        print("  /clear          Clear conversation history and context")
        print("  /context        Show current session context")
        print("  /project        Set project information")
        print("  /quit or /exit  Exit the application")
        print()
        print("Tips:")
        print("  • Use @filename to reference files in your queries")
        print("  • The AI can read, write, and analyze code files")
        print("  • Session context is maintained automatically")
        print("  • Context compresses automatically when it gets too long")
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
                from pilotcode.query_engine import QueryEngineConfig
                self.query_engine = QueryEngine(
                    config=QueryEngineConfig(
                        cwd=str(Path.cwd()),
                        tools=self.query_engine.config.tools,
                        get_app_state=self.store.get_state,
                        set_app_state=lambda f: self.store.set_state(f)
                    )
                )
            # Reset session context
            reset_session_context()
            self.session_context = get_session_context_manager()
            print("✅ Conversation history and context cleared")
        
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
        
        elif cmd == '/context':
            # Show current session context
            print()
            print(self.session_context.get_system_prompt_addition())
            print(f"   Messages: {len(self.query_engine.messages)}")
        
        elif cmd == '/project':
            # Set project information
            if len(args) >= 1:
                project_name = args[0]
                self.session_context.set_project_info(name=project_name)
                print(f"✅ Project name set to: {project_name}")
                if len(args) >= 2:
                    description = ' '.join(args[1:])
                    self.session_context.context.project.description = description
                    print(f"   Description: {description}")
            else:
                print("Usage: /project <name> [description]")
                print("Example: /project 博客系统 '一个基于Python的博客系统'")
        
        elif cmd == '/compact':
            # Manually trigger context compression
            print("\n🔄 Manually compressing context...")
            original_count = len(self.query_engine.messages)
            compressor = get_context_compressor()
            self.query_engine.messages = compressor.simple_compact(
                self.query_engine.messages,
                keep_recent=10
            )
            compressed_count = len(self.query_engine.messages)
            print(f"   Compressed: {original_count} -> {compressed_count} messages")
        
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
            context = CommandContext(
                get_app_state=self.store.get_state,
                set_app_state=lambda f: self.store.set_state(f)
            )
            is_command, result = await process_user_input(text, context)
            if is_command:
                if isinstance(result, str):
                    print(result)
                return
        
        print()
        print("🤖 Thinking...")
        print()
        
        try:
            # Check if we need to compress context before processing
            await self._check_and_compress_context()
            
            # Add session context to query engine messages if not present
            self._inject_session_context()
            
            iteration = 0
            max_iterations = 5
            current_prompt = text
            
            while iteration < max_iterations:
                iteration += 1
                accumulated_response = ""
                pending_tools = []
                
                # Process through query engine with streaming
                response_received = False
                async for result in self.query_engine.submit_message(current_prompt):
                    msg = result.message
                    
                    if isinstance(msg, UserMessage):
                        # User message - skip
                        continue
                    
                    elif isinstance(msg, AssistantMessage):
                        # Accumulate assistant message content
                        if msg.content:
                            accumulated_response += msg.content
                            response_received = True
                        
                        # Only print when message is complete
                        if result.is_complete:
                            if accumulated_response:
                                print()
                                print("📝 Response:")
                                print(accumulated_response)
                                print()
                            elif not response_received and not pending_tools:
                                # No response from model
                                print()
                                print("⚠️  No response from model. Check your API key and model configuration.")
                                print("   Run: ./pilotcode configure --show")
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
                    # Format tool description based on tool type
                    if tool_name == 'Bash':
                        desc = params.get('command', 'N/A')
                    elif tool_name == 'FileRead':
                        desc = f"reading {params.get('path', 'N/A')}"
                    elif tool_name == 'FileWrite':
                        desc = f"writing {params.get('path', 'N/A')}"
                    elif tool_name == 'FileEdit':
                        desc = f"editing {params.get('path', 'N/A')}"
                    elif tool_name == 'Glob':
                        desc = f"pattern={params.get('pattern', 'N/A')}"
                    elif tool_name == 'Grep':
                        desc = f"searching '{params.get('pattern', 'N/A')}'"
                    elif tool_name == 'AskUser':
                        desc = f"asking: {params.get('question', 'N/A')[:40]}"
                    else:
                        # Generic: show first param value
                        first_param = list(params.values())[0] if params else 'N/A'
                        desc = str(first_param)[:50]
                    
                    print(f"🔧 Executing {tool_name}: {desc[:50]}...")
                    
                    try:
                        from pilotcode.tools.base import ToolUseContext
                        
                        ctx = ToolUseContext(
                            get_app_state=self.store.get_state,
                            set_app_state=lambda f: self.store.set_state(f)
                        )
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
            
            # Update session context with this exchange
            self.session_context.update_from_message(text, accumulated_response)
            
            # Show project context hint if available
            project = self.session_context.context.project
            if project.name and iteration == 1:  # Only on first response
                print(f"\n📋 Project: {project.name}")
                if project.current_focus:
                    print(f"   Focus: {project.current_focus}")
        
        except Exception as e:
            print(f"❌ Error processing query: {e}")
    
    def _inject_session_context(self):
        """Inject session context into query engine messages as system message."""
        context_msg = self.session_context.get_system_prompt_addition()
        
        # Check if we already have a context message
        has_context = False
        for msg in self.query_engine.messages:
            if isinstance(msg, SystemMessage) and "=== Current Session Context ===" in msg.content:
                # Update existing context message
                msg.content = context_msg
                has_context = True
                break
        
        if not has_context and len(self.query_engine.messages) > 0:
            # Insert after first system message (or at beginning if no system message)
            first_system_idx = -1
            for i, msg in enumerate(self.query_engine.messages):
                if isinstance(msg, SystemMessage):
                    first_system_idx = i
                    break
            
            if first_system_idx >= 0:
                self.query_engine.messages.insert(first_system_idx + 1, SystemMessage(content=context_msg))
            else:
                self.query_engine.messages.insert(0, SystemMessage(content=context_msg))
    
    async def _check_and_compress_context(self):
        """Check if context needs compression and perform it if necessary."""
        msg_count = len(self.query_engine.messages)
        
        if self.session_context.should_compress_context(msg_count, self.compression_threshold):
            print("\n🔄 Context getting long, compressing...")
            
            from pilotcode.services.token_estimation import estimate_tokens
            
            # Get compressor
            compressor = get_context_compressor()
            
            # Compress messages
            original_count = len(self.query_engine.messages)
            self.query_engine.messages = compressor.simple_compact(
                self.query_engine.messages,
                keep_recent=10  # Keep last 10 messages
            )
            compressed_count = len(self.query_engine.messages)
            
            # Record compression
            self.session_context.record_compression()
            
            # Estimate tokens saved
            tokens_saved = estimate_tokens("dummy") * (original_count - compressed_count)
            
            print(f"   Compressed: {original_count} -> {compressed_count} messages (~{tokens_saved} tokens saved)")
            print("   Older messages summarized. Key context preserved.")
            print()
    
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
