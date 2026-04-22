# PilotCode TUI v2 (MVP)

Enhanced Terminal UI for PilotCode - MVP Version

## Features

### Core Architecture
- **Provider Pattern**: ThemeProvider, SessionProvider for state management
- **TUIController**: Bridges TUI with PilotCode core (QueryEngine, Tools, etc.)
- **Component-based**: Reusable UI components with Textual

### UI Components
- **PromptInput**: Multi-line input with history (↑/↓ navigation)
- **MessageList**: Scrollable chat interface with message types (user/assistant/tool/system)
- **StatusBar**: Shows processing state, token count, shortcuts
- **PermissionDialog**: Modal dialog for tool execution approval

### Commands (All 68 commands supported)
All internal commands work correctly:
- `/help` - Show available commands
- `/test` - Run project tests
- `/save [file]` - Save session (default: session.json)
- `/load [file]` - Load session
- `/clear` - Clear conversation
- `/quit` - Exit application
- `/agents` - Manage sub-agents
- `/git` - Git operations
- `/config` - Configuration management
- And 58 more commands...

### Keyboard Shortcuts
- `Ctrl+D` - Quit
- `Ctrl+S` - Save session
- `Ctrl+L` - Clear conversation
- `Ctrl+B` - Toggle sidebar
- `F1` - Show help
- `Enter` - Send message
- `Ctrl+Enter` - New line in input
- `↑/↓` - Navigate input history

## Usage

```bash
# Default: Simple CLI
./pilotcode

# Run with enhanced TUI v2
./pilotcode --tui-v2

# With auto-allow (for testing)
./pilotcode --tui-v2 --auto-allow

# Skip config check
./pilotcode --tui-v2 --skip-config-check
```

## Architecture

```
tui_v2/
├── app.py                 # Main app entry
├── controller/            # Integration with PilotCode core
│   └── controller.py      # TUIController
├── providers/             # State management
│   ├── theme.py           # ThemeProvider (2 themes)
│   └── session.py         # SessionProvider
├── components/            # UI components
│   ├── prompt/input.py    # PromptInput
│   ├── message/display.py # MessageList, MessageDisplay
│   ├── status/bar.py      # StatusBar
│   └── dialog/permission.py # PermissionDialog
└── screens/
    └── session.py         # Main session screen
```

## Code Statistics

- **Total Lines**: ~1,644
- **Providers**: ~300 lines
- **Components**: ~800 lines
- **Screens**: ~320 lines
- **Controller**: ~280 lines

## Known Limitations (MVP)

- Sidebar not fully implemented (placeholder)
- @file references parsed but not interactive
- Only 2 built-in themes (default, light)
- No command palette
- No real-time streaming for assistant messages (chunked display)

## Future Enhancements

- Full sidebar with file tree, tool list, MCP servers
- Interactive @file autocomplete
- More themes (35+ like OpenCode)
- Command palette (`/` or `Ctrl+P`)
- Real message streaming
- Plugin system
