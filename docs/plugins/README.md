# Plugins 插件系统

PilotCode 的插件系统提供了强大的扩展能力，允许第三方开发者和企业用户自定义和扩展功能。

---

## 概述

插件系统是 PilotCode 的扩展层，提供以下核心能力：

| 能力 | 说明 |
|------|------|
| **动态安装** | 从市场、GitHub 或本地安装插件 |
| **生命周期管理** | 安装、启用、禁用、卸载的完整流程 |
| **安全验证** | 签名验证、发布者信任、策略控制 |
| **钩子系统** | 介入核心功能的执行流程 |
| **LSP 集成** | 语言服务器协议支持 |
| **企业策略** | 组织级别的插件使用策略 |

---

## 架构组件

```
src/pilotcode/plugins/
├── __init__.py              # 插件系统入口
├── core/                    # 核心管理
│   ├── manager.py           # PluginManager
│   ├── types.py             # 类型定义
│   ├── config.py            # 配置管理
│   ├── marketplace.py       # 市场管理
│   ├── dependencies.py      # 依赖解析
│   ├── versioning.py        # 版本管理
│   └── autoupdate.py        # 自动更新
├── hooks/                   # 钩子系统
│   ├── manager.py           # HookManager
│   ├── types.py             # 钩子类型
│   ├── builtin.py           # 内置钩子
│   └── executor.py          # 执行器
├── loader/                  # 加载器
│   ├── commands.py          # 命令加载
│   └── skills.py            # Skill 加载
├── security/                # 安全
│   ├── trust.py             # 信任存储
│   ├── signature.py         # 签名管理
│   └── verification.py      # 验证
├── policy/                  # 策略
│   ├── policy.py            # 策略管理
│   ├── enforcement.py       # 执行
│   └── audit.py             # 审计
├── lsp/                     # LSP 支持
│   ├── manager.py           # LSPManager
│   ├── client.py            # LspClient
│   └── types.py             # LSP 类型
├── sources/                 # 插件源
│   ├── base.py              # 基础接口
│   └── github.py            # GitHub 源
├── commands/                # 插件命令
│   └── plugin_cmd.py        # /plugin 命令
└── ui/                      # UI 支持
    ├── formatter.py         # 格式化
    └── interactive.py       # 交互
```

---

## 子系统文档

| 文档 | 说明 | 关键类 |
|------|------|--------|
| [core.md](./core.md) | 插件核心管理 | `PluginManager`, `PluginManifest` |
| [hooks.md](./hooks.md) | 生命周期钩子系统 | `HookManager`, `HookType` |
| [loader.md](./loader.md) | 插件内容加载 | `SkillLoader`, `CommandLoader` |
| [security.md](./security.md) | 安全与信任管理 | `TrustStore`, `SignatureManager` |
| [lsp.md](./lsp.md) | 语言服务器集成 | `LSPManager`, `LspClient` |
| [policy.md](./policy.md) | 企业策略管理 | `PolicyManager`, `PluginPolicy` |
| [sources.md](./sources.md) | 插件源管理 | `PluginSource`, `GitHubSource` |
| [commands.md](./commands.md) | 插件管理命令 | `/plugin` 命令 |

---

## 快速开始

### 获取插件管理器

```python
from pilotcode.plugins import get_plugin_manager

manager = await get_plugin_manager()
```

### 安装插件

```python
# 从市场安装
plugin = await manager.install_plugin("docker@claude-plugins-official")

# 从 GitHub 安装
plugin = await manager.install_plugin("my-plugin@github-user/repo")

# 强制重新安装
plugin = await manager.install_plugin("docker", force=True)
```

### 列出已安装插件

```python
result = await manager.load_plugins()

for plugin in result.enabled:
    print(f"✓ {plugin.name}")

for plugin in result.disabled:
    print(f"○ {plugin.name} (disabled)")
```

### 启用/禁用插件

```python
await manager.enable_plugin("docker@claude-plugins-official")
await manager.disable_plugin("docker@claude-plugins-official")
```

### 卸载插件

```python
await manager.uninstall_plugin("docker@claude-plugins-official")
```

---

## 使用命令行

### 查看已安装插件

```
/plugin list
```

输出：
```
Installed Plugins:

Enabled:
  ✓ docker (claude-plugins-official)
    Docker integration for container management
  ✓ github (claude-plugins-official)
    GitHub PR and issue management

Disabled:
  ○ kubernetes (claude-plugins-official)
```

### 安装插件

```
/plugin install docker@claude-plugins-official
```

### 搜索插件

```
/plugin search git
```

### 更新市场

```
/plugin update
```

### 检查插件更新

```
/plugin update check
```

---

## 插件结构

一个典型的插件目录结构：

```
my-plugin/
├── plugin.json              # 插件配置
├── commands/                # 斜杠命令
│   └── my-cmd.md
├── skills/                  # Skills
│   └── my-skill.md
├── agents/                  # Agents
│   └── my-agent.json
├── hooks.json               # 钩子配置
└── lsp-servers.json         # LSP 服务器配置
```

### plugin.json 示例

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "My awesome plugin",
  "author": {
    "name": "Developer Name",
    "email": "dev@example.com"
  },
  "dependencies": ["other-plugin>=1.0"],
  "commands": "commands",
  "skills": "skills",
  "hooks": "hooks.json",
  "mcpServers": {
    "my-server": {
      "command": "node",
      "args": ["server.js"]
    }
  }
}
```

---

## 钩子类型

插件可以通过钩子介入系统行为：

| 钩子类型 | 触发时机 | 用途 |
|----------|----------|------|
| `PreToolUse` | Tool 执行前 | 修改输入、权限检查 |
| `PostToolUse` | Tool 执行后 | 记录日志、修改输出 |
| `SessionStart` | 会话开始时 | 初始化、欢迎消息 |
| `UserPromptSubmit` | 用户提交提示时 | 预处理、注入上下文 |
| `PermissionRequest` | 请求权限时 | 自定义权限策略 |

---

## 安全特性

### 信任级别

| 级别 | 说明 | 自动更新 |
|------|------|----------|
| `OFFICIAL` | 官方/精选 | ✅ |
| `TRUSTED` | 明确信任 | ✅ |
| `VERIFIED` | 已验证身份 | ❌ |
| `UNTRUSTED` | 未知 | ❌ |
| `BLOCKED` | 已阻止 | ❌ |

### 签名验证

```python
from pilotcode.plugins.security import SignatureManager

sig_manager = SignatureManager()

# 创建签名（插件作者）
signature = sig_manager.create_signature(
    plugin_path,
    plugin_name="my-plugin",
    plugin_version="1.0.0",
    signer="my-key",
    private_key=key
)

# 验证签名（安装时）
is_valid = sig_manager.verify_signature(
    plugin_path,
    signature,
    public_key=key
)
```

---

## 企业策略

组织可以通过策略文件控制插件使用：

```json
{
  "name": "company-policy",
  "version": "1.0",
  "allowed_marketplaces": ["company-internal"],
  "blocked_plugins": ["risky-plugin"],
  "require_signatures": true,
  "require_trusted_publishers": true,
  "audit_all_installs": true
}
```

保存到 `.pilotcode/policy.json` 即可生效。

---

## 开发插件

参见 [插件开发指南](../development/plugin-development.md)

---

## 相关文档

- [Tools、Commands、Plugins 对比](../architecture/tools-commands-plugins.md)
- [架构设计](../architecture/ARCHITECTURE.md)
- [开发指南](../development/README.md)
