# PilotCode Python

[中文](README.md) | English

Python rewrite of Claude Code - an AI-powered coding assistant.

## Overview

This is a Python reimplementation of the Claude Code CLI tool, maintaining architectural parity with the original TypeScript version while leveraging Python's strengths.

## About

**PilotCode** is an AI-powered coding assistant developed by Zhang Xiao from the School of Computer Science, Northwestern Polytechnical University (NWPU). This tool references Claude Code's implementation and is built with pure Python, aiming to provide developers with an intelligent programming assistance experience.

### Key Features

- **Pure Python Implementation**: Clean code, easy to understand and extend
- **Cross-Platform Support**: Tested on Ubuntu and Windows systems for stable operation
- **Multi-Model Compatibility**: Supports mainstream LLM APIs both domestically and internationally, with tested integration of Qwen (Tongyi Qianwen) API

### Contact

We welcome developers to download and try PilotCode to experience the efficiency boost of AI-assisted programming. For any suggestions or questions, please contact the developer via email: **zhangxiao@nwpu.edu.cn**

## Quick Start

📖 **For detailed guide, see [QUICKSTART_EN.md](QUICKSTART_EN.md)**

```bash
# 1. Install
pip3 install -e .

# 2. Configure LLM (interactive wizard)
python3 -m pilotcode configure

# 3. Run
python3 -m pilotcode main
```

More ways to start:
```bash
# Run demo
python3 full_demo.py

# Or use the launch script (Linux/macOS)
./pilotcode.sh

# Windows
.\pilotcode.cmd
```

## Model Configuration

PilotCode supports both international and domestic (China) language models. You can configure the model through:

1. **Interactive Configuration Wizard** (Recommended)
2. **Environment Variables**
3. **Configuration File** (`~/.config/pilotcode/settings.json`)

### Interactive Configuration (Recommended)

Run the interactive configuration wizard to easily set up your model:

```bash
# Run configuration wizard
python3 -m pilotcode configure

# Or use the shortcut
python3 -m pilotcode.cli configure --wizard
```

The wizard will guide you through:
1. Selecting a model category (International/Domestic/Local)
2. Choosing a specific model
3. Entering your API key
4. Optional settings (theme, auto-compact, etc.)

### Quick Configuration

```bash
# Configure with specific model
python3 -m pilotcode configure --model deepseek --api-key your-api-key

# List all available models
python3 -m pilotcode configure --list-models

# Show current configuration
python3 -m pilotcode configure --show
```

### Supported Models

#### International Models

| Model | Provider | Description |
|-------|----------|-------------|
| `openai` | OpenAI | GPT-4o - Most capable multimodal model |
| `openai-gpt4` | OpenAI | GPT-4 Turbo - High capability model |
| `anthropic` | Anthropic | Claude 3.5 Sonnet - Excellent coding assistant |
| `azure` | Azure | Azure OpenAI Service - Enterprise grade |

#### Domestic (China) Models

| Model | Provider | Description |
|-------|----------|-------------|
| `deepseek` | DeepSeek | DeepSeek V3 - Strong coding capabilities, cost-effective |
| `qwen` | Alibaba | Qwen Max - Powerful Chinese/English model |
| `qwen-plus` | Alibaba | Qwen Plus - Balanced performance and cost |
| `zhipu` | Zhipu | GLM-4 - Strong Chinese model with tool use |
| `moonshot` | Moonshot | Kimi - Long context window model |
| `baichuan` | Baichuan | Baichuan 4 - Advanced Chinese model |
| `doubao` | ByteDance | Doubao - Versatile model |

#### Local/Custom Models

| Model | Description |
|-------|-------------|
| `ollama` | Local Ollama instance (no API key needed) |
| `custom` | Custom OpenAI-compatible endpoint |

### Environment Variables

You can configure PilotCode using environment variables:

```bash
# Generic configuration
export PILOTCODE_API_KEY="your-api-key"
export PILOTCODE_MODEL="deepseek"
export PILOTCODE_BASE_URL="https://api.deepseek.com/v1"

# Provider-specific (auto-detected)
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export DEEPSEEK_API_KEY="sk-..."
export DASHSCOPE_API_KEY="sk-..."
export ZHIPU_API_KEY="..."
export MOONSHOT_API_KEY="sk-..."
export BAICHUAN_API_KEY="sk-..."
export ARK_API_KEY="..."
```

### Configuration File

The configuration is stored in `~/.config/pilotcode/settings.json`:

```json
{
  "theme": "default",
  "verbose": false,
  "auto_compact": true,
  "default_model": "deepseek",
  "model_provider": "deepseek",
  "api_key": "sk-...",
  "base_url": "https://api.deepseek.com/v1",
  "allowed_tools": [],
  "mcp_servers": {}
}
```

### Getting API Keys

- **OpenAI**: https://platform.openai.com/api-keys
- **Anthropic**: https://console.anthropic.com/settings/keys
- **DeepSeek**: https://platform.deepseek.com/api_keys
- **Qwen (Alibaba)**: https://dashscope.aliyun.com/api-key-management
- **Zhipu**: https://open.bigmodel.cn/usercenter/apikeys
- **Moonshot**: https://platform.moonshot.cn/console/api-keys
- **Baichuan**: https://platform.baichuan-ai.com/console/apikey
- **Doubao**: https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey

## Current Status

| Component | Implemented | Total | Progress |
|-----------|-------------|-------|----------|
| **Tools** | 18 | 40+ | 45% |
| **Commands** | 13 | 80+ | 16% |
| **Core Infrastructure** | - | - | 70% |
| **Lines of Code** | 6,080 | ~150,000 | 4% |

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
│   ├── config.py           # Configuration management
│   ├── models_config.py    # Supported models
│   └── configure.py        # Interactive configuration wizard
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

## Development

```bash
# Install dependencies
pip3 install -e .

# Run tests
python3 run_tests.py

# Run demo
python3 full_demo.py

# Configure
python3 -m pilotcode configure
```

## Documentation

- [Architecture](docs/architecture/ARCHITECTURE.md) - Architecture details
- [Features](docs/features/README.md) - Feature documentation
- [Guides](docs/guides/README.md) - User guides

## Comparison with Original

| Metric | TypeScript Original | Python Version |
|--------|---------------------|----------------|
| Files | 1,884 | ~50 |
| Lines | ~512,000 | ~6,000 |
| Tools | 40+ | 18 |
| Commands | 80+ | 13 |
| Bundle Size | Large | Lightweight |

The Python version prioritizes:

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
