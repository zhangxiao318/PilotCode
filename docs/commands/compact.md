# /compact 命令

手动压缩当前会话的上下文历史，释放 Token 空间并保留关键信息。

## 作用

- 手动触发上下文压缩（通常由系统在 80% 时自动触发）
- 查看压缩前后的消息数、Token 数和使用率对比
- 将会话维持在健康的 Token 预算内

## 基本用法

```bash
/compact
```

## 工作原理

`/compact` 使用智能压缩策略：

1. **保留系统消息**：系统提示始终保留
2. **保留最近消息**：默认保留最近 10 条消息完整内容
3. **压缩早期消息**：对较早的消息进行摘要压缩

## 使用示例

### 基本压缩

```bash
> /compact
```

输出示例：
```
Context compacted:
  Messages:  24 -> 10 (14 removed)
  Tokens:    89000 -> 42000 (47000 saved)
  Usage:     69% -> 32%
```

### 压缩后仍接近上限

```bash
> /compact
Context compacted:
  Messages:  50 -> 10 (40 removed)
  Tokens:    115000 -> 98000 (17000 saved)
  Usage:     89% -> 76%
  ⚠️  Still above 80% — may compress again soon
```

当压缩后仍然高于 80% 时，系统会提示可能很快再次触发压缩。此时建议：
- 使用 `/new` 开始新会话
- 或精简当前问题的描述

### 无需压缩时

```bash
> /compact
No compaction possible.
  Messages: 5 | Tokens: 1200/128000 (0%)
```

当消息数较少或低于阈值时，压缩不会被触发。

## 输出字段说明

| 字段 | 说明 |
|------|------|
| `Messages` | 压缩前消息数 → 压缩后消息数（移除数） |
| `Tokens` | 压缩前 Token 数 → 压缩后 Token 数（节省数） |
| `Usage` | 压缩前使用率 → 压缩后使用率 |

## 使用场景

### 场景1：主动压缩避免中断

在重要任务前主动压缩，避免对话过程中因自动压缩打断思路：

```bash
# 开始复杂任务前先压缩
> /compact
Context compacted: 45% -> 18%

# 现在可以安心进行多轮深入讨论
```

### 场景2：压缩后仍不理想

```bash
> /compact
Context compacted:
  Usage: 92% -> 85%
  ⚠️  Still above 80%

# 建议开始新会话
> /new
🆕 New conversation started. 10 previous message(s) cleared.
```

### 场景3：监控压缩效果

```bash
> /status
# 看到使用量 75%

> /compact
# 查看压缩节省了多少 Token

> /status
# 确认已回到安全范围
```

## 自动压缩与手动压缩

| 方式 | 触发条件 | 特点 |
|------|----------|------|
| **自动压缩** | Token 达到上下文窗口的 80% | 自动触发，无需干预 |
| **手动压缩** | 执行 `/compact` 命令 | 用户控制时机，可观察效果 |

## 注意事项

1. **不可逆**：压缩会合并或删除早期消息，无法撤销
2. **保留关键信息**：系统消息和最近消息通常会被保留
3. **与 `/new` 的区别**：`/compact` 保留压缩后的历史，`/new` 完全清空
4. **频繁压缩**：如果经常需要手动压缩，考虑提高上下文窗口或简化对话

## 相关命令

- `/status` - 查看当前 Token 使用量
- `/new` - 开始新会话（完全清空历史）
- `/model` - 切换到更大上下文窗口的模型
