# Hook 系统

PilotCode 的 Hook 系统允许在关键生命周期事件点插入自定义逻辑，实现扩展和定制。

---

## 概述

Hook 系统提供了一种事件驱动的扩展机制，允许插件和用户在特定时机：
- **拦截操作** - 阻止或修改即将执行的操作
- **记录日志** - 跟踪系统行为
- **增强功能** - 添加自定义验证或处理
- **集成外部** - 与外部系统联动

---

## 功能特性

### 支持的 Hook 类型

| Hook 类型 | 触发时机 | 典型用途 |
|-----------|----------|----------|
| **PreToolUse** | Tool 执行前 | 权限检查、输入验证、日志记录 |
| **PostToolUse** | Tool 执行成功 | 结果处理、缓存更新、日志记录 |
| **PostToolUseFailure** | Tool 执行失败 | 错误处理、重试逻辑、报警 |
| **SessionStart** | 会话开始时 | 初始化、欢迎消息、上下文设置 |
| **UserPromptSubmit** | 用户提交消息 | 提示预处理、敏感词过滤 |
| **PermissionRequest** | 请求权限时 | 自动审批策略、权限升级 |
| **PreAgentRun** | Agent 运行前 | Agent 参数调整、资源准备 |
| **PostAgentRun** | Agent 运行后 | 结果汇总、资源清理 |
| **OnError** | 发生错误时 | 错误分类、降级处理、报警 |

### Hook 能力

```python
# 控制执行
allow_execution: bool       # 是否允许继续执行
continue_after: bool        # 是否继续后续 hooks

# 修改数据
modified_input: dict        # 修改输入参数
modified_output: any        # 修改输出结果

# 添加信息
message: str                # 用户消息
system_message: str         # 系统消息
additional_context: str     # 额外上下文

# 权限决策
permission_decision: PermissionDecision  # 权限决策
```

---

## 相关代码

### 核心模块

```
src/pilotcode/
├── plugins/hooks/
│   ├── manager.py              # HookManager - Hook 注册和执行
│   ├── types.py                # HookType, HookContext, HookResult
│   ├── executor.py             # HookExecutor - 执行器
│   └── builtin.py              # 内置 Hooks
├── hooks/
│   └── builtin_hooks.py        # 更多内置 Hooks
└── permissions/
    └── tool_executor.py        # 集成 Hook 到 Tool 执行
```

### 关键类

```python
# Hook 类型枚举
class HookType(Enum):
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    POST_TOOL_USE_FAILURE = "PostToolUseFailure"
    SESSION_START = "SessionStart"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    PERMISSION_REQUEST = "PermissionRequest"
    PRE_AGENT_RUN = "PreAgentRun"
    POST_AGENT_RUN = "PostAgentRun"
    ON_ERROR = "OnError"

# Hook 上下文
@dataclass
class HookContext:
    hook_type: HookType
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None
    tool_output: Any = None
    tool_error: Optional[Exception] = None
    session_id: Optional[str] = None
    user_prompt: Optional[str] = None
    permission_type: Optional[str] = None
    metadata: dict = field(default_factory=dict)

# Hook 结果
@dataclass
class HookResult:
    allow_execution: bool = True
    continue_after: bool = True
    modified_input: Optional[dict] = None
    modified_output: Any = None
    message: Optional[str] = None
    system_message: Optional[str] = None
    permission_decision: Optional[PermissionDecision] = None
    additional_context: Optional[str] = None

# Hook 管理器
class HookManager:
    def register(
        self,
        hook_type: HookType,
        callback: HookCallback,
        priority: int = 0,
        timeout: Optional[float] = None,
        plugin_source: Optional[str] = None
    ) -> HookCallback
    
    def unregister(self, hook_type: HookType, callback: HookCallback) -> bool
    def execute_hooks(self, hook_type: HookType, context: HookContext) -> AggregatedHookResult
```

---

## 使用示例

### 注册 Hook

```python
from pilotcode.plugins.hooks import get_hook_manager
from pilotcode.plugins.hooks.types import HookType, HookContext, HookResult

manager = get_hook_manager()

# 方式 1: 装饰器
@manager.register(HookType.PRE_TOOL_USE, priority=100)
async def block_dangerous_commands(context: HookContext) -> HookResult:
    """阻止危险的 Bash 命令"""
    if context.tool_name == "Bash":
        command = context.tool_input.get("command", "")
        dangerous = ["rm -rf /", "dd if=/dev/zero", "> /dev/sda"]
        for pattern in dangerous:
            if pattern in command:
                return HookResult(
                    allow_execution=False,
                    message=f"⚠️ Dangerous command blocked: {pattern}",
                    stop_reason="security_policy"
                )
    return HookResult()

# 方式 2: 直接注册
async def log_tool_usage(context: HookContext) -> HookResult:
    print(f"[LOG] Tool: {context.tool_name}, Input: {context.tool_input}")
    return HookResult()

manager.register(HookType.POST_TOOL_USE, log_tool_usage, priority=10)
```

### 权限控制 Hook

```python
@manager.register(HookType.PERMISSION_REQUEST)
async def auto_approve_safe_operations(context: HookContext) -> HookResult:
    """自动允许安全的操作"""
    from pilotcode.plugins.hooks.types import PermissionDecision
    
    if context.permission_type == "file_read":
        # 自动允许读取非敏感文件
        return HookResult(
            permission_decision=PermissionDecision(
                behavior="allow",
                message="Auto-approved for read operations"
            )
        )
    
    return HookResult()
```

### Session 初始化 Hook

```python
@manager.register(HookType.SESSION_START)
async def init_session(context: HookContext) -> HookResult:
    """会话开始时初始化"""
    return HookResult(
        system_message="Session initialized with custom settings",
        additional_context="Project: PilotCode"
    )
```

---

## 与其他工具对比

| 特性 | PilotCode | Claude Code | VS Code 扩展 | Git Hooks |
|------|-----------|-------------|--------------|-----------|
| **Hook 类型** | 9种 | 15+ | 事件驱动 | 8种 |
| **执行控制** | ✅ 允许/阻止 | ✅ | ❌ | ❌ |
| **数据修改** | ✅ 输入/输出 | ✅ | 有限 | ❌ |
| **优先级** | ✅ | ✅ | ✅ | 顺序 |
| **超时控制** | ✅ | ❌ | ❌ | ❌ |
| **插件注册** | ✅ | ✅ | ✅ | ❌ |
| **异步支持** | ✅ | ✅ | ✅ | ❌ |

### 优势

1. **执行控制** - 可以真正阻止操作执行，不只是监听
2. **数据修改** - 可以修改输入输出，实现数据转换
3. **优先级** - 支持优先级排序，控制执行顺序
4. **超时控制** - 防止 Hook 执行过久阻塞系统

### 劣势

1. **Hook 数量** - 相比 Claude Code 原生支持较少
2. **生态** - 预构建的 Hook 插件较少

---

## 内置 Hooks

### LoggingHook

```python
# 自动记录所有 Tool 调用
@manager.register(HookType.PRE_TOOL_USE)
async def log_tool(context: HookContext) -> HookResult:
    logger.info(f"Tool: {context.tool_name}")
    return HookResult()
```

### CostTrackingHook

```python
# 跟踪 API 调用成本
@manager.register(HookType.POST_TOOL_USE)
async def track_cost(context: HookContext) -> HookResult:
    cost = estimate_cost(context.tool_name, context.tool_output)
    add_to_session_cost(cost)
    return HookResult()
```

### PermissionCheckHook

```python
# 权限检查
@manager.register(HookType.PERMISSION_REQUEST)
async def check_permission(context: HookContext) -> HookResult:
    if is_dangerous(context):
        return HookResult(allow_execution=False)
    return HookResult()
```

---

## 最佳实践

### 1. 合理设置优先级

```python
# 高优先级 - 安全检查（先执行）
@manager.register(HookType.PRE_TOOL_USE, priority=100)
async def security_check(context): ...

# 中优先级 - 日志记录
@manager.register(HookType.PRE_TOOL_USE, priority=50)
async def logging(context): ...

# 低优先级 - 指标收集（后执行）
@manager.register(HookType.PRE_TOOL_USE, priority=10)
async def metrics(context): ...
```

### 2. 快速失败

```python
# 好 - 快速返回
if context.tool_name != "Bash":
    return HookResult()  # 不相关，立即返回

# 不好 - 不必要的处理
result = HookResult()
if context.tool_name == "Bash":
    # 复杂处理
    ...
return result
```

### 3. 设置超时

```python
# 防止 Hook 阻塞
@manager.register(HookType.PRE_TOOL_USE, timeout=5.0)
async def slow_validation(context) -> HookResult:
    # 如果超过 5 秒，自动超时
    ...
```

### 4. 错误处理

```python
@manager.register(HookType.PRE_TOOL_USE)
async def safe_hook(context) -> HookResult:
    try:
        # 可能出错的操作
        risky_operation()
    except Exception as e:
        # 记录错误但允许执行
        logger.error(f"Hook error: {e}")
    return HookResult()
```

---

## 相关文档

- [插件 Hook 文档](../plugins/hooks.md)
- [权限系统](./permission-system.md)
