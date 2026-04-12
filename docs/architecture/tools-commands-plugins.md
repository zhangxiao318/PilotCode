# Tools、Commands 与 Plugins 对比分析

本文档详细对比分析 PilotCode 中三个核心组件：**Tools（工具）**、**Commands（命令）** 和 **Plugins（插件）**，帮助开发者理解它们的关系、差异和使用场景。

---

## 目录

1. [概述](#概述)
2. [架构层次](#架构层次)
3. [详细对比](#详细对比)
4. [关系图解](#关系图解)
5. [代码示例](#代码示例)
6. [使用场景决策](#使用场景决策)
7. [扩展机制](#扩展机制)

---

## 概述

| 组件 | 核心定位 | 主要使用者 | 加载方式 |
|------|----------|-----------|----------|
| **Tools** | 原子能力单元 | AI/LLM | 启动时加载，内置 |
| **Commands** | 用户交互接口 | 人类用户 | 启动时注册，内置 |
| **Plugins** | 功能扩展包 | 系统/用户 | 动态加载，可插拔 |

### 一句话概括

- **Tools**: LLM 可以调用的"原子能力"（如读取文件、执行命令）
- **Commands**: 用户输入的"斜杠命令"（如 `/index`、`/search`）
- **Plugins**: 可独立安装的功能"扩展包"（如 GitHub 集成、数据库支持）

---

## 架构层次

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 3: Plugins（插件层）- 可选扩展                                  │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Plugin: GitHub Integration                                  │    │
│  │  ├── Commands: /github, /pr, /issue                         │    │
│  │  └── Tools: CreatePRTool, MergeTool, IssueTool              │    │
│  └─────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Plugin: Database Support                                    │    │
│  │  ├── Commands: /db, /query, /migrate                        │    │
│  │  └── Tools: SQLQueryTool, DBConnectTool, SchemaTool         │    │
│  └─────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Plugin: Docker Integration                                  │    │
│  │  ├── Commands: /docker, /container                          │    │
│  │  └── Tools: DockerRunTool, DockerBuildTool                  │    │
│  └─────────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 2: Commands（命令层）- 用户界面                                 │
│                                                                     │
│   /index    /search    /config    /git    /help    /bash            │
│     ↓          ↓          ↓         ↓       ↓        ↓              │
│   代码索引    代码搜索    配置管理    Git操作   帮助    Shell         │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 1: Tools（工具层）- 原子能力                                    │
│                                                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ FileRead │ │   Bash   │ │   Grep   │ │ CodeSearch│ │ WebSearch│  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ FileEdit │ │  Glob    │ │ FetchURL │ │  Agent   │ │ CodeIndex│  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 详细对比

### 1. 基本属性对比

| 属性 | Tools | Commands | Plugins |
|------|-------|----------|---------|
| **定义** | 封装单一功能的可调用单元 | 用户输入的斜杠指令 | 功能扩展的容器 |
| **命名规范** | PascalCase（如 `BashTool`） | lowercase（如 `/index`） | kebab-case（如 `github-plugin`） |
| **代码位置** | `src/pilotcode/tools/*.py` | `src/pilotcode/commands/*.py` | `src/pilotcode/plugins/*/` |
| **配置方式** | Pydantic 输入/输出模型 | 参数解析器 | `plugin.json` 配置文件 |
| **调用方式** | LLM 自动选择 via `ToolUse` | 用户手动输入 `/command` | 隐式加载，显式调用 |

### 2. 技术特性对比

| 特性 | Tools | Commands | Plugins |
|------|-------|----------|---------|
| **Schema 约束** | ✅ 严格的输入/输出 Schema | ⚠️ 参数解析，较灵活 | ✅ 定义扩展点 |
| **类型安全** | ✅ Pydantic 验证 | ⚠️ 运行时解析 | ✅ 接口约束 |
| **并发支持** | ✅ 异步 `async def call()` | ✅ 异步处理器 | ✅ 支持异步初始化 |
| **错误处理** | 结构化错误返回 | 用户友好的错误消息 | 插件级错误隔离 |
| **权限控制** | `is_read_only` 标记 | 依赖底层 Tool | 插件级权限声明 |

### 3. 功能范围对比

| 范围 | Tools | Commands | Plugins |
|------|-------|----------|---------|
| **功能粒度** | 细粒度（单一功能） | 中等粒度（组合功能） | 粗粒度（完整功能集） |
| **职责范围** | 做一件事，做好 | 组织交互流程 | 封装完整领域功能 |
| **状态管理** | 无状态（纯函数） | 可访问会话状态 | 可维护持久状态 |
| **依赖关系** | 依赖 Core Services | 可调用多个 Tools | 可包含 Tools + Commands + Services |

### 4. 生命周期对比

```
Tools 生命周期:
启动 → 扫描 tools/ 目录 → 导入模块 → 注册到 ToolRegistry → 运行时通过名称调用

Commands 生命周期:
启动 → 扫描 commands/ 目录 → 导入模块 → 注册到 CommandRegistry → 用户输入时解析调用

Plugins 生命周期:
发现 → 加载 → 初始化 → 注册扩展点 → 启用 → 运行 → 禁用 → 卸载
    │       │        │         │          │
    ▼       ▼        ▼         ▼          ▼
  扫描    导入    执行      注册       激活
  目录    模块    __init__  Hooks      功能
```

### 5. 扩展性对比

| 扩展方式 | Tools | Commands | Plugins |
|----------|-------|----------|---------|
| **添加新功能** | 创建新 Tool 类 | 创建新 Command 处理器 | 创建新插件包 |
| **修改现有功能** | ❌ 不可修改（替换） | ❌ 不可修改（替换） | ✅ Hook 机制介入 |
| **第三方扩展** | ❌ 需修改核心代码 | ❌ 需修改核心代码 | ✅ 独立发布安装 |
| **热加载** | ❌ 需重启 | ❌ 需重启 | ✅ 支持动态加载 |

---

## 关系图解

### 包含关系

```
Plugins（容器）
    ├── Tools（0..n 个工具）
    │   ├── Tool A
    │   └── Tool B
    ├── Commands（0..n 个命令）
    │   ├── Command X
    │   └── Command Y
    ├── Hooks（0..n 个钩子）
    │   ├── on_startup
    │   └── on_shutdown
    └── Services（0..n 个服务）
        └── Service Z
```

### 调用关系

```
┌─────────────┐     调用      ┌─────────────┐     使用      ┌─────────────┐
│   用户输入   │ ───────────▶ │  Commands   │ ───────────▶ │    Tools    │
│   /index    │              │  命令处理器  │              │   原子能力   │
└─────────────┘              └─────────────┘              └─────────────┘
       │                            │                            │
       │                            │                            │
       ▼                            ▼                            ▼
┌─────────────┐              ┌─────────────┐              ┌─────────────┐
│  Plugin 可   │              │  Plugin 可   │              │  Plugin 可   │
│  扩展命令    │              │  扩展命令    │              │  扩展工具    │
└─────────────┘              └─────────────┘              └─────────────┘
```

### 与 LLM 的交互

```
┌─────────────────────────────────────────────────────────────────┐
│                          LLM / AI                               │
│  "帮我搜索代码中所有的 User 类定义"                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Tool Selection                             │
│  1. 分析意图 → 需要搜索代码                                        │
│  2. 选择工具 → CodeSearchTool                                    │
│  3. 构建输入 → {"query": "class User", "type": "class"}          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Tools 层                                 │
│              CodeSearchTool.call(input_data)                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Core Services                             │
│              实际执行代码搜索，访问代码索引                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 代码示例

### Tool 示例

```python
# src/pilotcode/tools/bash_tool.py
from pydantic import BaseModel
from typing import Literal

class BashInput(BaseModel):
    command: str
    timeout: int = 60
    description: str = "执行 bash 命令"

class BashOutput(BaseModel):
    stdout: str
    stderr: str
    exit_code: int

async def bash_call(input_data: BashInput) -> BashOutput:
    """Bash 工具的核心执行逻辑"""
    import subprocess
    result = subprocess.run(
        input_data.command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=input_data.timeout
    )
    return BashOutput(
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.returncode
    )

# 工具定义
BashTool = build_tool(
    name="Bash",
    input_schema=BashInput,
    output_schema=BashOutput,
    call=bash_call,
    aliases=["bash", "shell", "cmd"],
    is_read_only=lambda x: False,  # 会修改系统状态
)
```

### Command 示例

```python
# src/pilotcode/commands/index_cmd.py
from ..commands.base import CommandHandler, CommandContext

async def index_command_handler(args: list[str], context: CommandContext) -> str:
    """
    /index 命令处理器
    
    支持的子命令:
    - /index         - 增量索引
    - /index full    - 全量重建索引
    - /index stats   - 查看索引统计
    - /index clear   - 清除索引
    """
    from ..tools.code_index_tool import code_index_call, CodeIndexInput, IndexAction
    
    cmd = args[0] if args else "incremental"
    
    if cmd == "full":
        result = await code_index_call(CodeIndexInput(action=IndexAction.INDEX))
        return f"✅ 全量索引完成\n文件数: {result.total_files}\n符号数: {result.total_symbols}"
    
    elif cmd == "stats":
        result = await code_index_call(CodeIndexInput(action=IndexAction.STATS))
        return f"📊 索引统计\n文件数: {result.total_files}\n符号数: {result.total_symbols}"
    
    elif cmd == "clear":
        await code_index_call(CodeIndexInput(action=IndexAction.CLEAR))
        return "🗑️ 索引已清除"
    
    else:
        # 默认增量索引
        result = await code_index_call(CodeIndexInput(action=IndexAction.INDEX))
        return f"✅ 增量索引完成"

# 注册命令
register_command(CommandHandler(
    name="index",
    description="代码索引管理",
    handler=index_command_handler,
    aliases=["idx", "reindex"],
    help_text="使用 /index [full|stats|clear] 管理代码索引"
))
```

### Plugin 示例

```python
# src/pilotcode/plugins/github/__init__.py
"""
GitHub 集成插件

提供 GitHub 相关的命令和工具。
"""

from ..core import Plugin, PluginContext

class GitHubPlugin(Plugin):
    """GitHub 集成插件"""
    
    name = "github"
    version = "1.0.0"
    description = "GitHub 仓库管理和 PR 操作"
    
    def __init__(self):
        self.client = None
    
    async def initialize(self, context: PluginContext) -> bool:
        """插件初始化"""
        from .github_client import GitHubClient
        
        token = context.config.get("github.token")
        if not token:
            context.logger.warning("GitHub token 未配置")
            return False
        
        self.client = GitHubClient(token)
        await self.client.validate()
        
        # 注册工具
        context.tool_registry.register(CreatePRTool(self.client))
        context.tool_registry.register(MergePRTool(self.client))
        context.tool_registry.register(ListIssuesTool(self.client))
        
        # 注册命令
        context.command_registry.register(GitHubCommand(self.client))
        
        context.logger.info("GitHub 插件初始化完成")
        return True
    
    async def shutdown(self):
        """插件卸载"""
        if self.client:
            await self.client.close()

# plugin.json
{
    "name": "github",
    "version": "1.0.0",
    "description": "GitHub 集成插件",
    "entry": "__init__:GitHubPlugin",
    "dependencies": ["requests>=2.28.0"],
    "config_schema": {
        "github.token": {"type": "string", "required": true},
        "github.api_url": {"type": "string", "default": "https://api.github.com"}
    }
}
```

---

## 使用场景决策

### 决策流程图

```
需要添加新功能？
    │
    ├──► 是单一原子操作？（如读取文件、执行命令）
    │       │
    │       ├──► 是 → 创建 Tool
    │       │
    │       └──► 否 → 需要组合多个操作？
    │               │
    │               ├──► 是用户交互导向？（如 /index, /git）
    │               │       │
    │               │       ├──► 是 → 创建 Command
    │               │       │
    │               │       └──► 否 → 是完整功能集？
    │               │               │
    │               │               ├──► 是 → 创建 Plugin
    │               │               │
    │               │               └──► 否 → 考虑重构为 Tool
    │               │
    │               └──► 否 → 检查现有 Tool 是否可复用
    │
    └──► 修改现有功能？
            │
            ├──► 修改核心行为？ → 考虑 Hook 机制
            │
            └──► 添加新变体？ → 创建新 Tool/Command/Plugin
```

### 场景对照表

| 场景 | 推荐方案 | 示例 |
|------|----------|------|
| 读取项目文件 | **Tool** | `FileReadTool` |
| 执行 Shell 命令 | **Tool** | `BashTool` |
| 搜索代码符号 | **Tool** | `CodeSearchTool` |
| 代码索引管理 | **Command** | `/index` |
| Git 操作组合 | **Command** | `/git` |
| 配置管理 | **Command** | `/config` |
| GitHub PR 管理 | **Plugin** | GitHub 插件 |
| 数据库支持 | **Plugin** | Database 插件 |
| Docker 集成 | **Plugin** | Docker 插件 |
| 自定义工作流 | **Plugin** | Workflow 插件 |

---

## 扩展机制

### 1. Tool 扩展

```python
# 创建新 Tool 的步骤

# 1. 定义输入输出模型
class MyToolInput(BaseModel):
    param1: str
    param2: int = 10

class MyToolOutput(BaseModel):
    result: str
    status: Literal["success", "error"]

# 2. 实现调用函数
async def my_tool_call(input_data: MyToolInput) -> MyToolOutput:
    # 实现逻辑
    return MyToolOutput(result="done", status="success")

# 3. 构建 Tool
MyTool = build_tool(
    name="MyTool",
    input_schema=MyToolInput,
    output_schema=MyToolOutput,
    call=my_tool_call,
    aliases=["mytool", "mt"],
    is_read_only=True,
)

# 4. 自动注册（通过文件扫描）
# 文件放在 src/pilotcode/tools/my_tool.py
```

### 2. Command 扩展

```python
# 创建新 Command 的步骤

# 1. 实现处理器
async def my_command_handler(args: list[str], context: CommandContext) -> str:
    if not args:
        return "用法: /mycmd <action>"
    
    action = args[0]
    # 处理逻辑
    return f"执行了 {action}"

# 2. 注册命令
from ..commands.registry import register_command
from ..commands.base import CommandHandler

register_command(CommandHandler(
    name="mycmd",
    description="我的自定义命令",
    handler=my_command_handler,
    aliases=["mc"],
    help_text="/mycmd <action> - 执行自定义操作"
))

# 3. 文件放在 src/pilotcode/commands/my_cmd.py
```

### 3. Plugin 扩展

```python
# 创建新 Plugin 的步骤

# 1. 创建插件目录
# src/pilotcode/plugins/my_plugin/

# 2. 编写 plugin.json
{
    "name": "my-plugin",
    "version": "1.0.0",
    "description": "我的插件",
    "entry": "plugin:MyPlugin"
}

# 3. 实现插件类
from ..core import Plugin, PluginContext

class MyPlugin(Plugin):
    name = "my-plugin"
    
    async def initialize(self, context: PluginContext) -> bool:
        # 注册 Tools、Commands、Hooks
        context.tool_registry.register(MyTool())
        context.command_registry.register(MyCommand())
        context.hooks.register("on_file_save", self.on_save)
        return True
    
    async def shutdown(self):
        pass
    
    async def on_save(self, file_path: str):
        # Hook 处理
        pass

# 4. 插件自动加载
# 重启后系统扫描 plugins/ 目录自动加载
```

---

## 总结

| 维度 | Tools | Commands | Plugins |
|------|-------|----------|---------|
| **核心定位** | 原子能力 | 用户接口 | 扩展容器 |
| **使用对象** | AI/LLM | 人类用户 | 系统/开发者 |
| **复杂度** | 低（单一功能） | 中（流程组合） | 高（完整功能集） |
| **耦合度** | 松耦合 Core | 依赖 Tools | 可独立存在 |
| **扩展性** | 代码级扩展 | 代码级扩展 | 包级扩展 |
| **发布方式** | 核心版本 | 核心版本 | 独立发布 |
| **安装方式** | 随核心安装 | 随核心安装 | 可选安装 |

### 最佳实践

1. **Tools 设计原则**
   - 保持单一职责，一个 Tool 只做一件事
   - 输入/输出使用 Pydantic 模型保证类型安全
   - 正确处理错误，返回结构化错误信息
   - 标记 `is_read_only` 帮助 LLM 理解副作用

2. **Commands 设计原则**
   - 命令名称简洁明了（如 `/index` 而非 `/code_index`）
   - 提供清晰的帮助信息
   - 支持常用别名提升效率
   - 输出格式用户友好，支持 Markdown

3. **Plugins 设计原则**
   - 封装完整的功能领域
   - 提供清晰的配置 Schema
   - 优雅处理依赖缺失的情况
   - 使用 Hook 机制介入核心流程
   - 保持向后兼容性

---

## 相关文档

- [ARCHITECTURE.md](./ARCHITECTURE.md) - 整体架构设计
- [../tools/README.md](../tools/README.md) - 工具详细文档
- [../commands/README.md](../commands/README.md) - 命令详细文档
- [../plugins/README.md](../plugins/README.md) - 插件开发指南
