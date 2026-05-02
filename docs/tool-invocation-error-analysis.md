# 工具调用解析与 "Read not found" 错误根因分析

## 概述

本文档追溯 PilotCode 中工具调用（Tool Call）从 LLM 响应到最终执行的完整代码路径，重点分析 **"Read not found"** 错误的生成原因，以及为何该错误未被优雅处理。

---

## 1. 完整调用链路

```
LLM 返回 tool_call (name="Read", arguments={...})
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ ① query_engine.py: submit_message()                            │
│    解析 stream/XML，输出 ToolUseMessage(name="Read", ...)       │
│    → yield QueryResult(message=tool_use_msg)                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ ② repl.py: process_response()                                  │
│    for tool_msg in pending_tools:                              │
│        exec_result = await self.tool_executor                  │
│            .execute_tool_by_name(                               │
│                tool_msg.name,  # "Read"                         │
│                tool_msg.input,                                  │
│                context                                         │
│            )                                                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ ③ permissions/tool_executor.py: execute_tool_by_name()          │
│                                                                 │
│    all_tools = get_all_tools()                                  │
│    for t in all_tools:                                          │
│        if t.name == tool_name or tool_name in t.aliases:        │
│            tool = t  # ← 这里是大小写敏感的精确匹配              │
│            break                                                │
│                                                                 │
│    if tool is None:                                             │
│        return ToolExecutionResult(                               │
│            success=False,                                       │
│            permission_granted=False,   ← ⚠️ 问题点!              │
│            message=f"Tool 'Read' not found"                     │
│        )                                                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ ④ repl.py: process_response() — 错误处理                        │
│                                                                 │
│    if not exec_result.permission_granted:                       │
│        self.query_engine.add_tool_result(                       │
│            tool_msg.tool_use_id,                                │
│            "Tool execution denied by user",  ← ⚠️ 错误消息      │
│            is_error=True,                                       │
│        )                                                        │
│        self._render_system("permission_denied")                 │
│        permission_denied = True                                 │
│        break  ← ⚠️ 直接终止整个轮次!                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 两个独立的工具查找点

系统中存在 **两处** 独立的工具查找逻辑，行为不完全一致：

### 查找点 A：`permissions/tool_executor.py:235-252`（REPL/TUI 使用）

```python
async def execute_tool_by_name(self, tool_name, tool_input, context, ...):
    all_tools = get_all_tools()
    tool = None
    for t in all_tools:
        if t.name == tool_name or tool_name in t.aliases:
            tool = t
            break

    if tool is None:
        return ToolExecutionResult(
            success=False,
            permission_granted=False,        # ← 将"未找到"伪装成"权限拒绝"
            message=f"Tool '{tool_name}' not found",
        )
```

### 查找点 B：`services/tool_orchestrator.py:70-75, 190-194`（编排器使用）

```python
# analyze_batch() 中的行为:
def analyze_batch(self, tool_calls):
    for i, (name, input_data) in enumerate(tool_calls):
        tool = get_tool_by_name(name)
        if tool is None:
            continue  # ← 静默跳过！无任何反馈

# _execute_single() 中的行为:
async def _execute_single(self, exec_item, ...):
    tool = get_tool_by_name(exec_item.tool_name)
    if tool is None:
        exec_item.error = f"Tool {exec_item.tool_name} not found"
        return exec_item
```

### 底层注册表：`tools/registry.py:114-120`

```python
class ToolRegistry:
    def get(self, name: str) -> Tool | None:
        if name in self._tools:       # dict key 查找，大小写敏感
            return self._tools[name]
        if name in self._aliases:     # dict key 查找，大小写敏感
            return self._tools[self._aliases[name]]
        return None
```

**FileRead** 工具注册信息：
- `name = "FileRead"`
- `aliases = ["read", "cat", "view"]`（全小写）

---

## 3. "Read not found" 错误的三个根本原因

### 原因一：大小写敏感的精确匹配

| LLM 调用的名称 | 注册表中的名称 | 匹配结果 |
|---------------|---------------|---------|
| `FileRead` | `name="FileRead"` | ✅ 匹配 |
| `read` | `aliases=["read"]` | ✅ 匹配（alias） |
| `Read` | — | ❌ 不匹配 |
| `fileRead` | — | ❌ 不匹配 |
| `READ` | — | ❌ 不匹配 |
| `fileread` | — | ❌ 不匹配 |
| `ReadFile` | — | ❌ 不匹配 |

LLM 经常输出变体名称（如 `Read`、`ReadFile`），而这些都无法通过大小写敏感的精确匹配找到。

### 原因二：错误类别混淆 —— "未找到"被当作"权限拒绝"

在 `tool_executor.py:execute_tool_by_name()` 中，未找到工具时返回 `permission_granted=False`。在 `repl.py:process_response()` 中：

```python
if not exec_result.permission_granted:
    self.query_engine.add_tool_result(
        tool_msg.tool_use_id,
        "Tool execution denied by user",  # ← 错误消息！
        is_error=True,
    )
    self._render_system("permission_denied")
    permission_denied = True
    break  # ← 终止整个工具执行轮次！
```

**后果**：
1. LLM 收到的错误消息是 "Tool execution denied by user" 而非 "Tool 'Read' not found"
2. LLM 以为用户拒绝了操作，可能会不断请求权限或改变策略
3. 整个轮次被终止，后续合法工具调用也被丢弃

### 原因三：编排器的静默跳过

在 `tool_orchestrator.py:analyze_batch()` 中，未找到工具时直接 `continue`，不做任何记录或通知。这意味着：
- 工具调用在批量分析阶段就被丢弃
- 没有错误反馈给 LLM
- 调用的消费者可能只看到"没有结果"而不知道发生了什么

---

## 4. 错误恢复机制的缺失

### 4.1 错误分类器将其标记为"永久性"

`services/error_recovery.py:90`:
```python
# Permanent errors
if any(x in error_str for x in ["not found", "invalid", "bad request", "400", "404"]):
    return ErrorCategory.PERMANENT
```

"not found" 被分类为 `PERMANENT` 错误，因此重试处理器不会尝试重试。

### 4.2 无模糊匹配 / 建议机制

系统没有任何"你是不是想用 FileRead？"的提示机制。LLM 只能自己猜测正确的工具名称。

### 4.3 无降级策略

当 `FileEdit` 失败时，系统提示中有 `SmartEditPlanner` 作为降级方案。但当工具本身"未找到"时，没有任何降级路径。

---

## 5. 代码中所有失败点总结

| 文件 | 行号 | 失败点 | 影响 |
|------|------|--------|------|
| `permissions/tool_executor.py` | 251-256 | `tool is None` → `permission_granted=False` | 错误类别混淆，轮次终止 |
| `services/tool_orchestrator.py` | 74-75 | `tool is None` → `continue` | 静默跳过，无反馈 |
| `services/tool_orchestrator.py` | 192-194 | `tool is None` → `exec_item.error = ...` | 错误字符串，调用方可能忽略 |
| `tools/registry.py` | 117-119 | 精确 dict 查找 | 大小写变体无法匹配 |
| `repl.py` | ~310 | `not exec_result.permission_granted` | 将"未找到"等同于"权限拒绝" |

---

## 6. 推荐的修复方向

### 6.1 大小写不敏感的工具查找（最小改动）

在 `ToolRegistry.get()` 和 `execute_tool_by_name()` 中添加大小写不敏感的 fallback：

```python
def get(self, name: str) -> Tool | None:
    if name in self._tools:
        return self._tools[name]
    if name in self._aliases:
        return self._tools[self._aliases[name]]
    # Fallback: case-insensitive lookup
    lower_name = name.lower()
    for tool_name, tool in self._tools.items():
        if tool_name.lower() == lower_name:
            return tool
    for alias, tool_name in self._aliases.items():
        if alias.lower() == lower_name:
            return self._tools[tool_name]
    return None
```

### 6.2 区分 "未找到" 和 "权限拒绝"

在 `ToolExecutionResult` 中增加一个 `not_found: bool = False` 字段：

```python
if tool is None:
    return ToolExecutionResult(
        success=False,
        not_found=True,           # ← 明确标记
        permission_granted=True,  # ← 不再是 False
        message=f"Tool '{tool_name}' not found. Did you mean 'FileRead'?",
    )
```

REPL 中分别处理：

```python
if exec_result.not_found:
    # 向 LLM 反馈准确的错误信息，但继续执行其他工具
    self.query_engine.add_tool_result(
        tool_msg.tool_use_id,
        exec_result.message,
        is_error=True,
    )
    continue  # ← 不终止轮次
elif not exec_result.permission_granted:
    # 真正的权限拒绝
    ...
```

### 6.3 编排器中的反馈

在 `analyze_batch()` 中，不要静默跳过，而是为未找到的工具生成一个错误执行项：

```python
if tool is None:
    exec_item = ToolExecution(
        tool_name=name, tool_input=input_data, execution_id=f"exec_{i}"
    )
    exec_item.error = f"Tool '{name}' not found. Available: {suggestions}"
    exec_item.completed = True
    current_batch.append(exec_item)
    continue
```

---

## 7. 文件清单

分析涉及的核心文件：

| 文件 | 角色 |
|------|------|
| `src/pilotcode/tools/registry.py` | 工具注册表（name+alias 精确查找） |
| `src/pilotcode/tools/base.py` | Tool 基类定义 |
| `src/pilotcode/tools/file_read_tool.py` | FileRead 工具（name="FileRead", aliases=["read","cat","view"]） |
| `src/pilotcode/permissions/tool_executor.py` | 工具执行器（包含 execute_tool_by_name） |
| `src/pilotcode/services/tool_orchestrator.py` | 工具编排器（analyze_batch + _execute_single） |
| `src/pilotcode/components/repl.py` | REPL 主循环（process_response 中的错误处理） |
| `src/pilotcode/query_engine.py` | 查询引擎（submit_message 解析 LLM 响应） |
| `src/pilotcode/services/error_recovery.py` | 错误恢复（将 "not found" 分类为 PERMANENT） |
| `src/pilotcode/services/fileedit_compensation.py` | FileEdit 失败补偿（仅处理 FileEdit，不处理工具未找到） |
