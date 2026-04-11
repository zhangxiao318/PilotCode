# MemPO-Style Context Management for PilotCode

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
