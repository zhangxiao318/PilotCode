# PilotCode Python - Development Status

## Overview
PilotCode Python is a rewrite of the TypeScript PilotCode project in Python. It provides an AI-powered programming assistant with tool support, agent orchestration, and a rich terminal UI.

**Current Version:** v0.2.0  
**Total Lines of Code:** ~13,000  
**Tools:** 51  
**Commands:** 65  
**Git Commits:** 10+

---

## Architecture

### Core Components

| Component | Description | Status |
|-----------|-------------|--------|
| Tool System | Registry-based tool system with 51 tools | ✅ Complete |
| Command System | 65 slash commands for various operations | ✅ Complete |
| Query Engine | LLM interaction with streaming support | ✅ Complete |
| State Management | Store pattern for application state | ✅ Complete |
| Agent System | 7 agent types with orchestrator | ✅ Complete |
| Hook System | 5 hook types for extensibility | ✅ Complete |
| TUI Components | Rich-based UI with permission dialogs | ✅ Complete |
| Permission System | Risk-based permission levels | ✅ Complete |

### Agent Types
1. **coder** - General software engineering tasks
2. **debugger** - Debugging and error analysis
3. **explainer** - Code explanation and documentation
4. **tester** - Test generation and execution
5. **reviewer** - Code review and quality checks
6. **planner** - Implementation planning
7. **explorer** - Codebase exploration

### Workflow Modes
- **single** - Direct agent execution
- **sequential** - Multi-step sequential workflow
- **parallel** - Concurrent agent execution
- **adaptive** - Dynamic workflow adjustment

---

## Tool Categories

### File Operations
- `FileRead` - Read file contents
- `FileWrite` - Write/create files
- `FileEdit` - Edit existing files
- `Glob` - Find files by pattern
- `Grep` - Search file contents

### System Operations
- `Bash` - Execute shell commands
- `Shell` - Extended shell operations

### Development Tools
- `Think` - Analysis and reasoning
- `GetErrors` - Error retrieval
- `Exit` - Session termination

### Agent Tools
- `Agent` - Delegate to sub-agents
- `Task` - Task management

---

## Permission System

### Permission Levels
| Level | Description |
|-------|-------------|
| `ASK` | Prompt user for each execution |
| `ALLOW` | Allow for current session |
| `ALWAYS_ALLOW` | Always allow this specific action |
| `DENY` | Deny this once |
| `NEVER_ALLOW` | Never allow this tool |

### Risk Levels
- **low** - Read-only operations
- **medium** - File modifications
- **high** - Destructive operations
- **critical** - System-level changes

---

## Recent Features Implemented

### 1. Prompt Cache (New)
**Status:** ✅ Complete with 24 tests  
**Description:** LLM response caching with memory and disk storage  
**Features:**
- SHA256-based cache keys for deterministic lookup
- Memory + disk tiered storage with configurable TTL
- Compression for disk storage
- Cache statistics tracking (hits, misses, token savings)
- Cache-aware message building for incremental updates

### 2. Tool Sandbox (New)
**Status:** ✅ Complete with 31 tests  
**Description:** Secure command execution with risk analysis  
**Features:**
- Command risk analysis (dangerous pattern detection)
- Sandbox levels: NONE, STANDARD, STRICT, ISOLATED
- Resource limits (timeout, memory, file descriptors)
- Path restrictions and network access control
- Security violation detection and reporting

### 3. Embedding Service (New)
**Status:** ✅ Complete with 37 tests  
**Description:** Vector embeddings for semantic code search  
**Features:**
- OpenAI API integration with local numpy fallback
- LRU caching for embeddings
- Cosine similarity search
- In-memory vector store
- Statistics tracking

### 4. LSP Manager (New)
**Status:** ✅ Complete with 27 tests  
**Description:** Language Server Protocol for multi-language code intelligence  
**Features:**
- Multi-language server management (Python, TypeScript, Rust, Go)
- JSON-RPC protocol implementation
- Document tracking and synchronization
- Code intelligence: definition, references, hover, completion, diagnostics

### 5. Event Bus (New)
**Status:** ✅ Complete with 33 tests  
**Description:** Decoupled event-driven architecture  
**Features:**
- Publish-subscribe pattern with priority ordering
- Wildcard subscriptions (e.g., `user.*`)
- Event middleware for cross-cutting concerns
- Dead letter queue for failed events
- Typed event bus for type-safe handling
- PilotCodeEvents constants for standard events

---

## Recent Fixes

### 1. Permission Prompt Hanging (Fixed)
**Issue:** Permission prompts would hang/"thinking" indefinitely  
**Root Cause:** `prompt_toolkit.prompt()` blocks async event loop  
**Solution:** Use standard `input()` wrapped in `loop.run_in_executor()`  
**Commit:** `b42a498`, `a57aa37`

### 2. Auto-Allow Not Executing Tools (Fixed)
**Issue:** With `--auto-allow`, tools showed "completed" but files weren't created  
**Root Cause:** Tool executor wasn't calling `validate_input()` or parsing input through Pydantic schema  
**Solution:** Added input validation and schema parsing before tool execution  
**Commit:** `d97adb0`, `e9a4a12`

### 3. Field Name Mapping (Fixed)
**Issue:** LLM uses `path` instead of `file_path` for file tools  
**Solution:** Added `_normalize_tool_input()` to map field names  
**Commit:** `08a0ef8`

### 4. UTF-8 Encoding (Fixed)
**Issue:** Chinese characters not displaying correctly  
**Solution:** Set `PYTHONIOENCODING=utf-8` in run.sh  
**Commit:** `acac106`

---

## Usage

### Basic Usage
```bash
./run.sh
```

### With Auto-Allow (Testing Mode)
```bash
./run.sh main --auto-allow
```

### Command Line Options
```bash
./run.sh main --help
```

### Available Options
- `--version, -v` - Show version
- `--verbose` - Enable verbose output
- `--model, -m` - Select model (default: default)
- `--cwd` - Set working directory
- `--auto-allow` - Auto-allow all tool executions

---

## Known Issues

### 1. Chinese Input (Terminal Configuration)
**Status:** Output works, input depends on terminal locale  
**Workaround:** Set terminal locale to UTF-8:
```bash
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
```

### 2. Tool Recursion Limit
**Status:** By design  
**Description:** Maximum 10 tool execution rounds to prevent infinite loops

### 3. Model Compatibility
**Status:** Configured for Qwen API  
**Note:** Uses `delta.content` for streaming (incremental), not accumulated content

---

## Project Structure

```
pilotcode_py/
├── src/pilotcode/
│   ├── agents/          # Agent system
│   ├── commands/        # Slash commands
│   ├── components/      # TUI components
│   ├── hooks/           # Hook system
│   ├── permissions/     # Permission system
│   ├── state/           # State management
│   ├── tools/           # Tool implementations
│   ├── types/           # Type definitions
│   ├── utils/           # Utilities
│   ├── cli.py           # CLI entry point
│   ├── query_engine.py  # LLM interaction
│   └── __main__.py      # Module entry
├── run.sh               # Startup script
├── pyproject.toml       # Project config
└── STATUS.md            # This file
```

---

## Dependencies

### Core
- `pydantic` - Data validation
- `rich` - Terminal UI
- `httpx` - HTTP client
- `prompt-toolkit` - Interactive prompts
- `platformdirs` - Cross-platform directories

### Development
- `pytest` - Testing
- `mypy` - Type checking
- `ruff` - Linting

---

## Future Enhancements

### Recently Completed ✅
- [x] Prompt Cache for LLM cost optimization (30%+ cost reduction)
- [x] Tool Sandbox for secure command execution
- [x] Embedding Service for semantic search
- [x] LSP Manager for multi-language code intelligence
- [x] Event Bus for decoupled architecture
- [x] GitHub Integration (Repositories, Issues, PRs, Actions, Releases)

### Planned
- [ ] MCP (Model Context Protocol) integration
- [ ] GitHub Integration (PRs, Issues, CI/CD)
- [ ] Additional agent types
- [ ] Advanced TUI (permission dialogs, status components)
- [ ] Multi-model support

### Under Consideration
- [ ] Plugin system for custom tools
- [ ] Web interface
- [ ] Git integration improvements
- [ ] Code indexing for large repositories

---

## Development Notes

### Adding a New Tool
1. Create tool file in `src/pilotcode/tools/`
2. Define input/output schemas with Pydantic
3. Implement call function
4. Register with `@register_tool` or `register_tool()`

### Adding a New Command
1. Create command file in `src/pilotcode/commands/`
2. Implement command function with `@command` decorator
3. Add to command registry

### Adding a New Hook
1. Define hook type in `src/pilotcode/hooks/base.py`
2. Implement hook in `src/pilotcode/hooks/builtin_hooks.py`
3. Register in `HookManager`

---

## Testing

### Manual Testing
```bash
# Test file creation
./run.sh main --auto-allow
# Then: 创建一个计算阶乘的Python程序 factorial.py

# Test permission prompt
./run.sh
# Then: 读取 README.md 文件
```

### Unit Tests
```bash
pytest
```

---

## License

MIT License - See LICENSE file for details

---

## Contributors

- Claude Code (AI Assistant)

---

*Last Updated: 2026-04-05*
