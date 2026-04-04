#!/usr/bin/env python3
"""PilotCode TUI Automation Test Runner.

This script uses MCP TUI testing servers to automatically test PilotCode's
TUI functionality including:
- Startup and welcome screen
- Query processing (time, code generation)
- File operations
- Project analysis
- Multi-turn conversations
- Commands (/help, /clear)

Requirements:
    - mcp-tui-test: pip install mcp-tui-test
      OR
    - mcp-terminator: go install github.com/davidroman0O/mcp-terminator@latest

Usage:
    python test_tui_automation.py
    python test_tui_automation.py --command "python -m pilotcode main --auto-allow"
    python test_tui_automation.py --server "mcp-terminator"
    python test_tui_automation.py --list-servers  # Check available servers
"""

import asyncio
import argparse
import sys
import subprocess
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from pilotcode.mcp_tui_client import PilotCodeTestSuite, run_pilotcode_tui_tests


def check_server_available(command: str) -> bool:
    """Check if an MCP server is available."""
    result = subprocess.run(
        ["which", command.split()[0]],
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def list_available_servers():
    """List all available MCP TUI servers."""
    print("Checking for available MCP TUI servers...\n")
    
    servers = [
        ("mcp-terminator", "Go", "go install github.com/davidroman0O/mcp-terminator@latest"),
        ("mcp-tui-test", "Python", "pip install mcp-tui-test"),
    ]
    
    found_any = False
    for name, lang, install_cmd in servers:
        available = check_server_available(name)
        status = "✅ Available" if available else "❌ Not found"
        print(f"{status}: {name} ({lang})")
        if not available:
            print(f"   Install: {install_cmd}")
        else:
            found_any = True
        print()
    
    if not found_any:
        print("No MCP TUI servers found. Please install one of the above.")
        print("\nRecommended: mcp-terminator (faster, more features)")
        print("  go install github.com/davidroman0O/mcp-terminator@latest")
    
    return found_any


async def main():
    parser = argparse.ArgumentParser(
        description="PilotCode TUI Automation Tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all tests with auto-detected server
  python test_tui_automation.py

  # Use specific PilotCode command
  python test_tui_automation.py --command "python -m pilotcode main --auto-allow"

  # Use specific MCP server
  python test_tui_automation.py --server "mcp-terminator"

  # Check available servers
  python test_tui_automation.py --list-servers

  # Run specific test only
  python test_tui_automation.py --test startup
  python test_tui_automation.py --test time_query
  python test_tui_automation.py --test code_generation
        """
    )
    
    parser.add_argument(
        "--command",
        default="python -m pilotcode main --auto-allow",
        help="Command to launch PilotCode TUI (default: %(default)s)"
    )
    parser.add_argument(
        "--server",
        help="MCP TUI server command (auto-detected if not specified)"
    )
    parser.add_argument(
        "--list-servers",
        action="store_true",
        help="List available MCP TUI servers and exit"
    )
    parser.add_argument(
        "--test",
        choices=["startup", "time_query", "code_generation", "file_ops", 
                 "project_analysis", "multi_turn", "clear", "help", "all"],
        default="all",
        help="Run specific test only (default: all)"
    )
    parser.add_argument(
        "--screenshots",
        help="Directory to save screenshots (default: temp dir)"
    )
    
    args = parser.parse_args()
    
    # List servers mode
    if args.list_servers:
        available = list_available_servers()
        sys.exit(0 if available else 1)
    
    # Check if any server is available
    if not args.server:
        has_terminator = check_server_available("mcp-terminator")
        has_tui_test = check_server_available("mcp-tui-test")
        
        if not has_terminator and not has_tui_test:
            print("Error: No MCP TUI server found!")
            print("\nPlease install one of:")
            print("  1. mcp-terminator (recommended): go install github.com/davidroman0O/mcp-terminator@latest")
            print("  2. mcp-tui-test: pip install mcp-tui-test")
            print("\nOr specify server path with --server")
            sys.exit(1)
    
    # Run tests
    print("=" * 70)
    print("PILOTCODE TUI AUTOMATION TESTS")
    print("=" * 70)
    print(f"PilotCode: {args.command}")
    print(f"Server: {args.server or 'auto-detect'}")
    print(f"Test: {args.test}")
    print("=" * 70)
    
    try:
        if args.test == "all":
            exit_code, results = await run_pilotcode_tui_tests(
                pilotcode_command=args.command,
                server_command=args.server
            )
        else:
            # Run specific test
            async with PilotCodeTestSuite(
                pilotcode_command=args.command,
                server_command=args.server,
                screenshots_dir=args.screenshots
            ) as suite:
                test_map = {
                    "startup": suite.test_startup,
                    "time_query": suite.test_time_query,
                    "code_generation": suite.test_code_generation,
                    "file_ops": suite.test_file_operations,
                    "project_analysis": suite.test_project_analysis,
                    "multi_turn": suite.test_multi_turn_conversation,
                    "clear": suite.test_clear_command,
                    "help": suite.test_help_command,
                }
                
                result = await test_map[args.test]()
                suite.print_report([result])
                exit_code = 0 if result.passed else 1
        
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
