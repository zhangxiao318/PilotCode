# Reasoning Content 全链路利用

> **状态**: ✅ 已实现  
> **关联改进项**: 系统性改进计划 — 修复 `reasoning_content` 识别 bug + 5 个利用方案  
> **适用模型**: DeepSeek (native), Qwen3 (OpenAI-compatible), Anthropic Claude 3.7+ (extended thinking)

---

## 1. 背景与问题

DeepSeek、Qwen3、Claude 3.7+ 等模型支持 **thinking / reasoning** 模式：模型在输出最终回答前，先进行一段内部推理（reasoning_content / thinking blocks）。这段推理内容通常占 token 消耗的 **20–50%**，但传统 Agent 框架只将其视为"模型内部状态"——透传、显示、回传，**不做任何后处理**。

这导致三个浪费：
1. **Token 浪费**：问候、简单查询也触发 thinking，白白消耗 30% tokens
2. **错误浪费**：模型在 reasoning 中"想对了"但 tool call "做错了"（如说要改 A 文件实际改了 B），无人发现
3. **循环浪费**：模型在 reasoning 中反复"再试一次"，但工具级 doom loop 检测不到这种"思维层面的循环"

---

## 2. 核心设计

将 reasoning_content 从"被动透传"升级为**主动利用**：

```
┌─────────────────────────────────────────────────────────────────┐
│               Reasoning Content 全链路处理                        │
├─────────────────────────────────────────────────────────────────┤
│  生成前: enable_thinking 动态开关（省 token）                    │  方案1
├─────────────────────────────────────────────────────────────────┤
│  生成中: 流式捕获 → EventBus → UI 显示                          │  已有
├─────────────────────────────────────────────────────────────────┤
│  生成后:                                                        │
│    ├── Reasoning-Action 一致性检查（防漏改）                    │  方案2
│    ├── Reasoning Doom Loop 检测（思维级循环检测）               │  方案3
│    └── Reasoning Reflection（逻辑缺陷自检）                     │  方案5
├─────────────────────────────────────────────────────────────────┤
│  压缩时: Reasoning 摘要化（保留决策上下文，省空间）              │  方案4
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 五层利用方案详解

### 方案 1：Thinking Mode 动态切换（省 Token）

**问题**：简单问候也触发 thinking，消耗大量 reasoning tokens。

**方案**：`QueryEngineConfig.enable_thinking` 支持三种模式：
- `None`（默认）：自动判断
- `True`：强制开启
- `False`：强制关闭

**自动判断启发式**：
```python
def _should_enable_thinking(prompt: str) -> bool:
    # 禁用：greeting、短提示（<20 字符）
    if len(prompt.strip()) < 20 or is_greeting(prompt):
        return False
    # 启用：有文件修改、复杂关键词（bug/fix/refactor/设计/架构）
    if changed_files or has_complex_keyword(prompt):
        return True
    return False
```

**效果**：日常对话节省 **20–30% tokens**。

**文件**：`src/pilotcode/query_engine.py` (`_build_extra_body`, `_should_enable_thinking`)

---

### 方案 2：Reasoning-Action 一致性检查（防漏改）

**问题**：模型在 reasoning 中说"我要修改 A.py 和 B.py"，但实际 tool call 只修改了 A.py。

**方案**：正则提取 reasoning 中提及的文件路径，与实际 tool_calls 对比：

```python
def _check_reasoning_action_consistency(reasoning, tool_calls):
    intended = extract_file_mentions(reasoning)   # regex
    actual = extract_files_from_tool_calls(tool_calls)
    missed = intended - actual
    if missed:
        return f"You mentioned editing {missed} but didn't include them in tool calls."
```

**效果**：发现"想一套做一套"，阻止漏改。

**成本**：纯本地正则，**0 API 调用**。

**文件**：`src/pilotcode/query_engine.py` (`_check_reasoning_action_consistency`)

---

### 方案 3：Reasoning-based Doom Loop（思维级循环检测）

**问题**：模型在 reasoning 中反复说"让我再试一次"，但每次 tool call 不同，工具级 doom loop 检测不到。

**方案**：比较最近 3 轮 reasoning 内容的文本相似度：

```python
def _detect_reasoning_loop(reasoning_history):
    if similarity(history[-2], current) > 0.75 and \
       similarity(history[-1], current) > 0.75:
        return "Detected similar reasoning for 3 consecutive turns..."
```

**效果**：在思维层面提前检测循环，比工具级检测**更早一步**。

**成本**：SequenceMatcher 纯本地计算，**0 API 调用**。

**文件**：`src/pilotcode/query_engine.py` (`_detect_reasoning_loop`)

---

### 方案 4：Reasoning 摘要压缩（Compaction 优化）

**问题**：reasoning 内容通常几百~几千 tokens，在上下文压缩时未被特殊处理，占用大量窗口空间。

**方案**：在 compaction 时提取决策关键词句，将长 reasoning 替换为摘要：

```python
def compress_reasoning(reasoning: str, max_length=300) -> str:
    if len(reasoning) <= max_length:
        return reasoning
    key_lines = [l for l in lines
                 if any(kw in l.lower() for kw in DECISION_KEYWORDS)]
    if key_lines:
        return "[Thinking summary] " + " | ".join(key_lines[:5])
    return reasoning[:max_length] + "..."
```

**效果**：2000 token 的 reasoning → 200 token 摘要，保留决策上下文。

**集成点**：`compaction_manager.py`、`compaction_pipeline.py`、`intelligent_compact.py` 三处 AssistantMessage 处理。

**文件**：`src/pilotcode/utils/reasoning_compressor.py`

---

### 方案 5：Reasoning Reflection（零成本逻辑自检）

**问题**：模型在 reasoning 中犯了逻辑错误（猜测未验证、重复重试、未分析根因直接修复），但没有任何机制发现。

**方案**：纯本地启发式规则分析 reasoning 内容：

| 检测模式 | 触发条件 | 反馈 |
|---------|---------|------|
| **猜测无验证** | reasoning 含"猜测/大概/可能"但不含"验证/测试/确认" | "You made a guess but didn't plan to verify it." |
| **重试循环** | "再试/retry/again"出现 ≥3 次 | "You've retried N times. Consider a different strategy." |
| **未分析根因** | 含"fix/修复/修改"但不含"根因/原因/why/because" | "You jumped to a fix without analyzing the root cause." |

**效果**：让模型在下一轮看到自检反馈，自我纠正。

**成本**：纯本地字符串匹配，**0 API 调用**。

**文件**：`src/pilotcode/query_engine.py` (`_reflect_on_reasoning`)

---

## 4. Provider 支持矩阵

修复前，`supports_reasoning_content` 仅识别 DeepSeek，Anthropic/Qwen 的 reasoning 被静默丢弃。

| Provider | 原生字段 | 需回传 | 动态开关 | 支持状态 |
|----------|----------|--------|----------|----------|
| **DeepSeek** | `reasoning_content` | ✅ 必须 | ❌ 不可控 | ✅ 全利用 |
| **Qwen3** | `reasoning_content` | ❌ 不需要 | ✅ `enable_thinking` | ✅ 全利用 |
| **Anthropic** | `thinking` blocks | ❌ 不需要 | ⚠️ extended thinking | ✅ 全利用 |
| **OpenAI GPT** | 无 | — | — | ❌ 不适用 |

**修复**：`models.json` 中给 Qwen/Anthropic 添加 `reasoning_content_field: true`，`model_client.py` 中扩展识别逻辑。

---

## 5. 与弱模型代偿的关系

弱模型（7B–30B）在 reasoning 质量上尤其脆弱：
- **容易陷入循环**：模型小，推理深度不够，反复尝试相同思路
- **容易猜而不验**：缺乏自我怀疑能力，做出假设后不去验证
- **容易直接改**：不分析根因，看到报错就改表面

**本系统与弱模型代偿的协同**：

| 弱模型问题 | 弱模型代偿机制 | Reasoning 利用机制 |
|-----------|--------------|-------------------|
| 陷入循环 | 降低任务粒度、增加重试次数 | **方案3** 在思维级检测循环，提前终止 |
| 猜而不验 | 强化验证步骤（L1/L2/L3） | **方案5** 在 reasoning 阶段发现"无验证计划" |
| 直接改表面 | 代码审查 + 测试回环 | **方案2** 发现"想改A实际改B"的一致性偏差 |
| Token 消耗高 | 上下文压缩 | **方案4** 压缩 reasoning，**方案1** 减少不必要的 thinking |

> 弱模型代偿解决"模型能力不足时如何兜底"，Reasoning 利用解决"即使能力不足，也要在最早阶段发现和纠正"。两者互补，构成**事前预防 + 事后兜底**的完整闭环。

---

## 6. 快速参考

### 配置

```python
# QueryEngineConfig
enable_thinking: bool | None = None   # None=auto, True=force on, False=force off
```

### 测试

```bash
# 动态 thinking
pytest tests/unit/query/test_thinking_mode.py -v

# 一致性检查
pytest tests/unit/query/test_reasoning_action_consistency.py -v

# Doom loop
pytest tests/unit/query/test_reasoning_loop.py -v

# 摘要压缩
pytest tests/unit/utils/test_reasoning_compressor.py -v

# Reflection
pytest tests/unit/query/test_reasoning_reflection.py -v
```

---

## 7. 相关文档

- [弱模型多维代偿](./weak-model-compensation.md) — 框架级能力补偿
- [Reflection Mode](./reflection-mode.md) — 生成→审查→修改闭环（设计阶段）
