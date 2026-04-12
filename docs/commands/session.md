# /session 命令

会话管理命令，用于保存、加载和管理对话会话。

## 作用

- 保存当前对话会话
- 加载历史会话
- 列出所有会话
- 删除会话

## 基本用法

```bash
/session [subcommand]
```

## 子命令

| 子命令 | 说明 |
|--------|------|
| (无) | 显示当前会话信息 |
| `save [name]` | 保存当前会话 |
| `load <name>` | 加载会话 |
| `list` | 列出所有会话 |
| `delete <name>` | 删除会话 |

## 使用示例

### 查看当前会话

```bash
/session
```

输出：
```
Current session:
  ID: session_20240412_092503
  Started: 2026-04-12 09:25:03
  Messages: 42
  Tokens used: 15,234
```

### 保存会话

```bash
# 保存当前会话（自动生成名称）
/session save

# 保存并指定名称
/session save project_analysis

# 保存带有时间戳的名称
/session save bug_fix_$(date +%Y%m%d)
```

### 加载会话

```bash
# 加载指定会话
/session load project_analysis

# 加载后可以继续之前的对话
```

### 列出所有会话

```bash
/session list
```

输出示例：
```
Saved sessions:
  1. project_analysis    2026-04-11 18:30  56 msgs
  2. bug_fix_20240410    2026-04-10 14:20  23 msgs
  3. feature_design      2026-04-09 09:15  89 msgs
```

### 删除会话

```bash
/session delete old_session
```

## 使用场景

### 场景1：保存重要对话

```bash
# 完成一次复杂的架构设计讨论
/session save architecture_design_v2

# 退出
/quit

# 下次启动后可以恢复
/session load architecture_design_v2
```

### 场景2：多任务切换

```bash
# 任务A：Bug修复
/session load bug_fix_session
# ... 进行 bug 修复讨论

# 切换到任务B：新功能设计
/session load feature_design
# ... 进行功能设计讨论
```

### 场景3：定期保存

```bash
# 长时间工作时定期保存
/session save checkpoint_1
# ... 工作一段时间后
/session save checkpoint_2
```

## 会话文件位置

会话文件存储在：

```
~/.config/pilotcode/sessions/
```

## 注意事项

1. **自动保存**：可以配置自动保存会话
2. **会话大小**：大会话可能占用较多磁盘空间
3. **隐私**：会话文件包含完整的对话历史，注意隐私保护
4. **兼容性**：会话文件可能在不同版本间不兼容

## 相关命令

- `/clear` - 清屏（不影响会话）
- `/quit` - 退出（可配置自动保存）