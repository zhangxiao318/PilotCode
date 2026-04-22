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

- [模型配置与能力验证](./model-configuration.md) — 如何修改 `config/models.json`
- [智能上下文压缩](./context-compaction.md) — 压缩算法的详细机制
- [会话管理](./session-management.md) — 保存和恢复会话
