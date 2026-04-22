# /status 命令

显示 PilotCode 当前运行状态，包括 Git 状态、模型能力详情和会话 Token 使用量。

## 作用

- 查看当前工作目录和 Git 状态摘要
- 查看当前模型的能力配置（上下文窗口、工具支持等）
- 查看当前会话的消息数和 Token 使用量
- 可视化 Token 使用进度条，预警接近上限的情况

## 基本用法

```bash
/status
```

## 别名

| 别名 | 说明 |
|------|------|
| `/st` | `/status` 的简写 |

## 输出内容

```
PilotCode Status
========================================

Git:
  ## main...origin/main [ahead 2]
  M  src/pilotcode/cli.py
  ?? docs/commands/status.md

Working directory: /home/user/myproject
Time: 2026-04-22 09:35:00
Model: deepseek
  Context window: 128K
  Max output:     8K
  Tools:          Yes
  Vision:         No
Theme: default

Conversation Context:
  Messages:   12
  Tokens:     3240 / 128000 (2%)
  Remaining:  124760
  [░░░░░░░░░░░░░░░░░░░░] 2%
```

### 字段说明

| 区域 | 字段 | 说明 |
|------|------|------|
| **Git** | 状态行 | `git status -sb` 的前 5 行摘要 |
| **工作区** | `Working directory` | 当前工作目录 |
| | `Time` | 当前时间 |
| **模型** | `Model` | 当前模型标识名 |
| | `Context window` | 上下文窗口总大小 |
| | `Max output` | 单次最大输出 Token 数 |
| | `Tools` | 是否支持工具调用 |
| | `Vision` | 是否支持视觉输入 |
| | `Theme` | 当前主题 |
| **会话** | `Messages` | 当前会话消息数 |
| | `Tokens` | 已用 Token / 总限额 (百分比) |
| | `Remaining` | 剩余可用 Token |
| | 进度条 | 20 格可视化进度 |

### 使用预警

当 Token 使用量达到不同阈值时，会显示预警提示：

| 阈值 | 提示 | 说明 |
|------|------|------|
| ≥ 60% | `⚡ Above 60% — approaching limit` | 建议关注 |
| ≥ 80% | `⚠️  Above 80% — auto-compression active` | 自动压缩已触发 |

## 使用场景

### 场景1：检查是否会触发自动压缩

```bash
> /status
...
Conversation Context:
  Tokens:     102400 / 128000 (80%)
  [████████████████░░░░] 80%
  ⚠️  Above 80% — auto-compression active
```

当显示 80% 预警时，系统已自动或即将自动压缩历史消息以释放 Token 空间。

### 场景2：长会话监控

在长时间对话中定期执行 `/status`，观察 Token 增长趋势：

```bash
# 每 10-20 轮对话后检查一次
> /status
# 如果超过 60%，考虑手动 /compact
```

### 场景3：切换模型后验证

```bash
> /model set qwen-plus
> /status
# 确认 Context window 显示为 1M
```

## 注意事项

1. **Token 估算**：显示的 Token 数为估算值，实际 API 计数可能略有差异
2. **Git 信息**：仅在当前目录为 Git 仓库时显示 Git 状态
3. **实时刷新**：`/status` 为即时快照，不会自动刷新

## 相关命令

- `/model` - 查看和切换模型
- `/compact` - 手动压缩上下文
- `/new` - 开始新会话（清空历史）
