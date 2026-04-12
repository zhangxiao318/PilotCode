# Hooks - 钩子系统

钩子系统允许插件介入 PilotCode 的核心执行流程，在特定事件发生时执行自定义逻辑。

---

## 概述

钩子（Hook）是一种事件订阅机制，允许插件：

- **拦截** 操作执行（如阻止某个 Tool 调用）
- **修改** 输入/输出数据
- **记录** 操作日志
- **注入** 额外上下文

---

## 架构

```
src/pilotcode/plugins/hooks/
├── __init__.py              # 模块导出
├── manager.py               # HookManager
├── types.py                 # 类型定义
├── builtin.py               # 内置钩子
└── executor.py              # 钩子执行器
```

---

## HookManager

钩子管理器负责注册和执行钩子。

### 获取管理器

```python
from pilotcode.plugins.hooks import get_hook_manager

manager = get_hook_manager()
```

### 注册钩子

```python
from pilotcode.plugins.hooks.types import HookType, HookContext, HookResult

# 方式 1: 使用装饰器
@manager.register(HookType.PRE_TOOL_USE, priority=10)
async def log_tool_use(context: HookContext) -> HookResult:
    print(f"Tool: {context.tool_name}")
    return HookResult()

# 方式 2: 直接注册
async def validate_input(context: HookContext) -> HookResult:
    if context.tool_name == "Bash":
        command = context.tool_input.get("command", "")
        if "rm -rf /" in command:
            return HookResult(
                allow_execution=False,
                message="Dangerous command blocked"
            )
    return HookResult()

manager.register(HookType.PRE_TOOL_USE, validate_input, priority=100)
```

### 注销钩子

```python
# 通过回调函数注销
manager.unregister(HookType.PRE_TOOL_USE, validate_input)

# 通过名称注销
manager.unregister_by_name(HookType.PRE_TOOL_USE, name="validate_input")

# 通过插件源注销
manager.unregister_by_name(plugin_source="my-plugin")

# 清除所有钩子
manager.clear(HookType.PRE_TOOL_USE)  # 清除特定类型
manager.clear()  # 清除所有
```

### 列出钩子

```python
# 获取所有钩子
all_hooks = manager.list_hooks()

# 获取特定类型的钩子
pre_hooks = manager.list_hooks(HookType.PRE_TOOL_USE)

# 获取执行优先级排序后的钩子
hooks = manager.get_hooks_for_type(HookType.PRE_TOOL_USE)
```

### 启用/禁用

```python
manager.enable()   # 启用钩子执行
manager.disable()  # 禁用钩子执行

if manager.is_enabled():
    print("Hooks are enabled")
```

---

## 钩子类型

### 工具执行钩子

```python
class HookType(Enum):
    PRE_TOOL_USE = "PreToolUse"           # Tool 执行前
    POST_TOOL_USE = "PostToolUse"         # Tool 执行后
    POST_TOOL_USE_FAILURE = "PostToolUseFailure"  # Tool 执行失败
```

**PreToolUse** - 在 Tool 执行前触发：

```python
@manager.register(HookType.PRE_TOOL_USE)
async def before_tool(context: HookContext) -> HookResult:
    # context.tool_name: Tool 名称
    # context.tool_input: Tool 输入参数
    
    # 修改输入
    return HookResult(
        modified_input={"command": "echo 'modified'"}
    )
    
    # 阻止执行
    return HookResult(
        allow_execution=False,
        message="Execution blocked by policy"
    )
```

**PostToolUse** - 在 Tool 执行成功后触发：

```python
@manager.register(HookType.POST_TOOL_USE)
async def after_tool(context: HookContext) -> HookResult:
    # context.tool_output: Tool 输出结果
    
    # 修改输出
    return HookResult(
        modified_output="Modified result"
    )
    
    # 添加上下文
    return HookResult(
        additional_context="Extra information"
    )
```

### 会话生命周期钩子

```python
class HookType(Enum):
    SESSION_START = "SessionStart"   # 会话开始
    SETUP = "Setup"                  # 系统初始化
```

**SessionStart** - 在会话开始时触发：

```python
@manager.register(HookType.SESSION_START)
async def on_session_start(context: HookContext) -> HookResult:
    print("New session started")
    return HookResult(
        message="Welcome! Plugin system ready."
    )
```

### 用户交互钩子

```python
class HookType(Enum):
    USER_PROMPT_SUBMIT = "UserPromptSubmit"     # 用户提交提示
    PERMISSION_REQUEST = "PermissionRequest"    # 请求权限
    PERMISSION_DENIED = "PermissionDenied"      # 权限被拒绝
```

**UserPromptSubmit** - 在用户提交提示时触发：

```python
@manager.register(HookType.USER_PROMPT_SUBMIT)
async def on_prompt(context: HookContext) -> HookResult:
    # context.user_prompt: 用户输入
    
    # 修改提示
    return HookResult(
        modified_input={"prompt": context.user_prompt + "\n\nBe concise."}
    )
```

**PermissionRequest** - 在请求权限时触发：

```python
@manager.register(HookType.PERMISSION_REQUEST)
async def on_permission(context: HookContext) -> HookResult:
    # context.permission_type: 权限类型
    
    from pilotcode.plugins.hooks.types import PermissionDecision
    
    # 自动允许特定权限
    if context.permission_type == "file_read":
        return HookResult(
            permission_decision=PermissionDecision(
                behavior="allow",
                message="Auto-allowed by policy"
            )
        )
    
    return HookResult()
```

### Agent 钩子

```python
class HookType(Enum):
    SUBAGENT_START = "SubagentStart"   # Subagent 启动
```

### 文件系统钩子

```python
class HookType(Enum):
    CWD_CHANGED = "CwdChanged"     # 工作目录改变
    FILE_CHANGED = "FileChanged"   # 文件改变
```

### 通知钩子

```python
class HookType(Enum):
    NOTIFICATION = "Notification"           # 收到通知
    ELICITATION = "Elicitation"             # 请求额外信息
    ELICITATION_RESULT = "ElicitationResult"  # 收到额外信息
```

---

## HookContext

钩子上下文包含当前执行环境的信息。

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class HookContext:
    hook_type: HookType           # 触发的钩子类型
    
    # Tool 信息
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None
    tool_output: Any = None
    tool_error: Optional[Exception] = None
    
    # 会话信息
    session_id: Optional[str] = None
    user_prompt: Optional[str] = None
    
    # Agent 信息
    agent_id: Optional[str] = None
    agent_prompt: Optional[str] = None
    
    # 文件信息
    file_path: Optional[str] = None
    cwd: Optional[str] = None
    
    # 权限信息
    permission_type: Optional[str] = None
    permission_result: Optional[PermissionDecision] = None
    
    # 额外上下文
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
```

**复制上下文：**

```python
# 创建上下文的副本（用于隔离修改）
new_context = context.copy()
```

---

## HookResult

钩子返回的结果，用于影响系统行为。

```python
from dataclasses import dataclass

@dataclass
class HookResult:
    # 执行控制
    allow_execution: bool = True        # 是否允许继续执行
    continue_after: bool = True         # 是否继续后续钩子
    
    # 修改数据
    modified_input: Optional[dict] = None   # 修改后的输入
    modified_output: Any = None             # 修改后的输出
    
    # 消息
    message: Optional[str] = None           # 用户消息
    system_message: Optional[str] = None    # 系统消息
    stop_reason: Optional[str] = None       # 停止原因
    
    # 权限决策
    permission_decision: Optional[PermissionDecision] = None
    
    # 额外上下文
    additional_context: Optional[str] = None
    
    # 错误处理
    retry: bool = False
    error: Optional[str] = None
```

### 常见返回模式

**允许执行（默认）：**

```python
return HookResult()
```

**阻止执行：**

```python
return HookResult(
    allow_execution=False,
    message="Blocked by security policy",
    stop_reason="security_policy"
)
```

**修改输入：**

```python
return HookResult(
    modified_input={"command": "safe-command"}
)
```

**修改输出：**

```python
return HookResult(
    modified_output={"result": "processed"}
)
```

**添加上下文：**

```python
return HookResult(
    additional_context="Additional information for LLM"
)
```

---

## AggregatedHookResult

多个钩子执行后的聚合结果。

```python
@dataclass
class AggregatedHookResult:
    allow_execution: bool = True
    continue_after: bool = True
    messages: list[str] = field(default_factory=list)
    system_messages: list[str] = field(default_factory=list)
    blocking_errors: list[str] = field(default_factory=list)
    modified_input: Optional[dict] = None
    modified_output: Any = None
    permission_decision: Optional[PermissionDecision] = None
    additional_contexts: list[str] = field(default_factory=list)
    stop_reason: Optional[str] = None
    retry: bool = False
```

**聚合逻辑：**

- `allow_execution`: 所有钩子的 AND 逻辑（任一个阻止则阻止）
- `retry`: 所有钩子的 OR 逻辑（任一个重试则重试）
- `modified_input`/`modified_output`: 最后一个非 None 的值
- `messages`/`system_messages`: 收集所有消息

---

## PermissionDecision

权限决策用于控制权限请求。

```python
@dataclass
class PermissionDecision:
    behavior: str                    # 'allow', 'deny', 'ask', 'passthrough'
    updated_input: Optional[dict] = None
    updated_permissions: Optional[list[dict]] = None
    message: Optional[str] = None
    interrupt: bool = False
```

**行为类型：**

| 行为 | 说明 |
|------|------|
| `allow` | 自动允许权限请求 |
| `deny` | 自动拒绝权限请求 |
| `ask` | 向用户询问 |
| `passthrough` | 不处理，传递给下一个钩子 |

---

## 便捷方法

HookManager 提供了便捷的专用方法：

```python
# PreToolUse
result = await manager.on_pre_tool_use(
    tool_name="Bash",
    tool_input={"command": "ls"}
)

# PostToolUse
result = await manager.on_post_tool_use(
    tool_name="Bash",
    tool_input={"command": "ls"},
    tool_output={"stdout": "file.txt"}
)

# SessionStart
result = await manager.on_session_start()

# UserPromptSubmit
result = await manager.on_user_prompt_submit(
    user_prompt="Hello"
)

# PermissionRequest
result = await manager.on_permission_request(
    permission_type="file_write"
)
```

---

## 优先级

钩子按优先级顺序执行（数值高的先执行）：

```python
# 高优先级（先执行）
@manager.register(HookType.PRE_TOOL_USE, priority=100)
async def security_check(context):
    ...

# 中优先级
@manager.register(HookType.PRE_TOOL_USE, priority=50)
async def logging(context):
    ...

# 低优先级（后执行）
@manager.register(HookType.PRE_TOOL_USE, priority=10)
async def metrics(context):
    ...
```

---

## 超时控制

为钩子设置执行超时：

```python
@manager.register(
    HookType.PRE_TOOL_USE,
    timeout=5.0  # 5 秒超时
)
async def slow_validation(context):
    ...
```

---

## 插件注册

插件应该在初始化时注册钩子：

```python
class MyPlugin:
    def __init__(self):
        self.hooks = []
    
    async def initialize(self, context):
        hook_manager = get_hook_manager()
        
        # 注册并保存引用
        @hook_manager.register(HookType.PRE_TOOL_USE, plugin_source="my-plugin")
        async def my_hook(hook_context):
            return HookResult()
        
        self.hooks.append(my_hook)
    
    async def shutdown(self):
        # 注销所有钩子
        hook_manager = get_hook_manager()
        hook_manager.unregister_by_name(plugin_source="my-plugin")
```

---

## 完整示例

### 输入验证钩子

```python
from pilotcode.plugins.hooks import get_hook_manager
from pilotcode.plugins.hooks.types import HookType, HookContext, HookResult

manager = get_hook_manager()

@manager.register(HookType.PRE_TOOL_USE, priority=100)
async def validate_bash(context: HookContext) -> HookResult:
    """验证 Bash 命令安全性"""
    if context.tool_name != "Bash":
        return HookResult()
    
    command = context.tool_input.get("command", "")
    
    # 危险命令列表
    dangerous = ["rm -rf /", "dd if=/dev/zero", "> /dev/sda"]
    
    for pattern in dangerous:
        if pattern in command:
            return HookResult(
                allow_execution=False,
                message=f"⚠️ Dangerous command detected: {pattern}",
                stop_reason="security_policy"
            )
    
    return HookResult()
```

### 输出处理钩子

```python
@manager.register(HookType.POST_TOOL_USE)
async def format_output(context: HookContext) -> HookResult:
    """格式化工具输出"""
    if context.tool_name != "Bash":
        return HookResult()
    
    output = context.tool_output
    if isinstance(output, dict) and "stdout" in output:
        # 添加行号
        lines = output["stdout"].split("\n")
        numbered = "\n".join(f"{i+1:3}: {line}" for i, line in enumerate(lines))
        output["stdout"] = numbered
        
        return HookResult(modified_output=output)
    
    return HookResult()
```

### 会话初始化钩子

```python
@manager.register(HookType.SESSION_START)
async def init_session(context: HookContext) -> HookResult:
    """会话初始化"""
    return HookResult(
        system_message="Session initialized. Plugins active: docker, github",
        additional_context="Current project: PilotCode"
    )
```

---

## 错误处理

```python
from pilotcode.plugins.hooks.types import HookError, HookTimeoutError

try:
    result = await manager.execute_hooks(HookType.PRE_TOOL_USE, context)
except HookTimeoutError:
    print("Hook execution timed out")
except HookError as e:
    print(f"Hook error: {e}")
```

---

## 相关文档

- [插件核心管理](./core.md)
- [插件加载器](./loader.md)
- [安全验证](./security.md)
