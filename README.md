# PilotCode Python

[中文](README.md) | [English](README_EN.md)

Python rewrite of Claude Code - an AI-powered coding assistant.

## Overview

This is a Python reimplementation of the Claude Code CLI tool, maintaining architectural parity with the original TypeScript version while leveraging Python's strengths.

## About

**PilotCode** 是一款由西北工业大学计算机学院张晓开发的 AI 辅助编程工具。该工具参考 Claude Code 的实现，采用纯 Python 实现，旨在为开发者提供智能化的编程辅助体验。

### 主要特点

- **纯 Python 实现**：代码简洁，易于理解和二次开发
- **跨平台支持**：已在 Ubuntu 和 Windows 系统上完成测试，确保稳定运行
- **多模型兼容**：支持国内外主流大模型 API，已测试接入通义千问（Qwen）API

### 获取与反馈

欢迎广大开发者下载试用，体验 AI 辅助编程带来的效率提升。如有任何建议或问题，欢迎通过邮件联系开发者：**zhangxiao@nwpu.edu.cn**

## Quick Start

📖 **详细指南请查看 [QUICKSTART.md](QUICKSTART.md)**

```bash
# 1. 安装
pip3 install -e .

# 2. 配置 LLM（交互式向导）
python3 -m pilotcode configure

# 3. 运行（Linux/macOS）
./pilotcode.sh

# 或 Windows
.\pilotcode.cmd

# 或使用 Python 模块方式
python3 -m pilotcode
```

更多启动方式：
```bash
# 运行演示
python3 full_demo.py

# 单次命令模式
python3 -m pilotcode -p "分析当前目录的代码结构"

# 简单 CLI 模式
python3 -m pilotcode --simple
```

## Model Configuration

PilotCode supports both international and domestic (China) language models. Model parameters are managed via `config/models.json` and can be dynamically verified at runtime. See [Model Configuration & Capability Verification](docs/features/model-configuration.md) for details.

You can configure the model through:

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

# View model capabilities and runtime-probed info
python3 -m pilotcode config --list
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

### Commands (15)

- `/help`, `/clear`, `/quit` - System commands
- `/index` - Codebase indexing for intelligent search
- `/search` - Semantic and symbol-based code search
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

## Code Indexing & Search

PilotCode 包含企业级的代码索引和智能搜索系统，类似于 Claude Code 的代码库理解能力。

### 快速开始

```bash
# 1. 索引代码库（首次使用）
/index full

# 2. 语义搜索（自然语言）
/search authentication middleware

# 3. 符号搜索（精确查找）
/search -s UserModel

# 4. 正则搜索
/search -r "class.*View"
```

### 功能特性

| 功能 | 说明 | 示例 |
|------|------|------|
| **语义搜索** | 自然语言查询代码 | `/search database connection` |
| **符号搜索** | 精确查找类/函数/变量 | `/search -s calculate_total` |
| **正则搜索** | 正则表达式匹配 | `/search -r "TODO|FIXME"` |
| **文件搜索** | 按文件名查找 | `/search -f "*test*.py"` |
| **多语言支持** | Python, C/C++, JS/TS, Go, Rust, Java | `/search -s MyClass -l cpp` |

### 支持的文件类型

- **Python**: `.py`, `.pyw`, `.pyi`
- **C/C++**: `.c`, `.h`, `.cpp`, `.hpp`, `.cc`, `.hh`, `.cxx`, `.hxx`
- **JavaScript/TypeScript**: `.js`, `.jsx`, `.ts`, `.tsx`
- **Go/Rust/Java**: `.go`, `.rs`, `.java`
- **其他**: `.rb`, `.php`, `.swift`, `.kt`

### 性能对比

| 操作 | 无索引 (Grep) | 有索引 | 提升 |
|------|--------------|--------|------|
| 查找类定义 | 5+ 秒 | <10ms | **500x** |
| 语义搜索 | 不支持 | <50ms | ∞ |
| 项目结构分析 | 手动扫描 | 即时 | ∞ |

更多详细用法请参考 [QUICKSTART.md](QUICKSTART.md) 中的"代码索引与搜索"章节。

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
