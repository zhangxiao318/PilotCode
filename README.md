# PilotCode Python

Python rewrite of Claude Code - an AI-powered coding assistant.

## Overview

This is a Python reimplementation of the Claude Code CLI tool, maintaining architectural parity with the original TypeScript version while leveraging Python's strengths.

## Current Status

| Component | Implemented | Total | Progress |
|-----------|-------------|-------|----------|
| **Tools** | 18 | 40+ | 45% |
| **Commands** | 13 | 80+ | 16% |
| **Core Infrastructure** | - | - | 70% |
| **Lines of Code** | 6,080 | ~150,000 | 4% |

## Quick Start

```bash
# Run the demo
python3 full_demo.py

# Run the CLI
python3 -m pilotcode

# Or use the run script
./run.sh
```

## Implemented Features

### Tools (18)

#### File Operations
- **FileRead** - Read file contents with pagination
- **FileWrite** - Write content atomically
- **FileEdit** - Search/replace editing with conflict detection

#### Shell Execution
- **Bash** - Bash command execution with timeout
- **PowerShell** - PowerShell support (cross-platform)

#### Search
- **Glob** - File pattern matching
- **Grep** - Text search with regex
- **ToolSearch** - Find available tools

#### Web
- **WebSearch** - Search the web
- **WebFetch** - Fetch webpage content

#### Agents
- **Agent** - Spawn sub-agents for tasks

#### Tasks
- **TaskCreate**, **TaskGet**, **TaskList**, **TaskStop**, **TaskUpdate** - Background task management

#### Other
- **AskUser** - Interactive user prompts
- **TodoWrite** - Todo list management
- **Brief** - Text summarization
- **Config** - Configuration management
- **LSP** - Language Server Protocol
- **NotebookEdit** - Jupyter notebook editing

### Commands (13)

- `/help`, `/clear`, `/quit` - System commands
- `/config` - Configuration management
- `/theme` - Color theme switching
- `/model` - Model settings
- `/session` - Session management
- `/cost` - Usage statistics
- `/tasks` - Background task listing
- `/tools` - Tool listing
- `/agents` - Agent management
- `/git` - Git operations
- `/memory` - Memory management

### Core Infrastructure

- ✅ Type system (Pydantic models)
- ✅ Tool system with registry
- ✅ Command system
- ✅ Query engine
- ✅ State management (Store pattern)
- ✅ Configuration management
- ✅ Model client (OpenAI-compatible)
- ✅ MCP client (basic)
- ✅ TUI (Rich + Prompt Toolkit)

## Architecture

```
pilotcode/
├── types/          # Pydantic models for type safety
├── tools/          # Tool implementations (18 tools)
├── commands/       # Slash commands (13 commands)
├── components/     # TUI components
├── state/          # State management
├── utils/          # Utilities
├── services/       # External services
└── query_engine.py # LLM interaction
```

## TypeScript to Python Mapping

| TypeScript | Python |
|------------|--------|
| `type` / `interface` | Pydantic models / dataclasses |
| `async/await` | `asyncio` |
| `Promise<T>` | `Awaitable[T]` |
| React/Ink | Rich + Prompt Toolkit |
| Zod validation | Pydantic validation |
| Zustand | Custom Store class |

## Configuration

Configuration is loaded from `~/.config/pilotcode/settings.json`:

```json
{
  "theme": "default",
  "default_model": "default",
  "base_url": "http://172.19.201.40:3509/v1",
  "api_key": "sk-..."
}
```

Or from environment variables:
```bash
export LOCAL_API_KEY="sk-..."
export OPENAI_BASE_URL="http://172.19.201.40:3509/v1"
```

## Development

```bash
# Install dependencies
pip3 install platformdirs rich prompt-toolkit httpx pydantic

# Run tests
python3 run_tests.py

# Run demo
python3 full_demo.py
```

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - Architecture details
- [FEATURE_LIST.md](FEATURE_LIST.md) - Complete feature list
- [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) - Current status

## Missing Features

Major features not yet implemented:

- Permission system dialogs
- Agent swarms coordination
- Full MCP support
- GitHub integration
- Skills system
- Plugin system
- Background daemon mode
- Session persistence
- Analytics/telemetry
- Cost tracking

See [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for full details.

## Comparison with Original

| Metric | TypeScript Original | Python Version |
|--------|---------------------|----------------|
| Files | 1,884 | ~50 |
| Lines | ~512,000 | ~6,000 |
| Tools | 40+ | 18 |
| Commands | 80+ | 13 |
| Bundle Size | Large | Lightweight |

The Python version prioritizes:
1. **Readability** - Pythonic code with clear structure
2. **Maintainability** - Fewer lines, simpler abstractions
3. **Quick iteration** - No build step, direct execution

## Roadmap

### Phase 1: Core (✅ Complete)
- Basic architecture
- Tool system
- Command system
- Query engine

### Phase 2: Tools (In Progress)
- 22 more tools to implement
- Full shell integration
- Advanced search
- Web automation

### Phase 3: Commands (Pending)
- 67 more commands
- Git integration
- Session management
- Configuration

### Phase 4: TUI (Pending)
- Rich components
- Permission dialogs
- Progress indicators

### Phase 5: Services (Pending)
- Full MCP support
- Git integration
- LSP client

### Phase 6: Advanced (Future)
- Agent swarms
- Skills system
- Plugin system

## License

MIT

## Acknowledgments

This is a rewrite of Claude Code, originally developed by Anthropic.
