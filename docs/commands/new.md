# /new 命令

开始一个新的对话会话，清空所有历史消息。

## 作用

- 清空当前会话的所有历史消息
- 重置压缩统计计数器
- 在不退出程序的情况下开始全新对话

## 基本用法

```bash
/new
```

## 别名

| 别名 | 说明 |
|------|------|
| `/reset` | 完全重置会话 |
| `/clear-history` | 清除历史记录 |

## 使用示例

### 开始新会话

```bash
> /new
🆕 New conversation started. 15 previous message(s) cleared.
```

### 使用别名

```bash
> /reset
🆕 New conversation started. 8 previous message(s) cleared.

> /clear-history
🆕 New conversation started. 3 previous message(s) cleared.
```

## 与 /compact 的区别

| 命令 | 效果 | 适用场景 |
|------|------|----------|
| `/new` | **完全清空**所有历史消息 | 切换任务、释放全部上下文空间 |
| `/compact` | **压缩保留**关键历史信息 | 继续当前任务但释放 Token 空间 |

## 使用场景

### 场景1：切换任务

完成一个任务后，切换到完全不同的新任务：

```bash
# 完成了架构设计讨论
"好的，这个微服务架构方案就确定下来了"

# 切换到另一个完全不相关的任务
> /new
🆕 New conversation started. 42 previous message(s) cleared.

# 开始新任务
"帮我写一个 Python 脚本处理 CSV 文件"
```

### 场景2：上下文溢出

当 `/compact` 压缩后仍然接近上限：

```bash
> /status
Conversation Context:
  Tokens: 110000 / 128000 (85%)

> /compact
Context compacted:
  Usage: 85% -> 82%
  ⚠️  Still above 80%

# 压缩效果不明显，直接开始新会话
> /new
🆕 New conversation started. 12 previous message(s) cleared.

> /status
Conversation Context:
  Tokens: 0 / 128000 (0%)
```

### 场景3：清除错误上下文

当模型因错误上下文产生幻觉或不相关回答时：

```bash
# 发现模型开始重复错误或偏离主题
> /new
🆕 New conversation started. 20 previous message(s) cleared.

# 用更清晰的问题重新开始
"请重新分析这个问题，关注以下要点：..."
```

## 注意事项

1. **不可恢复**：`/new` 会永久删除当前会话的所有历史消息（除非之前已保存）
2. **不退出程序**：与 `/quit` 不同，`/new` 保持程序运行，只是清空对话
3. **保留配置**：模型设置、主题等全局配置不受影响
4. **建议保存重要会话**：在 `/new` 之前，如有重要对话可使用 `/session save` 保存

## 最佳实践

```bash
# 1. 检查当前状态
> /status

# 2. 如有需要，保存重要会话
> /session save important_discussion

# 3. 开始新会话
> /new

# 4. 确认已清空
> /status
```

## 相关命令

- `/compact` - 压缩上下文（保留历史摘要）
- `/status` - 查看当前 Token 使用量
- `/session save` - 保存当前会话
- `/quit` - 退出程序
