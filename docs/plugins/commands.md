# Commands - 插件管理命令

插件管理命令提供用户界面，用于安装、管理、更新插件。

---

## 命令结构

```
src/pilotcode/plugins/commands/
└── plugin_cmd.py            # /plugin 命令实现
```

---

## /plugin 命令

主命令：`/plugin <subcommand> [args]`

### 子命令概览

| 子命令 | 说明 | 示例 |
|--------|------|------|
| `list` | 列出已安装插件 | `/plugin list` |
| `install` | 安装插件 | `/plugin install docker` |
| `uninstall` | 卸载插件 | `/plugin uninstall docker` |
| `enable` | 启用插件 | `/plugin enable docker` |
| `disable` | 禁用插件 | `/plugin disable docker` |
| `search` | 搜索插件 | `/plugin search git` |
| `marketplaces` | 列出市场 | `/plugin marketplaces` |
| `update` | 更新市场/插件 | `/plugin update` |
| `help` | 显示帮助 | `/plugin help` |

---

## 命令详解

### list - 列出插件

```
/plugin list
```

输出示例：
```
Installed Plugins:

Enabled:
  ✓ docker (claude-plugins-official)
    Docker integration for container management
  ✓ github (claude-plugins-official)
    GitHub PR and issue management

Disabled:
  ○ kubernetes (claude-plugins-official)
    Kubernetes cluster management

Errors:
  ! Failed to load old-plugin: Invalid manifest
```

### install - 安装插件

```
/plugin install <name[@marketplace]> [--force] [--scope user|project|local]
```

示例：
```
# 从指定市场安装
/plugin install docker@claude-plugins-official

# 自动搜索市场
/plugin install docker

# 强制重新安装
/plugin install docker --force

# 项目级安装
/plugin install docker --scope project
```

输出示例：
```
✓ Installed docker@claude-plugins-official
```

### uninstall - 卸载插件

```
/plugin uninstall <name[@marketplace]>
```

示例：
```
/plugin uninstall docker
/plugin uninstall docker@claude-plugins-official
```

别名：`/plugin remove`

### enable - 启用插件

```
/plugin enable <name[@marketplace]>
```

示例：
```
/plugin enable docker
```

输出：
```
✓ Enabled docker@claude-plugins-official
```

### disable - 禁用插件

```
/plugin disable <name[@marketplace]>
```

示例：
```
/plugin disable docker
```

输出：
```
✓ Disabled docker@claude-plugins-official
```

### search - 搜索插件

```
/plugin search <query>
```

示例：
```
/plugin search git
```

输出示例：
```
Search results for 'git':

  git@claude-plugins-official
    Git integration for repository operations
    Author: Anthropic

  github@claude-plugins-official
    GitHub PR and issue management
    Author: Anthropic

  gitlab@community-marketplace
    GitLab integration
    Author: Community
```

### marketplaces - 市场列表

```
/plugin marketplaces
```

输出示例：
```
Configured Marketplaces:

  claude-plugins-official
    Source: github
    Repo: anthropics/claude-code-plugins
    Last Updated: 2024-01-20
    Auto-update: True

  company-internal
    Source: directory
    Path: /company/marketplace
    Last Updated: 2024-01-15
    Auto-update: False
```

### update - 更新

#### 更新市场

```
/plugin update
```

输出：
```
Updating marketplaces...

  ✓ claude-plugins-official
  ✓ company-internal
```

#### 检查插件更新

```
/plugin update check
```

输出：
```
Checking for updates...

Marketplace updates:
  (Use '/plugin update' to refresh marketplaces)

Plugin updates:
  docker@claude-plugins-official: 1.0.0 → 1.1.0
  github@claude-plugins-official: 2.0.0 → 2.1.0
```

#### 更新插件

```
/plugin update plugins [name] [--all]
```

示例：
```
# 检查可用更新
/plugin update plugins

# 更新特定插件
/plugin update plugins docker

# 更新所有插件
/plugin update plugins --all
```

输出：
```
Checking for plugin updates...

Available updates:
  docker@claude-plugins-official: 1.0.0 → 1.1.0
  github@claude-plugins-official: 2.0.0 → 2.1.0

Run '/plugin update plugins <name>' to update a specific plugin.
Or run '/plugin update plugins --all' to update all.
```

### help - 帮助

```
/plugin help
```

输出：
```
Plugin management commands:

  /plugin list                    - List installed plugins
  /plugin install <name>          - Install a plugin
  /plugin uninstall <name>        - Uninstall a plugin
  /plugin enable <name>           - Enable a plugin
  /plugin disable <name>          - Disable a plugin
  /plugin search <query>          - Search for plugins
  /plugin marketplaces            - List configured marketplaces
  /plugin update                  - Update all marketplaces
  /plugin update plugins [name]   - Check/update plugins
  /plugin update check            - Check for all updates
  /plugin help                    - Show this help

Examples:
  /plugin install docker@claude-plugins-official
  /plugin enable docker
  /plugin search git
  /plugin update plugins          - Check for plugin updates
  /plugin update plugins --all    - Update all plugins
```

---

## 使用场景

### 首次安装插件

```
# 1. 搜索需要的插件
/plugin search docker

# 2. 安装
/plugin install docker@claude-plugins-official

# 3. 确认安装成功
/plugin list
```

### 更新所有插件

```
# 1. 更新市场信息
/plugin update

# 2. 检查可用更新
/plugin update check

# 3. 更新所有插件
/plugin update plugins --all
```

### 临时禁用插件

```
# 禁用
/plugin disable problematic-plugin

# 之后再启用
/plugin enable problematic-plugin
```

### 清理不用的插件

```
# 查看已安装
/plugin list

# 卸载不需要的
/plugin uninstall old-plugin
```

---

## 注册命令

命令在系统启动时自动注册：

```python
from pilotcode.plugins.commands.plugin_cmd import register_plugin_command

# 注册 /plugin 命令
register_plugin_command()
```

---

## 命令实现

### 处理器函数

```python
async def plugin_command(args: list[str], context: CommandContext) -> str:
    """Handle /plugin command."""
    if not args:
        return _help_text()
    
    subcommand = args[0].lower()
    sub_args = args[1:] if len(args) > 1 else []
    
    manager = await get_plugin_manager()
    
    handlers = {
        "list": _handle_list,
        "install": _handle_install,
        "uninstall": _handle_uninstall,
        "enable": _handle_enable,
        "disable": _handle_disable,
        "search": _handle_search,
        "marketplaces": _handle_marketplaces,
        "update": _handle_update,
        "help": _handle_help,
    }
    
    handler = handlers.get(subcommand)
    if handler:
        return await handler(sub_args, manager)
    
    return f"Unknown subcommand: {subcommand}\n\n{_help_text()}"
```

### 扩展命令

添加新的子命令：

```python
async def _handle_status(args: list[str], manager: PluginManager) -> str:
    """显示插件详细状态"""
    if not args:
        return "Usage: /plugin status <name>"
    
    plugin_name = args[0]
    plugin = manager.get_loaded_plugin(plugin_name)
    
    if not plugin:
        return f"Plugin not found: {plugin_name}"
    
    lines = [
        f"Plugin: {plugin.name}",
        f"Version: {plugin.manifest.version}",
        f"Source: {plugin.source}",
        f"Status: {'Enabled' if plugin.enabled else 'Disabled'}",
        f"Path: {plugin.path}",
    ]
    
    if plugin.manifest.description:
        lines.append(f"Description: {plugin.manifest.description}")
    
    if plugin.manifest.dependencies:
        lines.append(f"Dependencies: {', '.join(plugin.manifest.dependencies)}")
    
    return "\n".join(lines)

# 注册到 handlers
def plugin_command(args: list[str], context: CommandContext) -> str:
    handlers = {
        # ... existing handlers
        "status": _handle_status,
    }
    # ...
```

---

## 相关文档

- [插件核心管理](./core.md)
- [插件系统概述](./README.md)
