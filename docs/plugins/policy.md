# Policy - 企业策略管理

策略模块允许组织定义和实施插件使用策略，控制哪些插件可以安装、哪些源可以信任等。

---

## 模块结构

```
src/pilotcode/plugins/policy/
├── __init__.py              # 模块导出
├── policy.py                # PolicyManager, PluginPolicy
├── enforcement.py           # 策略执行
└── audit.py                 # 审计日志
```

---

## PolicyManager

策略管理器加载和应用组织策略。

### 获取管理器

```python
from pilotcode.plugins.policy.policy import PolicyManager

# 自动搜索策略文件
manager = PolicyManager()

# 指定策略文件
manager = PolicyManager(policy_path=Path("/path/to/policy.json"))
```

### 策略文件搜索路径

按顺序搜索以下位置：

1. 指定的 `policy_path`
2. `.pilotcode/policy.json`
3. `.claude/policy.json`
4. `.config/pilotcode/policy.json`

### 检查策略

```python
# 检查市场
allowed, message = manager.check_marketplace("claude-plugins-official")
if not allowed:
    print(f"Marketplace blocked: {message}")

# 检查发布者
allowed, message = manager.check_publisher("anthropics")
if not allowed:
    print(f"Publisher blocked: {message}")

# 检查插件
allowed, message = manager.check_plugin("docker@claude-plugins-official")
if not allowed:
    print(f"Plugin blocked: {message}")

# 综合检查（安装前）
can_install, message = manager.can_install(
    plugin_id="docker@claude-plugins-official",
    publisher="anthropics",
    marketplace="claude-plugins-official"
)
print(f"Can install: {can_install}, {message}")
```

### 策略要求检查

```python
# 是否需要签名
if manager.requires_signature():
    print("All plugins must be signed")

# 是否需要可信发布者
if manager.requires_trusted_publisher():
    print("Only trusted publishers allowed")

# 是否需要审批
if manager.requires_approval("docker@claude-plugins-official"):
    print("Installation requires admin approval")

# 是否允许自动更新
if manager.can_auto_update("docker@claude-plugins-official", "claude-plugins-official"):
    print("Auto-update allowed")

# 是否需要审计
if manager.should_audit_installs():
    print("All installs will be audited")
```

### 策略摘要

```python
summary = manager.get_policy_summary()
print(summary)
```

输出：
```
Policy: company-policy
Version: 1.0
Description: Company plugin usage policy

Allowed Marketplaces: company-internal
Blocked Plugins: risky-plugin, untrusted-plugin

Requirements: Signatures required, Trusted publishers required
```

---

## PluginPolicy

策略配置数据结构。

### 创建策略

```python
from pilotcode.plugins.policy.policy import PluginPolicy, PolicyRule, PolicyScope, PolicyAction

policy = PluginPolicy(
    name="company-policy",
    version="1.0",
    description="Company plugin usage policy",
    
    # 允许/阻止列表
    allowed_marketplaces=["company-internal", "claude-plugins-official"],
    blocked_marketplaces=["untrusted-market"],
    allowed_publishers=["anthropics", "company-team"],
    blocked_publishers=["suspicious-dev"],
    allowed_plugins=["docker", "github"],
    blocked_plugins=["risky-plugin"],
    
    # 要求
    require_signatures=True,
    require_trusted_publishers=True,
    require_approval_for_install=True,
    
    # 自动更新
    auto_update_allowed=True,
    auto_update_sources=["company-internal"],
    
    # 审计
    audit_all_installs=True,
    audit_all_operations=False,
    
    # 自定义规则
    rules=[
        PolicyRule(
            name="block-experimental",
            description="Block experimental plugins",
            scope=PolicyScope.PLUGIN,
            pattern="*experimental*",
            action=PolicyAction.DENY,
            message="Experimental plugins are not allowed"
        ),
        PolicyRule(
            name="notify-admin",
            description="Notify on new publisher",
            scope=PolicyScope.PUBLISHER,
            pattern="*",
            action=PolicyAction.NOTIFY,
            message="New publisher detected"
        )
    ]
)
```

### 保存/加载策略

```python
# 保存
manager.save_policy(Path(".pilotcode/policy.json"))

# 策略文件格式
{
  "name": "company-policy",
  "version": "1.0",
  "description": "Company plugin usage policy",
  "allowed_marketplaces": ["company-internal"],
  "blocked_marketplaces": [],
  "allowed_publishers": ["anthropics"],
  "blocked_publishers": ["suspicious-dev"],
  "allowed_plugins": [],
  "blocked_plugins": ["risky-plugin"],
  "require_signatures": true,
  "require_trusted_publishers": true,
  "require_approval_for_install": true,
  "auto_update_allowed": true,
  "auto_update_sources": ["company-internal"],
  "audit_all_installs": true,
  "audit_all_operations": false,
  "rules": [
    {
      "name": "block-experimental",
      "description": "Block experimental plugins",
      "scope": "plugin",
      "pattern": "*experimental*",
      "action": "deny",
      "message": "Experimental plugins are not allowed"
    }
  ]
}
```

---

## 策略规则

### PolicyRule

```python
from pilotcode.plugins.policy.policy import PolicyRule, PolicyScope, PolicyAction

rule = PolicyRule(
    name="rule-name",
    description="What this rule does",
    scope=PolicyScope.PLUGIN,      # 规则适用范围
    pattern="*pattern*",            # Glob 匹配模式
    action=PolicyAction.DENY,       # 执行动作
    message="Optional message"      # 提示信息
)
```

### 策略范围 (PolicyScope)

| 范围 | 说明 | 匹配目标 |
|------|------|----------|
| `GLOBAL` | 全局 | 插件 ID |
| `MARKETPLACE` | 市场 | 市场名称 |
| `PLUGIN` | 插件 | 插件名称 |
| `PUBLISHER` | 发布者 | 发布者 ID |

### 策略动作 (PolicyAction)

| 动作 | 说明 |
|------|------|
| `ALLOW` | 允许 |
| `DENY` | 拒绝 |
| `REQUIRE_APPROVAL` | 需要审批 |
| `NOTIFY` | 允许但通知 |

### 匹配模式

使用 Glob 模式匹配：

```python
# 匹配所有
pattern="*"

# 匹配特定前缀
pattern="company-*"

# 匹配特定后缀
pattern="*-experimental"

# 匹配包含
pattern="*internal*"

# 精确匹配
pattern="exact-name"
```

---

## 策略示例

### 严格策略

```json
{
  "name": "strict-policy",
  "version": "1.0",
  "description": "Strict plugin policy",
  "allowed_marketplaces": ["company-internal"],
  "blocked_marketplaces": [],
  "allowed_publishers": [],
  "blocked_publishers": [],
  "allowed_plugins": ["docker", "kubernetes", "github"],
  "blocked_plugins": [],
  "require_signatures": true,
  "require_trusted_publishers": true,
  "require_approval_for_install": true,
  "auto_update_allowed": false,
  "audit_all_installs": true
}
```

特点：
- 只允许白名单插件
- 必须签名
- 必须可信发布者
- 需要审批
- 禁止自动更新

### 宽松策略

```json
{
  "name": "permissive-policy",
  "version": "1.0",
  "description": "Permissive plugin policy",
  "allowed_marketplaces": [],
  "blocked_marketplaces": ["untrusted-market"],
  "allowed_publishers": [],
  "blocked_publishers": ["known-malicious"],
  "allowed_plugins": [],
  "blocked_plugins": ["risky-plugin"],
  "require_signatures": false,
  "require_trusted_publishers": false,
  "require_approval_for_install": false,
  "auto_update_allowed": true,
  "audit_all_installs": true
}
```

特点：
- 黑名单模式
- 不强制签名
- 自动更新允许

### 分层策略

```json
{
  "name": "tiered-policy",
  "version": "1.0",
  "rules": [
    {
      "name": "official-auto",
      "scope": "marketplace",
      "pattern": "claude-plugins-official",
      "action": "allow"
    },
    {
      "name": "internal-auto",
      "scope": "marketplace",
      "pattern": "company-internal",
      "action": "allow"
    },
    {
      "name": "third-party-approval",
      "scope": "marketplace",
      "pattern": "*",
      "action": "require_approval"
    }
  ]
}
```

特点：
- 官方/内部市场：自动允许
- 其他市场：需要审批

---

## 集成到安装流程

```python
from pilotcode.plugins import get_plugin_manager
from pilotcode.plugins.policy.policy import PolicyManager

async def policy_aware_install(plugin_spec: str):
    manager = await get_plugin_manager()
    policy = PolicyManager()
    
    # 解析规格
    if "@" in plugin_spec:
        name, marketplace = plugin_spec.rsplit("@", 1)
    else:
        name, marketplace = plugin_spec, "unknown"
    
    # 检查策略
    can_install, message = policy.can_install(
        plugin_id=plugin_spec,
        publisher="unknown",  # 需要实际获取
        marketplace=marketplace
    )
    
    if not can_install:
        print(f"❌ Installation blocked: {message}")
        return None
    
    if message == "Requires approval":
        # 请求审批
        approved = await request_admin_approval(plugin_spec)
        if not approved:
            print("❌ Installation not approved")
            return None
    
    # 检查签名要求
    if policy.requires_signature():
        # 验证签名...
        pass
    
    # 安装
    plugin = await manager.install_plugin(plugin_spec)
    
    # 审计记录
    if policy.should_audit_installs():
        await audit_log.record("install", plugin_spec, success=True)
    
    return plugin

async def request_admin_approval(plugin_spec: str) -> bool:
    # 实现审批流程
    pass
```

---

## 审计日志

```python
from pilotcode.plugins.policy.audit import AuditLogger

logger = AuditLogger()

# 记录安装
await logger.record(
    action="install",
    plugin_id="docker@claude-plugins-official",
    user="developer",
    success=True,
    details={"version": "1.0.0"}
)

# 记录策略违规
await logger.record(
    action="policy_violation",
    plugin_id="risky-plugin",
    user="developer",
    success=False,
    details={"reason": "Blocked by policy", "rule": "blocked-plugins"}
)

# 查询日志
logs = await logger.query(
    action="install",
    start_time="2024-01-01",
    end_time="2024-12-31"
)
```

---

## 完整示例

```python
import asyncio
from pathlib import Path
from pilotcode.plugins.policy.policy import (
    PolicyManager, PluginPolicy, PolicyRule, 
    PolicyScope, PolicyAction
)

async def setup_policy():
    # 创建策略
    policy = PluginPolicy(
        name="dev-team-policy",
        version="1.0",
        description="Development team plugin policy",
        allowed_marketplaces=["claude-plugins-official", "company-internal"],
        blocked_plugins=["experimental-ai", "untested-tool"],
        require_signatures=True,
        require_trusted_publishers=False,
        audit_all_installs=True,
        rules=[
            PolicyRule(
                name="ai-tools-approval",
                description="AI-related tools require approval",
                scope=PolicyScope.PLUGIN,
                pattern="*ai*",
                action=PolicyAction.REQUIRE_APPROVAL,
                message="AI tools require manager approval"
            )
        ]
    )
    
    # 保存策略
    Path(".pilotcode").mkdir(exist_ok=True)
    with open(".pilotcode/policy.json", "w") as f:
        import json
        json.dump(policy.to_dict(), f, indent=2)
    
    # 加载并应用
    manager = PolicyManager()
    
    # 测试
    can_install, message = manager.check_plugin("docker@claude-plugins-official")
    print(f"Docker: {can_install}, {message}")
    
    can_install, message = manager.check_plugin("experimental-ai")
    print(f"Experimental AI: {can_install}, {message}")
    
    # 策略摘要
    print("\nPolicy Summary:")
    print(manager.get_policy_summary())

if __name__ == "__main__":
    asyncio.run(setup_policy())
```

---

## 相关文档

- [安全与信任](./security.md)
- [插件核心管理](./core.md)
