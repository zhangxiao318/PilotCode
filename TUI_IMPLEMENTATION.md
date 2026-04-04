# PilotCode TUI Implementation

Based on `/home/zx/mycc/docs/TUI设计.txt` design document.

## Layout Structure (三层布局)

```
┌─────────────────────────────────────────────────────────────┐
│  [AI Assistant Output Area]                      (Layer 1)  │
│  ─────────────────────────────────────────────────────────  │
│  • Message bubbles with Markdown rendering                  │
│  • Code syntax highlighting with copy buttons               │
│  • Tool execution visualization                             │
│  • Collapsible thinking process                             │
└─────────────────────────────────────────────────────────────┘
│  [User Input Area]                               (Layer 2)  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Multi-line text input with auto-resize                │  │
│  │ Support Shift+Enter for newline, Enter to send        │  │
│  └───────────────────────────────────────────────────────┘  │
│  [Attach] [Model ▼]                           [Send/Stop]   │
├─────────────────────────────────────────────────────────────┤
│  [Status Bar]                                    (Layer 3)  │
│  ┌──────────┬──────────┬──────────┬──────────────────────┐ │
│  │ ● Model  │ Token    │ Tips:    │                      │ │
│  │ PilotCode│ ████░░   │ /help    │                      │ │
│  └──────────┴──────────┴──────────┴──────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. TokenUsageBar (Token用量进度条)
**File**: `tui/enhanced_app.py`

Features:
- Color-coded progress: Green (<50%), Yellow (<80%), Red (>90%)
- Shows current/max tokens (e.g., "44.5k/262.1k")
- Visual progress bar using block characters

### 2. StatusBarWidget (状态栏)
**File**: `tui/enhanced_app.py`

Layout:
- **Left**: Model name + connection status indicator (●)
- **Center**: TokenUsageBar
- **Right**: Quick command tips (/help, /theme)

### 3. InputArea (输入区)
**File**: `tui/enhanced_app.py`

Features:
- Multi-line text area with auto-resize (max-height: 5 lines)
- Toolbar with [Attach], [Model] buttons
- Send/Stop button that toggles based on generation state
- Shift+Enter for new line, Enter to send

### 4. ToolExecutionWidget (工具执行可视化)
**File**: `tui/enhanced_app.py`

Features:
- Shows tool name and execution status
- Pending: Yellow loading indicator
- Success: Green with result preview
- Failed: Red with error message
- Collapsible/expandable details

### 5. MessageBubble (消息气泡)
**File**: `tui/enhanced_app.py`

Features:
- Different styles for User/Assistant/System/Error
- Markdown rendering support
- Code syntax highlighting
- Auto-scroll to latest message

### 6. PilotCodeTUI (主应用)
**File**: `tui/enhanced_app.py`

Features:
- Three-layer layout using Textual CSS
- Keyboard shortcuts:
  - `Ctrl+C`: Quit
  - `Ctrl+L`: Clear output
  - `Esc`: Cancel generation
- Integration with QueryEngine and permissions
- Token usage tracking

## Key Interactions

### Message Rendering
- User messages: Blue border with 👤 icon
- Assistant messages: Green border with 🤖 icon
- System messages: Dim style with ⚙️ icon
- Tool calls: Yellow border with 🔧 icon
- Errors: Red border with ❌ icon

### Code Blocks
- Syntax highlighting using Rich's Syntax
- Line numbers enabled
- Monokai theme
- Language detection from file extension

### Token Usage Display
```python
# Color coding logic
if percentage < 50:
    color = "green"
elif percentage < 80:
    color = "yellow"
else:
    color = "red"
```

### Input Handling
- **Enter**: Submit message (when not generating)
- **Shift+Enter**: Insert newline
- **Button toggle**: Send → Stop (during generation)

## Styling

### Colors
- Primary: Cyan
- Success: Green
- Warning: Yellow
- Error: Red
- Background: Dark surface

### Typography
- Code: JetBrains Mono (via Rich)
- UI: System default with Rich styling

## Usage

```python
from pilotcode.tui import PilotCodeTUI

# Run the TUI app
app = PilotCodeTUI()
app.run()

# Or with auto-allow mode
app = PilotCodeTUI(auto_allow=True)
app.run()
```

## Testing

```bash
# Run TUI tests
PYTHONPATH=src python3 -m pytest src/tests/test_tui_enhanced.py -v

# Run all tests
PYTHONPATH=src python3 -m pytest src/tests/ -v
```

## Future Enhancements

1. **Streaming Output**: Real-time token-by-token display
2. **Image Display**: Support for image output in messages
3. **Themes**: Light/dark theme switching
4. **Split View**: Side-by-side diff for file edits
5. **Terminal Output**: ANSI color support for command results
