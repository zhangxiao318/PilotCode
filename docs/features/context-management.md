# 上下文窗口管理

PilotCode 的上下文窗口管理系统动态读取模型配置，自动监控 Token 使用量，并在必要时触发智能压缩，确保长会话不会超出模型的上下文限制。

---

## 上下文窗口的获取

### 静态配置

每个模型的上下文窗口大小定义在 `config/models.json` 中：

```json
{
  "models": {
    "deepseek": {
      "context_window": 128000,
      "max_tokens": 8192
    },
    "qwen": {
      "context_window": 256000,
      "max_tokens": 8192
    },
    "qwen-plus": {
      "context_window": 1000000,
      "max_tokens": 8192
    }
  }
}
```

系统启动时自动读取该文件，所有模块共用同一套上下文限制。

### 运行时探测（本地模型）

对于本地部署的模型（Ollama、llama.cpp、LiteLLM 等），PilotCode 会在启动时自动探测实际的上下文窗口：

| 后端 | 探测端点 | 说明 |
|------|----------|------|
| llama.cpp / llama-server | `/props` | 读取 `n_ctx` |
| Ollama | `/api/show` | 读取 `context_length` |
| LiteLLM | `/model/info` | 读取 `max_input_tokens` |
| OpenAI-compatible | `/v1/models` | 模型列表（无详细能力） |

探测按优先级依次尝试，成功获取 `context_window` 即停止。若探测失败，回退到 `config/models.json` 中的静态值。

### 验证当前配置

```bash
# 启动时自动验证
$ python3 -m pilotcode
✓ LLM ready: DeepSeek (深度求索)
   Model: deepseek-chat  Provider: deepseek  Context: 128K  Max tokens: 8K  Tools: ✓  Vision: ✗

# 运行时查看完整配置
$ python3 -m pilotcode config --list
Model Capability (Static Config):
  Display Name: DeepSeek (深度求索)
  Context window: 128K
  Max Tokens: 8K
  Tools: ✓
  Vision: ✗
```

---

## Token 使用量监控

### `/status` 命令

在对话过程中随时执行 `/status`（或简写 `/st`）查看当前 Token 使用情况：

```
> /status
PilotCode Status
========================================

Working directory: /home/user/myproject
Time: 2026-04-22 09:35:00
Model: deepseek
  Context window: 128K
  Max output:     8K
  Tools:          Yes
  Vision:         No

Conversation Context:
  Messages:   12
  Tokens:     3240 / 128000 (2%)
  Remaining:  124760
  [░░░░░░░░░░░░░░░░░░░░] 2%
```

### 输出字段说明

| 字段 | 说明 |
|------|------|
| `Messages` | 当前会话的消息数量 |
| `Tokens` | 已用 Token / 总限额 (百分比) |
| `Remaining` | 剩余可用 Token |
| 进度条 | 20 格可视化进度 |

### 使用预警

当使用量达到不同阈值时，`/status` 会显示预警：

| 阈值 | 提示 | 建议 |
|------|------|------|
| ≥ 60% | `⚡ Above 60% — approaching limit` | 关注 Token 增长趋势 |
| ≥ 80% | `⚠️  Above 80% — auto-compression active` | 自动压缩已触发 |

---

## 自动压缩机制

### 触发阈值

所有上下文管理模块统一采用 **80%** 作为自动压缩触发阈值：

| 模块 | 阈值来源 | 行为 |
|------|----------|------|
| `query_engine` | `get_model_context_window()` | 达到 80% 触发 `auto_compact_if_needed()` |
| `context_manager` | `ContextConfig.max_tokens` | 75% 警告，80% 触发 `auto_compact` |
| `intelligent_compact` | 运行时 `ctx * 0.80` | ClaudeCode 风格压缩 |
| `context_compression` | 运行时 `ctx * 0.70` | 摘要压缩的目标 Token 数 |
| `simple_cli` | `get_model_context_window()` | Token 使用量检查 |

这意味着：当你把 `context_window` 从 128K 改为 256K，所有模块的压缩阈值会自动同步调整，无需修改代码。

### 压缩策略

自动压缩时，系统会：

1. **保留系统消息** — 系统提示始终完整保留
2. **保留最近消息** — 默认保留最近 10 条消息的完整内容
3. **压缩早期消息** — 对较早的消息进行摘要或移除

压缩在后台自动进行，通常用户无感知。

> **注意**：系统内置了**压缩冷却机制**。每次成功压缩后会记录消息数量，如果后续消息数量没有增加，不会重复触发压缩。这避免了在 Token 数接近阈值时的频繁压缩抖动。

### 开启/关闭自动压缩

```bash
# 查看当前设置
> /config get auto_compact
auto_compact = True

# 关闭自动压缩
> /config set auto_compact false
Set auto_compact = False

# 或通过配置文件
{
  "auto_compact": true
}
```

---

## 手动压缩

### `/compact` 命令

在需要时手动触发上下文压缩，查看压缩前后的对比统计：

```
> /compact
Context compacted:
  Messages:  24 -> 10 (14 removed)
  Tokens:    89000 -> 42000 (47000 saved)
  Usage:     69% -> 32%
```

### 何时手动压缩

- 在进行重要任务前主动压缩，避免过程中因自动压缩打断思路
- `/status` 显示接近 80% 时，手动控制压缩时机
- 发现模型因上下文过长而响应变慢或质量下降时

### 压缩后仍不理想

```
> /compact
Context compacted:
  Messages:  50 -> 10 (40 removed)
  Tokens:    115000 -> 98000 (17000 saved)
  Usage:     89% -> 76%
  ⚠️  Still above 80% — may compress again soon
```

此时建议：
- 使用 `/new` 开始新会话（完全清空历史）
- 或精简当前问题的描述

---

## 开始新会话

### `/new` 命令

当压缩无法有效释放空间，或需要切换到完全不同的任务时，使用 `/new` 清空所有历史：

```
> /new
🆕 New conversation started. 15 previous message(s) cleared.
```

### `/new` vs `/compact`

| 命令 | 效果 | 适用场景 |
|------|------|----------|
| `/new` | **完全清空**所有历史消息 | 切换任务、释放全部空间 |
| `/compact` | **压缩保留**关键历史摘要 | 继续当前任务但释放 Token |

### 别名

- `/reset`
- `/clear-history`

---

## 上下文管理最佳实践

### 1. 定期监控

```bash
# 每 10-20 轮对话后检查一次
> /status
# 如果超过 60%，考虑手动 /compact
```

### 2. 根据任务选择合适模型

```bash
> /model
# 查看当前模型的 Context window
# 分析大型代码库时，确保使用了 qwen-plus (1M) 等长上下文模型
```

### 3. 重要会话先保存

```bash
# 在 /new 前保存重要对话
> /session save architecture_design

# 清空后开始新任务
> /new
```

### 4. 避免频繁触发压缩

如果经常需要手动压缩，考虑：
- 切换到更大上下文窗口的模型
- 精简每轮对话的内容
- 拆分复杂任务为多个独立会话

---

## 交互命令速查

| 命令 | 作用 |
|------|------|
| `/status` / `/st` | 查看 Token 使用量和模型信息 |
| `/compact` | 手动压缩上下文历史 |
| `/new` / `/reset` | 开始新会话（清空历史） |
| `/model` | 查看当前模型能力和所有可用模型 |
| `/config get auto_compact` | 查看自动压缩开关 |
| `/config set auto_compact false` | 关闭自动压缩 |

---

## 相关文档

- [模型系统](./model-system.md) — 如何修改 `config/models.json`
- [上下文管理](./context-management.md) — 压缩算法与 MemPO 记忆管理
- [会话管理](./session-management.md) — 保存和恢复会话
## 智能上下文压缩

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

## MemPO 上下文管理

基于 [MemPO: Self-Memory Policy Optimization for Long-Horizon Agents](https://arxiv.org/abs/2603.00680) 论文实现的智能上下文管理系统。

## 核心思想

MemPO 提出了一种新的长程Agent上下文管理方法：

1. **将Memory视为可训练的策略变量**：Memory不再是被动检索的静态存储，而是与任务目标共同优化的动态组件
2. **Memory-level优势估计**：通过评估Memory对任务成功的贡献来指导记忆保留
3. **端到端联合优化**：记忆管理与任务完成质量直接关联

## 实现模块

### 1. Memory Value Estimation (`memory_value.py`)

信息价值评分机制，评估每条消息的重要性：

```python
from pilotcode.services.memory_value import get_memory_value_estimator

estimator = get_memory_value_estimator()
score = estimator.estimate_value(
    message=msg,
    task_context="Implement JWT authentication",
    current_files=["src/auth.py"],
)

print(f"Total score: {score.total_score}")
print(f"Info density: {score.info_density}")
print(f"Task relevance: {score.task_relevance}")
print(f"Historical utility: {score.historical_utility}")
```

**评分维度**：
- **信息密度 (40%)**：技术关键词密度、文件引用、结构信息
- **任务相关性 (40%)**：关键词重叠、文件上下文匹配、意图对齐
- **历史效用 (20%)**：基于历史反馈的学习得分

### 2. Task-Aware Compression (`task_aware_compression.py`)

任务导向的压缩策略，智能选择保留哪些信息：

```python
from pilotcode.services.task_aware_compression import (
    TaskAwareCompressor, TaskContext, CompressionMode
)

compressor = TaskAwareCompressor()
task_context = TaskContext(
    description="Implement user authentication",
    current_files=["src/auth.py"],
    task_type="feature",
    complexity="medium",
)

result = compressor.compress_with_task_context(
    messages=messages,
    task_context=task_context,
    target_tokens=3000,
)

print(f"Retained: {result.retained_messages}/{result.original_messages}")
print(f"Value retention: {result.value_retention_rate:.1%}")
```

**特点**：
- 语义聚类确保信息多样性
- 基于价值评分的选择性保留
- 中等价值消息自动摘要
- 四种压缩模式（Light/Moderate/Aggressive/Emergency）

### 3. Compression Feedback Loop (`compression_feedback.py`)

压缩质量反馈机制，从任务结果中学习：

```python
from pilotcode.services.compression_feedback import (
    get_compression_feedback_loop, TaskOutcome
)

feedback = get_compression_feedback_loop()

# 记录压缩事件
event_id = feedback.record_compression(
    result=compression_result,
    task_description="Fix login bug",
)

# 任务完成后记录结果
feedback.record_outcome(event_id, TaskOutcome.SUCCESS)

# 获取推荐压缩模式
recommended = feedback.get_recommended_mode("Implement feature")
```

**功能**：
- 压缩-结果关联追踪
- 任务类型模式学习
- 压缩模式效果评估
- 持久化存储

### 4. Hierarchical Memory (`hierarchical_memory.py`)

分层记忆架构，三级记忆系统：

```python
from pilotcode.services.hierarchical_memory import get_hierarchical_memory

memory = get_hierarchical_memory()

# 开始会话
memory.start_episode()
memory.add_to_working(message)

# 结束会话，生成摘要
snapshot = memory.end_episode()

# 检索相关历史
context = memory.retrieve_context("authentication JWT", top_k=3)
prompt_addition = memory.format_context_for_prompt(context)
```

**三层架构**：
1. **Working Memory**：当前对话上下文
2. **Episodic Memory**：历史会话摘要
3. **Semantic Memory**：提取的知识片段

### 5. Adaptive Context Manager (`adaptive_context_manager.py`)

自适应上下文管理器，整合所有功能：

```python
from pilotcode.services.adaptive_context_manager import (
    AdaptiveContextManager, AdaptiveContextConfig
)

config = AdaptiveContextConfig(
    enable_value_estimation=True,
    enable_task_aware_compression=True,
    enable_feedback_learning=True,
    enable_hierarchical_memory=True,
)

manager = AdaptiveContextManager(config)

# 设置任务上下文
manager.set_task_context(
    description="Implement JWT authentication",
    task_type="feature",
    current_files=["src/auth.py"],
)

# 添加消息（自动触发智能压缩）
manager.add_message("user", "I need to implement login")

# 任务完成后记录结果
manager.record_task_outcome(success=True)

# 获取统计
stats = manager.get_adaptive_stats()
```

**自适应特性**：
- 根据任务复杂度动态调整token预算
- 自动检索相关历史上下文
- 基于反馈持续优化压缩策略
- 完整的学习闭环

## 使用示例

```python
from pilotcode.services import (
    get_adaptive_context_manager,
    AdaptiveContextConfig,
)

# 创建配置
config = AdaptiveContextConfig(
    simple_task_tokens=4000,
    medium_task_tokens=8000,
    complex_task_tokens=12000,
    feedback_storage_path="/path/to/feedback.json",
    memory_storage_path="/path/to/memory.json",
)

# 获取管理器
manager = get_adaptive_context_manager(config)

# 开始任务
manager.set_task_context(
    description="Fix authentication bug in login",
    task_type="debug",
    current_files=["src/auth.py", "src/models.py"],
)

# 对话过程中自动管理上下文
manager.add_message("user", "Users can't login")
manager.add_message("assistant", "Checking auth.py...")
# ... 更多消息

# 查看消息价值评分
scored_messages = manager.get_messages_with_scores()
for msg in scored_messages:
    if "value_score" in msg:
        print(f"[{msg['role']}] Score: {msg['value_score']['total']:.2f}")

# 任务完成，记录结果
manager.record_task_outcome(success=True)
```

## 性能优化效果

基于MemPO论文的关键发现：

1. **Token使用量减少67-73%**：通过智能压缩减少冗余信息
2. **任务成功率提升**：保留关键信息的同时减少干扰
3. **自适应学习**：随着使用次数增加，压缩质量持续提升

## 配置选项

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `simple_task_tokens` | 4000 | 简单任务token预算 |
| `medium_task_tokens` | 8000 | 中等任务token预算 |
| `complex_task_tokens` | 12000 | 复杂任务token预算 |
| `enable_value_estimation` | True | 启用价值评分 |
| `enable_task_aware_compression` | True | 启用任务感知压缩 |
| `enable_feedback_learning` | True | 启用反馈学习 |
| `enable_hierarchical_memory` | True | 启用分层记忆 |
| `value_retention_target` | 0.75 | 价值保留目标 |

## 参考

- MemPO Paper: https://arxiv.org/abs/2603.00680
- MemPO Code: https://github.com/TheNewBeeKing/MemPO

