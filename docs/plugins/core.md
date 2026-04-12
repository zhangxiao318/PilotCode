# Core - 插件核心管理

`core` 模块提供插件系统的核心管理能力，包括插件的安装、加载、配置、市场、依赖、版本和自动更新等功能。

---

## 模块结构

```
src/pilotcode/plugins/core/
├── __init__.py              # 模块导出
├── manager.py               # PluginManager 主管理器
├── types.py                 # 类型定义
├── config.py                # 配置管理
├── marketplace.py           # 市场管理
├── dependencies.py          # 依赖解析
├── versioning.py            # 版本管理
└── autoupdate.py            # 自动更新
```

---

## PluginManager

插件管理器是插件系统的核心入口，提供完整的插件生命周期管理。

### 获取管理器

```python
from pilotcode.plugins import get_plugin_manager

manager = await get_plugin_manager()
```

### 主要方法

#### 安装插件

```python
async def install_plugin(
    self,
    plugin_spec: str,                    # 插件规格: "name@marketplace" 或 "name"
    scope: PluginScope = PluginScope.USER,
    force: bool = False
) -> LoadedPlugin
```

**示例：**

```python
# 从指定市场安装
plugin = await manager.install_plugin("docker@claude-plugins-official")

# 自动搜索市场安装
plugin = await manager.install_plugin("docker")

# 项目级安装
from pilotcode.plugins.core.types import PluginScope
plugin = await manager.install_plugin("docker", scope=PluginScope.PROJECT)

# 强制重新安装
plugin = await manager.install_plugin("docker", force=True)
```

#### 卸载插件

```python
async def uninstall_plugin(
    self,
    plugin_spec: str,
    scope: Optional[PluginScope] = None
) -> bool
```

**示例：**

```python
success = await manager.uninstall_plugin("docker@claude-plugins-official")
```

#### 启用/禁用插件

```python
async def enable_plugin(self, plugin_spec: str) -> bool
async def disable_plugin(self, plugin_spec: str) -> bool
```

**示例：**

```python
await manager.enable_plugin("docker@claude-plugins-official")
await manager.disable_plugin("docker@claude-plugins-official")
```

#### 加载所有插件

```python
async def load_plugins(self) -> PluginLoadResult
```

**示例：**

```python
result = await manager.load_plugins()

# 已启用的插件
for plugin in result.enabled:
    print(f"Enabled: {plugin.name}")

# 已禁用的插件
for plugin in result.disabled:
    print(f"Disabled: {plugin.name}")

# 加载错误
for error in result.errors:
    print(f"Error: {error}")
```

#### 依赖管理

```python
# 检查依赖
graph = await manager.check_dependencies("my-plugin", install_missing=True)

# 检查反向依赖（哪些插件依赖此插件）
dependents = manager.check_reverse_dependencies("base-plugin")

# 带依赖安装
plugin = await manager.install_with_dependencies("my-plugin")
```

#### 版本管理

```python
# 获取版本
version = manager.get_plugin_version("docker@claude-plugins-official")

# 检查更新
updates = await manager.check_for_updates()
# Returns: {"docker@claude-plugins-official": {"current": "1.0.0", "latest": "1.1.0"}}

# 更新插件
success = await manager.update_plugin("docker@claude-plugins-official")

# 版本比较
result = manager.compare_versions("1.0.0", "1.1.0")  # -1
```

#### 自动更新

```python
# 设置自动更新策略
from pilotcode.plugins.core.autoupdate import UpdatePolicy

manager.setup_auto_update(UpdatePolicy(
    auto_update=True,
    update_interval_hours=24,
    allowed_sources=["claude-plugins-official"]
))

# 启动后台检查
await manager.start_auto_update()

# 停止后台检查
await manager.stop_auto_update()

# 手动运行检查
updates = await manager.run_auto_update(dry_run=True)
```

#### 市场管理

```python
# 更新所有市场
results = await manager.update_marketplaces()

# 更新特定市场
success = await manager.update_marketplace("claude-plugins-official")

# 检查过时插件
outdated = await manager.check_outdated_plugins()
```

---

## 核心类型

### PluginScope

插件安装范围：

```python
from pilotcode.plugins.core.types import PluginScope

PluginScope.USER      # 用户级 (~/.config/pilotcode/plugins/)
PluginScope.PROJECT   # 项目级 (./.pilotcode/plugins/)
PluginScope.LOCAL     # 本地级 (./plugins/)
```

### PluginManifest

插件配置清单：

```python
from pilotcode.plugins.core.types import PluginManifest

manifest = PluginManifest(
    name="my-plugin",
    version="1.0.0",
    description="Plugin description",
    author=PluginAuthor(name="Developer", email="dev@example.com"),
    homepage="https://example.com",
    repository="https://github.com/user/repo",
    license="MIT",
    keywords=["docker", "container"],
    dependencies=["base-plugin>=1.0"],
    hooks="hooks.json",           # 或 HooksConfig 对象
    commands="commands",          # 或命令列表
    agents="agents",              # 或 agent 列表
    skills="skills",              # 或 skill 列表
    mcp_servers={                 # MCP 服务器配置
        "my-server": MCPServerConfig(
            command="node",
            args=["server.js"],
            env={"KEY": "value"}
        )
    }
)
```

### LoadedPlugin

已加载的插件实例：

```python
from pilotcode.plugins.core.types import LoadedPlugin

# 属性
plugin.name              # 插件名称
plugin.manifest          # PluginManifest
plugin.path              # 安装路径
plugin.source            # 来源市场
plugin.enabled           # 是否启用
plugin.scope             # 安装范围
plugin.installed_at      # 安装时间
plugin.commands_path     # 命令路径
plugin.skills_path       # Skills 路径
plugin.agents_path       # Agents 路径
plugin.hooks_config      # 钩子配置
plugin.mcp_servers       # MCP 服务器配置
```

### HooksConfig

钩子配置：

```python
from pilotcode.plugins.core.types import HooksConfig

hooks = HooksConfig(
    pre_tool_use=["validate_input"],
    post_tool_use=["log_usage"],
    session_start=["init_session"],
    user_prompt_submit=["preprocess"],
    permission_request=["check_policy"]
)
```

### SkillDefinition

Skill 定义：

```python
from pilotcode.plugins.core.types import SkillDefinition

skill = SkillDefinition(
    name="code-review",
    description="Review code for issues",
    aliases=["review", "cr"],
    when_to_use="When user asks for code review",
    argument_hint="<file_path>",
    allowed_tools=["Read", "Grep", "CodeSearch"],
    model="claude-3-5-sonnet",
    content="Please review the following code..."
)
```

### MCPServerConfig

MCP 服务器配置：

```python
from pilotcode.plugins.core.types import MCPServerConfig

server = MCPServerConfig(
    command="node",
    args=["server.js", "--port", "3000"],
    env={"API_KEY": "secret"},
    enabled=True
)
```

---

## 配置管理

### 配置文件位置

```
~/.config/pilotcode/
├── plugins/                 # 插件安装目录
│   ├── docker@claude-plugins-official/
│   └── github@claude-plugins-official/
├── settings.json            # 插件设置
├── installed.json           # 安装记录
└── marketplaces/            # 市场缓存
    └── claude-plugins-official.json
```

### 设置文件

```json
{
  "enabled_plugins": {
    "docker@claude-plugins-official": true,
    "github@claude-plugins-official": false
  },
  "auto_update": false,
  "default_marketplace": "claude-plugins-official"
}
```

### 安装记录

```json
[
  {
    "plugin_id": "docker@claude-plugins-official",
    "scope": "user",
    "install_path": "/home/user/.config/pilotcode/plugins/docker@claude-plugins-official",
    "version": "1.0.0",
    "installed_at": "2024-01-15T10:30:00"
  }
]
```

---

## 市场管理

### 市场配置

```python
from pilotcode.plugins.core.types import MarketplaceSource

# GitHub 市场
source = MarketplaceSource(
    source="github",
    repo="anthropics/claude-plugins",
    ref="main",
    path="marketplace.json"
)

# URL 市场
source = MarketplaceSource(
    source="url",
    url="https://example.com/marketplace.json"
)

# 本地目录
source = MarketplaceSource(
    source="directory",
    path="/path/to/marketplace"
)
```

### 市场文件格式

```json
{
  "name": "claude-plugins-official",
  "description": "Official Claude Code plugins",
  "version": "1.0.0",
  "owner": {
    "name": "Anthropic",
    "email": "support@anthropic.com"
  },
  "plugins": [
    {
      "name": "docker",
      "description": "Docker integration",
      "version": "1.0.0",
      "author": {
        "name": "Anthropic"
      },
      "source": "anthropics/claude-code-plugins/docker",
      "dependencies": [],
      "keywords": ["docker", "container"]
    }
  ]
}
```

---

## 依赖解析

### 依赖声明

在 `plugin.json` 中声明依赖：

```json
{
  "dependencies": [
    "base-plugin>=1.0.0",
    "utils-plugin~2.1.0",
    "optional-plugin?>=1.0"
  ]
}
```

### 版本约束

| 约束 | 含义 | 示例 |
|------|------|------|
| `>=1.0.0` | 大于等于 | `1.0.0`, `1.1.0`, `2.0.0` |
| `^1.0.0` | 兼容版本 | `1.0.0`, `1.1.0` (不含 `2.0.0`) |
| `~1.0.0` | 近似版本 | `1.0.0`, `1.0.1` (不含 `1.1.0`) |
| `?` 前缀 | 可选依赖 | 安装失败不中断 |

### 依赖图

```python
from pilotcode.plugins.core.dependencies import DependencyGraph

graph = await manager.check_dependencies("my-plugin")

# 检查冲突
errors = graph.validate()
for error in errors:
    print(f"Conflict: {error}")

# 获取安装顺序
order = graph.get_install_order()
```

---

## 自动更新

### 更新策略

```python
from pilotcode.plugins.core.autoupdate import UpdatePolicy

policy = UpdatePolicy(
    auto_update=True,                      # 启用自动更新
    update_interval_hours=24,              # 检查间隔
    allowed_sources=[                      # 允许自动更新的源
        "claude-plugins-official"
    ],
    blocked_plugins=[                      # 阻止自动更新的插件
        "critical-plugin"
    ],
    update_hook=None                       # 更新前钩子
)
```

### 更新检查

```python
# 检查所有插件
updates = await manager.check_for_updates()

# 结果格式
{
    "docker@claude-plugins-official": {
        "current": "1.0.0",
        "latest": "1.1.0",
        "changelog": "Added new features..."
    }
}
```

---

## 错误处理

```python
from pilotcode.plugins.core.manager import PluginError

try:
    plugin = await manager.install_plugin("unknown-plugin")
except PluginError as e:
    print(f"Installation failed: {e}")
```

常见错误：

| 错误 | 说明 |
|------|------|
| `Plugin not found` | 插件在市场不存在 |
| `Already installed` | 插件已安装（未使用 force） |
| `Download failed` | 下载失败 |
| `Invalid manifest` | plugin.json 格式错误 |
| `Dependency conflict` | 依赖冲突 |

---

## 完整示例

```python
import asyncio
from pilotcode.plugins import get_plugin_manager
from pilotcode.plugins.core.types import PluginScope

async def main():
    # 获取管理器
    manager = await get_plugin_manager()
    
    # 安装插件
    try:
        plugin = await manager.install_plugin(
            "docker@claude-plugins-official",
            scope=PluginScope.USER
        )
        print(f"Installed: {plugin.name} v{plugin.manifest.version}")
    except Exception as e:
        print(f"Install failed: {e}")
        return
    
    # 加载所有插件
    result = await manager.load_plugins()
    print(f"Enabled: {len(result.enabled)}")
    print(f"Disabled: {len(result.disabled)}")
    
    # 检查更新
    updates = await manager.check_for_updates()
    for plugin_id, info in updates.items():
        print(f"Update available: {plugin_id} {info['current']} → {info['latest']}")
    
    # 更新所有插件
    for plugin_id in updates:
        success = await manager.update_plugin(plugin_id)
        print(f"Updated {plugin_id}: {'success' if success else 'failed'}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 相关文档

- [Hooks 系统](./hooks.md)
- [插件加载器](./loader.md)
- [安全验证](./security.md)
- [插件命令](./commands.md)
