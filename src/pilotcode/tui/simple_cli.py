#!/usr/bin/env python3
"""
Simple CLI UI for PilotCode - No TUI dependencies.
Uses standard input/output for maximum compatibility.

Refactored to use SessionService (MVC Controller) with SimpleCLIProtocol
(View adapter). Business logic has been moved to SessionService; this
module only handles CLI-specific rendering and the REPL loop.
"""

import asyncio
import sys
from pathlib import Path

# Ensure pilotcode can be imported
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from pilotcode.ui.protocol import (  # noqa: E402
    BlockEvent,
    BlockKind,
    BlockPhase,
    StatusUpdate,
    PermissionResult,
)
from pilotcode.ui.config import SessionConfig, CommandAction  # noqa: E402
from pilotcode.ui.session_service import SessionService  # noqa: E402
from pilotcode.utils.config import get_global_config  # noqa: E402

# ------------------------------------------------------------------
# SimpleCLIProtocol - View adapter for the CLI
# ------------------------------------------------------------------


class SimpleCLIProtocol:
    """UIProtocol adapter for the CLI using print() and input().

    Maps three-channel protocol events to simple terminal output:
    - Channel 1 (on_block_event): print() with emoji prefixes
    - Channel 2 (on_status_update): no-op (CLI has no status bar)
    - Channel 3 (request_permission): blocking input() [Y/n]
    - Channel 3 (request_user_input): blocking input()
    - on_error: print() error message
    """

    async def on_block_event(self, event: BlockEvent) -> None:
        """Render a block event to the terminal."""
        if event.kind == BlockKind.ASSISTANT:
            if event.phase == BlockPhase.OPEN:
                print()
                print("🤖 Thinking...")
                print()
            elif event.phase == BlockPhase.CLOSE:
                if event.content:
                    print()
                    print("📝 Response:")
                    print(event.content)
                    print()

        elif event.kind == BlockKind.THINKING:
            # Thinking content - show inline (DeepSeek/Qwen3)
            if event.phase == BlockPhase.DELTA and event.content:
                # Only show the latest thinking content (not accumulated)
                pass  # Skip thinking display in CLI for cleanliness

        elif event.kind == BlockKind.TOOL_CALL:
            if event.phase == BlockPhase.OPEN:
                tool_name = event.metadata.get("tool_name", event.content)
                tool_input = event.metadata.get("tool_input", {})
                self._print_tool_call(tool_name, tool_input)

        elif event.kind == BlockKind.TOOL_RESULT:
            if event.phase == BlockPhase.CLOSE:
                error = event.metadata.get("error", False)
                tool_name = event.metadata.get("tool_name", "")
                output = event.content
                self._print_tool_result(tool_name, output, success=not error)

        elif event.kind == BlockKind.SYSTEM:
            if event.phase == BlockPhase.CLOSE and event.content:
                print(event.content)

        elif event.kind == BlockKind.PLAN_PROGRESS:
            if event.phase == BlockPhase.CLOSE and event.content:
                print(event.content)

    async def on_status_update(self, update: StatusUpdate) -> None:
        """CLI has no status bar - ignore status updates."""
        pass

    async def request_permission(
        self, tool_name: str, params: dict, risk_level: str
    ) -> PermissionResult:
        """Ask user for permission via blocking input()."""
        print()
        print(f"🔧 Tool Request: {tool_name}")
        if "path" in params:
            print(f"   Path: {params['path']}")
        if "command" in params:
            print(f"   Command: {params['command']}")

        while True:
            try:
                response = input("Allow execution? [Y/n]: ").strip().lower()
                if response in ("", "y", "yes"):
                    return PermissionResult(allowed=True)
                elif response in ("n", "no"):
                    return PermissionResult(allowed=False)
                else:
                    print("Please enter 'y' or 'n'")
            except (EOFError, KeyboardInterrupt):
                return PermissionResult(allowed=False)

    async def request_user_input(self, question: str, options: list[str] | None = None) -> str:
        """Ask user a question via blocking input()."""
        print(f"\n❓ {question}")
        if options:
            print(f"   Options: {', '.join(options)}")
        try:
            return input("Your answer: ").strip()
        except (EOFError, KeyboardInterrupt):
            return ""

    async def on_error(self, error: str) -> None:
        """Print error message."""
        print(f"❌ Error: {error}")

    # --- CLI-specific rendering helpers ---

    @staticmethod
    def _print_tool_call(tool_name: str, tool_input: dict) -> None:
        """Print tool call notification."""
        desc = ""
        if tool_name == "Bash":
            desc = tool_input.get("command", "N/A")[:50]
        elif tool_name in ("FileRead", "FileWrite", "FileEdit"):
            desc = tool_input.get("path", "N/A")
        elif tool_name == "Glob":
            desc = f"pattern={tool_input.get('pattern', 'N/A')}"
        elif tool_name == "Grep":
            desc = f"searching '{tool_input.get('pattern', 'N/A')}'"
        elif tool_name == "AskUser":
            desc = f"asking: {tool_input.get('question', 'N/A')[:40]}"
        else:
            desc = str(list(tool_input.values())[0])[:50] if tool_input else "N/A"
        print(f"🔧 Executing {tool_name}: {desc}")

    @staticmethod
    def _print_tool_result(tool_name: str, output: str, *, success: bool) -> None:
        """Print tool execution result."""
        if not success:
            print(f"❌ Error: {output}")
            return
        output_display = output.strip()
        if len(output_display) > 500:
            print(f"  Output ({len(output_display)} chars):")
            print(f"    {output_display[:300]}...")
            print("    ... [truncated] ...")
            print(f"    ...{output_display[-100:]}")
        elif len(output_display) > 100:
            print(f"  Output: {output_display[:200]}...")
        else:
            print(f"  Output: {output_display}")


# ------------------------------------------------------------------
# SimpleCLI - thin shell around SessionService
# ------------------------------------------------------------------


class SimpleCLI:
    """Simple command-line interface for PilotCode.

    Uses SessionService for all business logic. This class only handles:
    - CLI-specific initialization (store, API connection test)
    - The REPL loop (run method)
    - Welcome/help display
    """

    def __init__(
        self,
        model_name: str = "kimi-k2-0713-preview",
        auto_allow: bool = False,
        max_iterations: int = 50,
        cwd: str | None = None,
        no_verify: bool = False,
    ):
        self.global_config = get_global_config()
        self.model_name = model_name
        self.auto_allow = auto_allow
        self.max_iterations = max_iterations
        self.no_verify = no_verify
        self._cwd = cwd or str(Path.cwd())

        # Initialize store for state management
        from pilotcode.state.app_state import get_default_app_state
        from pilotcode.state.store import Store, set_global_store
        from dataclasses import replace

        app_state = get_default_app_state()
        self.store = Store(app_state)
        self.store.set_state(lambda s: replace(s, cwd=self._cwd))
        set_global_store(self.store)

        # Create the UI protocol adapter
        self._cli_protocol = SimpleCLIProtocol()

        # Create session config
        session_config = SessionConfig(
            cwd=self._cwd,
            auto_allow=auto_allow,
            max_iterations=max_iterations,
            compilation_verify=not no_verify,
            auto_save=True,
            auto_compact=True,
        )

        # Create SessionService - it handles all business logic
        self._service = SessionService(
            ui=self._cli_protocol,
            config=session_config,
            get_app_state=self.store.get_state,
            set_app_state=lambda f: self.store.set_state(f),
        )

    @property
    def query_engine(self):
        """Access query engine from SessionService."""
        return self._service.query_engine

    def is_local_model(self) -> bool:
        """Check if using a local model (e.g., Ollama) that doesn't need API key."""
        model = self.global_config.default_model or ""
        base_url = self.global_config.base_url or ""

        local_indicators = [
            "ollama",
            "localhost",
            "127.0.0.1",
            ":11434",
        ]

        for indicator in local_indicators:
            if indicator in model.lower() or indicator in base_url.lower():
                return True

        return False

    async def test_api_connection(self) -> tuple[bool, str]:
        """Test LLM API connection by sending an actual request."""
        from pilotcode.utils.model_client import get_model_client, Message

        try:
            client = get_model_client()
            messages = [Message(role="user", content="Hi")]

            response_content = ""
            async for chunk in client.chat_completion(messages, stream=True, max_tokens=10):
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content")
                if content:
                    response_content += content

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

        is_local = self.is_local_model()

        if is_local:
            print()
            print(f"🖥️  Local model detected: {self.global_config.default_model}")
            print(f"   Base URL: {self.global_config.base_url}")
        else:
            api_key = self.global_config.api_key or ""
            if (
                not api_key
                or api_key in ("sk-placeholder", "", "test-api-key")
                or len(api_key) < 20
            ):
                print()
                print("⚠️  Warning: API key not configured or invalid!")
                print("   Run: ./pilotcode configure")
                print()
                return

        print()
        print("🔄 Testing LLM API connection...")

        try:
            api_working, message = asyncio.run(self.test_api_connection())

            if not api_working:
                print()
                print("❌ API connection failed!")
                print(f"   Model: {self.global_config.default_model}")
                print(f"   Base URL: {self.global_config.base_url}")
                print(f"   Error: {message}")
                print()

                if is_local:
                    print("Please check:")
                    print("  1. Your local model server is running")
                    print("  2. The base URL is correct")
                    print(f"     Example: ollama run {self.global_config.default_model}")
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
                print(f"✅ API connection successful ({self.global_config.default_model})")
                if not is_local:
                    print(f"   Response preview: {message[:50]}...")
                print()

        except Exception as e:
            print(f"⚠️  Could not test API: {e}")
            print()

        print()
        print("Commands:")
        print("  /help     - Show available commands")
        print("  /save     - Save session to unified storage")
        print("  /load     - Load session from unified storage")
        print("  /clear    - Clear conversation history")
        print("  /quit     - Exit application")
        print()
        if self.auto_allow:
            print("⚠️  Auto-allow mode: All tool executions will be allowed")
            print()
        print("Type your message or a command (press Ctrl+Q to quit)")
        print("-" * 60)

    def print_help(self):
        """Print help information."""
        print()
        print("Available Commands:")
        print("  /help           Show this help message")
        print("  /save [file]    Save to unified storage, or to file if .json given")
        print("  /load [id/file] Load from unified storage, or from file if .json given")
        print("  /clear          Clear conversation history and context")
        print("  /compact        Manually compress context")
        print("  /quit or /exit  Exit the application")
        print()
        print("Tips:")
        print("  • Use @filename to reference files in your queries")
        print("  • The AI can read, write, and analyze code files")
        print("  • Session context is maintained automatically")
        print("  • Context compresses automatically when it gets too long")
        print()

    async def run(self):
        """Main run loop."""
        self.print_welcome()

        while True:
            try:
                print()
                user_input = input("You: ").strip()

                if not user_input:
                    continue

                # Handle slash commands via SessionService
                if user_input.startswith("/"):
                    result = await self._service.handle_command(user_input)

                    if result.action == CommandAction.QUIT:
                        print("Goodbye! 👋")
                        break
                    elif result.action == CommandAction.CLEAR:
                        self._service.clear_history()
                        print("✅ Conversation history and context cleared")
                    elif result.action == CommandAction.ERROR:
                        print(f"❌ {result.message}")
                    elif result.action == CommandAction.UNKNOWN:
                        print(f"Unknown command: {user_input}")
                    elif result.message:
                        print(result.message)
                    continue

                # Process query via SessionService
                await self._service.process_query(user_input)

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
    parser.add_argument("--model-name", default="kimi-k2-0713-preview", help="Model name to use")
    parser.add_argument("--auto-allow", action="store_true", help="Auto-allow all tool executions")

    args = parser.parse_args()

    cli = SimpleCLI(model_name=args.model_name, auto_allow=args.auto_allow)

    try:
        asyncio.run(cli.run())
    except KeyboardInterrupt:
        print("\nGoodbye! 👋")


if __name__ == "__main__":
    main()
