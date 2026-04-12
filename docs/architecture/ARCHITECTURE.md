# PilotCode 架构文档

本文档描述 PilotCode 的整体架构和核心组件。

## 目录结构

```
src/pilotcode/
├── agent/                  # Agent 系统（多 Agent 协调）
│   ├── agent_hooks.py      # Agent 生命周期钩子
│   ├── agent_manager.py    # Agent 管理器
│   └── agent_orchestrator.py # Agent 编排器
├── commands/               # 斜杠命令实现
│   ├── base.py             # 命令基类和注册
│   ├── code_index_cmd.py   # /index - 代码索引
│   ├── code_search_cmd.py  # /search - 代码搜索
│   ├── git*.py             # Git 相关命令
│   └── ...                 # 其他命令
├── components/             # 组件
│   └── repl.py             # REPL 交互循环
├── context/                # 应用上下文
├── hooks/                  # 钩子系统
│   ├── builtin_hooks.py    # 内置钩子
│   └── hook_manager.py     # 钩子管理器
├── mcp_tui_client/         # MCP TUI 客户端
├── orchestration/          # 任务编排
│   ├── coordinator.py      # 任务协调器
│   ├── decomposer.py       # 任务分解器
│   └── executor.py         # 任务执行器
├── permissions/            # 权限管理
│   ├── permission_manager.py # 权限管理器
│   └── tool_executor.py    # 工具执行器
├── plugins/                # 插件系统
│   ├── commands/           # 插件命令
│   ├── core/               # 插件核心
│   ├── hooks/              # 插件钩子
│   ├── lsp/                # LSP 客户端
│   └── ...
├── services/               # 核心服务
│   ├── adaptive_context_manager.py  # 自适应上下文
│   ├── advanced_code_analyzer.py    # AST 代码分析
│   ├── codebase_indexer.py          # 代码库索引
│   ├── code_index.py                # 符号索引
│   ├── embedding_service.py         # 向量嵌入服务
│   ├── file_metadata_cache.py       # 文件元数据缓存
│   ├── hierarchical_memory.py       # 分层内存
│   ├── mcp_client.py                # MCP 客户端
│   └── ...
├── state/                  # 状态管理
│   ├── app_state.py        # 应用状态
│   └── store.py            # Store 模式实现
├── tools/                  # 工具实现
│   ├── base.py             # 工具基类
│   ├── registry.py         # 工具注册
│   ├── bash_tool.py        # Bash 执行
│   ├── code_index_tool.py  # CodeIndex 工具
│   ├── code_search_tool.py # CodeSearch 工具
│   ├── file_read_tool.py   # 文件读取
│   ├── file_edit_tool.py   # 文件编辑
│   ├── grep_tool.py        # 文本搜索
│   └── ...
├── tui/                    # TUI v1
├── tui_v2/                 # TUI v2（增强版）
│   ├── app.py              # 应用主类
│   ├── components/         # UI 组件
│   ├── controller/         # 控制器
│   └── screens/            # 屏幕定义
├── types/                  # 类型定义
│   ├── base.py             # 基础类型
│   ├── command.py          # 命令类型
│   ├── message.py          # 消息类型
│   └── permissions.py      # 权限类型
├── utils/                  # 工具函数
│   ├── config.py           # 配置管理
│   ├── model_client.py     # 模型客户端
│   └── models_config.py    # 模型配置
├── cli.py                  # CLI 入口
├── main.py                 # 主模块
├── query_engine.py         # 查询引擎
└── version.py              # 版本信息
```

## 核心组件

### 1. Query Engine（查询引擎）

文件：`query_engine.py`

负责与 LLM 交互，管理对话历史，处理工具调用。

```python
class QueryEngine:
    async def submit_message(prompt: str) -> AsyncIterator[QueryResult]
    def add_tool_result(tool_use_id: str, content: str) -> None
    def count_tokens() -> int
```

### 2. Tool System（工具系统）

文件：`tools/base.py`, `tools/registry.py`

自注册的工具系统，支持异步执行、权限检查、并发控制。

```python
class Tool:
    name: str
    input_schema: BaseModel
    call: ToolCallFn
    is_read_only: Callable[[Input], bool]
    is_concurrency_safe: Callable[[Input], bool]
```

主要工具：
- **BashTool** - 执行 shell 命令
- **FileReadTool** - 读取文件
- **FileEditTool** - 编辑文件
- **GrepTool** - 文本搜索
- **CodeIndexTool** - 代码索引
- **CodeSearchTool** - 代码搜索
- **CodeContextTool** - 代码上下文

### 3. Code Indexing（代码索引）

文件：`services/codebase_indexer.py`, `services/code_index.py`

企业级代码索引系统：

- **符号提取**：类、函数、变量
- **语义搜索**：向量嵌入
- **多语言支持**：Python, C/C++, JS/TS, Go, Rust, Java

```python
class CodebaseIndexer:
    async def index_codebase() -> CodebaseStats
    async def search(query: SearchQuery) -> list[CodeSnippet]
    async def build_context(query: str) -> ContextWindow
```

### 4. Command System（命令系统）

文件：`commands/base.py`

斜杠命令注册和执行：

```python
@dataclass
class CommandHandler:
    name: str
    handler: Callable[..., Awaitable[str]]
    aliases: list[str]
```

主要命令：
- `/index` - 索引代码库
- `/search` - 搜索代码
- `/config` - 配置管理
- `/model` - 模型切换
- `/git` - Git 操作

### 5. TUI v2（终端界面）

文件：`tui_v2/`

基于 Textual 的增强终端界面：

```python
class EnhancedApp(App):
    # 主应用类
    
class SessionScreen(Screen):
    # 主会话屏幕
    
class TUIController:
    # 控制器，连接 TUI 和 QueryEngine
```

### 6. State Management（状态管理）

文件：`state/store.py`, `state/app_state.py`

Store 模式实现：

```python
class Store:
    def get_state() -> AppState
    def set_state(updater: Callable[[AppState], AppState]) -> None
    def subscribe(listener: Callable[[AppState], None]) -> Callable
```

### 7. Services（核心服务）

| 服务 | 文件 | 功能 |
|------|------|------|
| Adaptive Context Manager | `adaptive_context_manager.py` | 自适应上下文管理 |
| Advanced Code Analyzer | `advanced_code_analyzer.py` | AST 代码分析 |
| Codebase Indexer | `codebase_indexer.py` | 代码库索引和搜索 |
| Embedding Service | `embedding_service.py` | 向量嵌入和语义搜索 |
| File Metadata Cache | `file_metadata_cache.py` | 文件元数据 LRU 缓存 |
| MCP Client | `mcp_client.py` | MCP 协议客户端 |
| Tool Orchestrator | `tool_orchestrator.py` | 工具并发执行 |

## 数据流

```
用户输入
    ↓
TUI / CLI
    ↓
命令解析 (/command) 或 QueryEngine (自然语言)
    ↓
命令执行 / LLM 处理
    ↓
工具调用 (Tool System)
    ↓
代码索引 (Codebase Indexer) - 可选
    ↓
结果返回
    ↓
TUI 显示
```

## 关键技术决策

### 类型系统
- Pydantic 用于数据验证（等价于 TypeScript 的 Zod）
- Dataclasses 用于简单结构
- 全类型注解，兼容 mypy

### 并发
- `asyncio` 处理异步操作
- 工具并发执行（只读工具）
- 异步生成器用于流式响应

### 工具注册
- 自注册模式（import 时注册）
- 全局注册表
- 支持别名

### 错误处理
- 异常驱动（Pythonic）
- ToolResult 包含 error 字段用于优雅降级

## TypeScript 到 Python 映射

| TypeScript | Python |
|------------|--------|
| `type X = Y` | `TypeAlias = Y` |
| `interface X { }` | `class X(BaseModel)` |
| `Promise<T>` | `Awaitable[T]` |
| `async function` | `async def` |
| `Array<X>` | `list[X]` |
| `Record<K, V>` | `dict[K, V]` |
| React/Ink | Textual (TUI v2) |
| Zustand | Store 类 |

## 扩展点

### 添加新工具

1. 创建文件 `tools/my_tool.py`
2. 继承 `Tool` 基类
3. 使用 `@register_tool` 注册
4. 在 `tools/__init__.py` 导入

### 添加新命令

1. 创建文件 `commands/my_cmd.py`
2. 实现处理函数
3. 使用 `register_command()` 注册
4. 在 `commands/__init__.py` 导入

### 添加新服务

1. 创建文件 `services/my_service.py`
2. 实现服务类
3. 提供 `get_service()` 获取单例

## 相关文档

- [../commands/README.md](../commands/README.md) - 命令文档
- [../../CODE_INDEXING.md](../../CODE_INDEXING.md) - 代码索引详情
- [../features/](../features/) - 功能特性文档