# /session 命令

会话管理命令，用于保存、加载和管理对话会话。

## 作用

- 保存当前对话会话
- 加载历史会话
- 列出所有会话
- 删除 / 重命名会话

## 基本用法

```bash
/session [subcommand]
```

## 子命令

| 子命令 | 说明 |
|--------|------|
| (无) / `list` | 以表格形式列出所有会话 |
| `save [name]` | 保存当前会话（覆盖已有） |
| `load <session_id>` | 加载会话到当前对话 |
| `delete <session_id>` | 删除会话 |
| `rename <session_id> <new_name>` | 重命名会话 |
| `info <session_id>` | 显示会话详情 |
| `export <session_id> <format> [path]` | 导出会话（json / markdown） |

## 使用示例

### 列出所有会话

```bash
/session list
```

输出：
```
Session ID             Messages Project Path                   Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
sess_20260427_112901         0  /home/lyr/GDSystem             Empty session
sess_20260427_112327         2  /home/lyr/GDSystem             创建一个C程序...
```

### 保存会话

```bash
# 保存当前会话（使用当前 session ID，不创建新文件）
/session save

# 保存并指定显示名称
/session save project_analysis
```

> 注意：`/session save` 使用**当前 session ID**（状态栏显示的 `sess_xxx`），不会生成新 ID。

### 加载会话

```bash
# 加载指定会话到当前对话
/session load sess_20260426_235000

# 加载后可以继续之前的对话
```

### 删除会话

```bash
/session delete sess_20260426_130326
```

## 自动保存

TUI 模式下每次消息交换后会在 `finally` 块中自动触发 `_auto_save()`，无需手动保存。

### 自动保存的行为

- **正常追加**：只写入新增的消息（增量追加到 `.jsonl`）
- **段满滚动**：单个数据文件超过 50 条消息后创建新段，旧段删除
- **compact 后重写**：`auto_compact` 删除了旧消息后，会做一次 **rollover**（全量写入新段，清除旧段）

## 会话文件位置

会话文件存储在：

```
~/.local/share/pilotcode/sessions/
```

### 文件结构（v2.0 增量格式）

每个会话由以下文件组成：

```
sess_20260426_235000.index.json      # 段索引：data 文件列表、消息范围
sess_20260426_235000.meta.json       # 用户可见元数据（名称、路径、摘要）
sess_20260426_235000.data.0.jsonl    # JSON Lines 数据段 0
sess_20260426_235000.data.1.jsonl    # 数据段 1（段 0 满后创建）
```

#### index.json 示例

```json
{
  "version": "2.0",
  "session_id": "sess_20260426_235000",
  "data_files": [
    {"file": "sess_20260426_235000.data.0.jsonl", "start_idx": 0, "count": 50},
    {"file": "sess_20260426_235000.data.1.jsonl", "start_idx": 50, "count": 30}
  ],
  "total_messages": 80
}
```

#### data.0.jsonl 示例

每行一个独立的消息对象：

```json
{"type": "user", "content": "分析 token 计算方法", "timestamp": "2026-04-26T23:52:47.379154"}
{"type": "assistant", "content": "Mission Complete...", "reasoning_content": null, "timestamp": "2026-04-26T23:52:47.379171"}
{"type": "tool_use", "tool_use_id": "toolu_01AbCdEf", "name": "FileRead", "input": {"file_path": "/home/lyr/GDSystem/main.c"}, "timestamp": "2026-04-26T23:52:48.123456"}
{"type": "tool_result", "tool_use_id": "toolu_01AbCdEf", "content": "int main() {...}", "is_error": false, "timestamp": "2026-04-26T23:52:48.234567"}
```

## 使用场景

### 场景1：跨天恢复工作

```bash
# 昨天的工作
# ... 讨论了一整天的架构设计 ...
# 自动保存已触发多次，session 在磁盘上

# 今天启动时恢复
pilotcode --restore
# 或
pilotcode --session sess_20260426_235000
```

### 场景2：多项目切换

```bash
# 项目 A：GDSystem C 项目
/session load sess_gdsystem_001

# 项目 B：PilotCode Python 项目
/session load sess_pilotcode_002
```

### 场景3：手动保存关键节点

```bash
# 完成需求分析后手动存一个检查点
/session save checkpoint_after_analysis

# 后续继续工作，自动保存仍然生效
```

## 注意事项

1. **自动保存默认开启**：可通过 `_auto_save_enabled = False` 关闭
2. **session ID 复用**：`/session save` 使用当前 session ID，不是创建新 session
3. **加载后 cwd 同步**：恢复会话时会同步会话原来的 `project_path` 到当前工作目录
4. **隐私**：会话文件包含完整对话历史，注意隐私保护
5. **最多保留 2 个数据段**：更早的段会被自动删除以节省磁盘空间

## 相关命令

- `/clear` - 清屏（不影响会话）
- `/quit` - 退出（自动保存仍然触发）
- `/compact` - 手动压缩上下文（会触发 rollover）
