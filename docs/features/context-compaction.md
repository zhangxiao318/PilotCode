# 智能上下文压缩

PilotCode 的智能上下文压缩系统通过自动精简历史消息，解决长会话中的 Token 限制问题。

---

## 概述

在长时间的 AI 对话中，上下文历史会不断增长，导致：
- **Token 限制** - 超出 LLM 的最大上下文窗口
- **成本增加** - 更多的 Token 意味着更高的 API 费用
- **性能下降** - 处理大量上下文变慢

智能上下文压缩系统自动管理上下文长度，保持关键信息的同时移除冗余内容。

---

## 功能特性

### 三种压缩级别

| 级别 | 触发条件 | 行为 | 用户感知 |
|------|----------|------|----------|
| **微压缩** | Token 数 > 阈值的 50% | 清理旧的 Tool 结果 | 无 |
| **轻压缩** | Token 数 > 阈值的 75% | 摘要旧消息 | 轻微 |
| **完全压缩** | Token 数 > 阈值的 90% | 深度摘要，只保留关键决策 | 明显 |

### 压缩冷却机制

为防止压缩过于频繁，系统引入了**冷却机制**：

- 每次成功压缩后，记录当前消息数量 `_last_compaction_message_count`
- 后续调用 `auto_compact_if_needed()` 时，如果消息数量没有增加（`current_msg_count <= _last_compaction_message_count`），则**跳过压缩**
- 只有当新消息被添加到对话历史后，才可能再次触发压缩

这意味着：如果一次压缩后对话继续但 Token 数没有新增（或新增很少），系统不会重复压缩。冷却机制确保压缩只在"确实需要空间"时发生。

### 可压缩内容类型

```python
COMPRESSIBLE_TOOLS = [
    "FileRead",       # 文件内容可以摘要
    "Glob",           # 文件列表可以简化
    "Grep",           # 搜索结果可以摘要
    "WebSearch",      # 搜索结果可以摘要
    "Bash",           # 命令输出可以摘要
    "CodeSearch",     # 代码片段可以摘要
]

NON_COMPRESSIBLE_TOOLS = [
    "FileEdit",       # 编辑操作需要保留完整
    "AskUser",        # 用户交互需要保留
    "AgentTool",      # Agent 结果通常重要
]
```

### 结构化摘要格式

压缩后的消息使用统一的结构化格式：

```
[内容已压缩]

📋 摘要概览:
  • 文件读取: 15 个文件
  • 搜索操作: 8 次搜索
  • 代码分析: 完成

🔍 关键发现:
  • UserModel 在 src/models/user.py 定义
  • 认证逻辑在 src/auth/middleware.py
  • 发现 3 个潜在的 SQL 注入点

💡 重要决策:
  • 使用 JWT 进行认证
  • 选择 PostgreSQL 作为数据库

📁 涉及文件:
  • src/models/user.py
  • src/auth/middleware.py
  • src/api/routes.py
```

---

## 相关代码

### 核心模块

```
src/pilotcode/
├── services/
│   ├── hierarchical_memory.py    # 分层记忆系统
│   ├── intelligent_compactor.py  # 智能压缩引擎
│   └── context_manager.py        # 上下文管理
├── commands/
│   └── compact_cmd.py            # /compact 命令
└── hooks/
    └── compaction_hooks.py       # 压缩相关 Hooks
```

### 关键类

```python
# 智能压缩器
class IntelligentCompactor:
    def __init__(self):
        self.compression_threshold = 0.75  # 75% 触发压缩
        self.max_tokens = 128000          # 最大 Token 数
    
    async def compact(
        self,
        messages: List[Message],
        target_ratio: float = 0.5
    ) -> CompactionResult:
        """
        压缩消息列表
        
        Args:
            messages: 原始消息列表
            target_ratio: 目标压缩比例 (0.5 = 压缩到 50%)
        
        Returns:
            CompactionResult 包含压缩后的消息和统计信息
        """
        
    def should_compact(self, messages: List[Message]) -> bool:
        """检查是否需要压缩"""
        token_count = self.estimate_tokens(messages)
        return token_count > self.max_tokens * self.compression_threshold
    
    def micro_compact(self, messages: List[Message]) -> List[Message]:
        """微压缩 - 清理 Tool 结果"""
        # 移除旧的、不再引用的 Tool 结果
        ...
    
    def structured_compact(self, messages: List[Message]) -> List[Message]:
        """结构化压缩 - 生成摘要"""
        # 将相关操作分组并生成摘要
        ...

# 压缩结果
@dataclass
class CompactionResult:
    messages: List[Message]           # 压缩后的消息
    original_tokens: int              # 原始 Token 数
    compressed_tokens: int            # 压缩后 Token 数
    compression_ratio: float          # 压缩比例
    items_removed: int                # 移除的项目数
    items_summarized: int             # 摘要的项目数
```

---

## 使用示例

### 自动压缩

压缩在后台自动进行，用户无感知：

```python
# 当 Token 数超过阈值时自动触发
if compactor.should_compact(session.messages):
    result = await compactor.compact(session.messages)
    logger.info(f"Compressed: {result.original_tokens} → {result.compressed_tokens}")
```

### 手动压缩

```bash
# 查看当前 Token 使用
/cost

# 手动触发压缩
/compact

# 强制完全压缩
/compact --full
```

### 配置压缩参数

```python
# 在配置中调整压缩阈值
{
  "auto_compact": true,
  "compact_threshold": 0.8,      # 80% 时触发压缩
  "compact_target": 0.5          # 压缩到 50%
}
```

---

## 与其他工具对比

| 特性 | PilotCode | Claude Code | ChatGPT | 其他 CLI 工具 |
|------|-----------|-------------|---------|---------------|
| **自动压缩** | ✅ | ✅ | ✅ | ❌ |
| **结构化摘要** | ✅ | ✅ | ❌ | ❌ |
| **可压缩类型识别** | ✅ | ✅ | ❌ | ❌ |
| **用户控制** | ✅ 命令/配置 | ✅ | ❌ 自动 | N/A |
| **压缩级别** | 3级 | 3级 | 2级 | ❌ |
| **Token 估算** | ✅ | ✅ | ✅ | ❌ |
| **保留关键决策** | ✅ | ✅ | ❌ | ❌ |

### 优势

1. **细粒度控制** - 识别不同类型的可压缩内容
2. **结构化摘要** - 保留关键信息，易于理解
3. **用户可控** - 支持手动触发和配置调整
4. **透明度高** - 清晰显示压缩了哪些内容

### 劣势

1. **实现复杂** - 需要维护可压缩类型列表
2. **摘要质量** - 依赖 AI 生成摘要的质量

---

## 压缩策略

### 时间衰减

越久远的消息越容易被压缩：

```python
def compression_priority(message: Message, current_index: int) -> float:
    """
    计算消息的压缩优先级
    返回 0-1，越高越优先压缩
    """
    age = current_index - message.index
    base_priority = min(age / 10, 1.0)  # 越老优先级越高
    
    # 重要消息降低优先级
    if message.has_user_decision:
        base_priority *= 0.1
    if message.has_code_changes:
        base_priority *= 0.3
    
    return base_priority
```

### 重要性标记

某些消息被标记为重要，不会被压缩：

```python
IMPORTANT_PATTERNS = [
    r"批准了.*修改",      # 用户批准的修改
    r"重要决策",          # 明确标记的决策
    r"错误.*修复",        # 错误修复
    r"TODO.*完成",        # 完成的待办
]
```

---

## 最佳实践

### 1. 定期压缩

```bash
# 长时间会话后手动压缩
/compact

# 或在配置中启用自动压缩
{
  "auto_compact": true
}
```

### 2. 关键决策显式标记

```
用户: 这个方案很重要，请记住
AI: 已记录重要决策: 使用微服务架构

[这条消息会被标记为重要，不会被压缩]
```

### 3. 监控 Token 使用

```bash
/cost                    # 查看当前成本
/status                  # 查看系统状态，包括 Token 数
```

### 4. 合理设置阈值

```python
# 频繁触发压缩 - 保持高响应速度
"compact_threshold": 0.6

# 较少触发压缩 - 保留更多上下文
"compact_threshold": 0.85
```

---

## 相关文档

- [会话管理](./session-management.md)
- [成本统计命令](../commands/cost.md)
