# PilotCode TUI Automation Testing

This document describes the TUI automation testing framework for PilotCode.

## Quick Start

```bash
# Check available MCP TUI servers
python test_tui_automation.py --list-servers

# Run all tests
python test_tui_automation.py

# Run specific test
python test_tui_automation.py --test time_query
```

## Supported MCP Servers

### mcp-terminator (Recommended)
```bash
go install github.com/davidroman0O/mcp-terminator@latest
```

### mcp-tui-test
```bash
pip install mcp-tui-test
```

## Available Tests

- `startup` - Welcome screen verification
- `time_query` - Simple query ("现在几点了")
- `code_generation` - Factorial code generation
- `file_ops` - File read operations
- `project_analysis` - Project structure analysis
- `multi_turn` - Multi-turn conversation
- `clear` - /clear command
- `help` - /help command

## API Example

```python
from pilotcode.mcp_tui_client import TUITestClient

async with TUITestClient() as client:
    # Launch PilotCode
    await client.launch_tui("python -m pilotcode main --auto-allow")
    
    # Wait for welcome
    await client.expect_text("PilotCode", timeout=5)
    
    # Send query
    await client.send_keys("现在几点了\n")
    
    # Wait for response
    await client.expect_text("时间", timeout=15)
    
    # Capture screen
    screen = await client.capture_screen()
    print(screen.raw_text)
```

See full documentation in source code.
