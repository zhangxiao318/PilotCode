# 会话管理

PilotCode 的会话管理系统提供对话历史的持久化保存、启动恢复和增量存储，支持长期项目协作。

---

## 概述

会话管理使 AI 对话能够：
- **持久化保存** - 每次消息交换后自动保存，对话历史不丢失
- **启动恢复** - 通过 `--restore` 或 `--session` 参数恢复历史会话
- **cwd 同步** - 恢复时自动同步会话原来的工作目录
- **增量存储** - 只追加新消息，减少 SSD 写入量
- **滚动归档** - 自动删除旧数据段，控制磁盘占用

---

## 启动恢复流程

### 1. CLI 参数入口

```
cli.py  main()
    ├── --session  <session_id>   → session_options["session_id"] = sid
    └── --restore                 → session_options["restore"] = True
```

启动示例：
```bash
# 恢复指定 session
pilotcode --session sess_20260426_235000

# 自动恢复最近 session（先匹配 cwd，再全局 fallback）
pilotcode --restore
```

### 2. TUIController 初始化

```
TUIController.__init__(session_options)
    └── _init_session()
        ├── 若 session_options["session_id"] 存在
        │   → load_session(sid)
        │   → 成功: 恢复 messages + 同步 cwd
        │   → 失败: 打印警告，创建新 session
        ├── 若 session_options["restore"] = True
        │   → get_last_session(project_path=cwd)
        │   → 找不到 → get_last_session(project_path=None) 全局 fallback
        │   → load_session(last.session_id)
        │   → 成功: 恢复 messages + 同步 cwd
        │   → 失败: 打印警告，创建新 session
        └── 否则
            → 创建新 session（sess_YYYYMMDD_HHMMSS）
```

### 3. cwd 同步

恢复成功后，`_init_session()` 调用 `_update_session_cwd(restored_cwd)`：

```python
# 同步回三层，确保文件工具指向正确的项目目录
self.session_options["cwd"] = restored_cwd
self.query_engine.config.cwd = restored_cwd
self.set_app_state(lambda s: s.replace(cwd=restored_cwd))
```

---

## 增量存储架构（v2.0）

### 文件结构

```
~/.pilotcode/data/sessions/
├── sess_20260426_235000.index.json      # 段索引
├── sess_20260426_235000.meta.json       # 用户可见元数据
├── sess_20260426_235000.data.0.jsonl    # 数据段 0
└── sess_20260426_235000.data.1.jsonl    # 数据段 1（段 0 满后创建）
```

### 各文件职责

| 文件 | 内容 | 更新频率 |
|------|------|---------|
| `index.json` | 版本号、data_files 列表（文件名 + start_idx + count）、total_messages | 每次保存 |
| `meta.json` | name、project_path、message_count、summary、created_at、updated_at | 每次保存 |
| `data.*.jsonl` | 每行一个 message dict（JSON Lines 格式） | 增量追加 |

### 保存策略

#### 正常追加（最常见）

只写入新增的消息：

```
内存: [msg0, msg1, ..., msg49, msg50, msg51]
上次保存: 50 条
本次: 追加 msg50, msg51 到 data.0.jsonl
IO: 写 2 行
```

#### 段满滚动

单个段超过 `SEGMENT_MAX_MESSAGES`（默认 50）时：

```
data.0.jsonl: 50 条（已满）
→ 创建 data.1.jsonl
→ 写入新增消息
→ 若总段数 > MAX_SEGMENTS（2），删除最旧段
```

#### auto_compact 后 Rollover

`auto_compact` 删除了旧消息后，消息数减少：

```
内存: [msg0, msg1]（compact 后只剩 2 条）
上次保存: 100 条
检测: current_count < last_count → 触发 rollover
→ 删除所有旧 data 文件
→ 创建新的 data.0.jsonl，写入当前内存全部消息
→ 重写 index.json
```

### 消息序列化格式

每条消息是一个独立 JSON 对象，包含 `type` 字段用于区分：

```jsonl
{"type": "system", "content": "You are a helpful assistant.", "timestamp": "2026-04-26T23:52:47.379154"}
{"type": "user", "content": "Read file main.c", "timestamp": "2026-04-26T23:52:47.379154"}
{"type": "assistant", "content": "I'll read it.", "reasoning_content": null, "timestamp": "2026-04-26T23:52:47.379171"}
{"type": "tool_use", "tool_use_id": "toolu_01AbCdEf", "name": "FileRead", "input": {"file_path": "/home/lyr/GDSystem/main.c"}, "timestamp": "2026-04-26T23:52:48.123456"}
{"type": "tool_result", "tool_use_id": "toolu_01AbCdEf", "content": "int main() {...}", "is_error": false, "timestamp": "2026-04-26T23:52:48.234567"}
```

---

## 自动保存机制

### 触发时机

TUI 模式下，每次消息交换的 `finally` 块中调用：

```python
# session.py 的 submit_message / _run_pevr_mode 的 finally
if self.controller:
    self.controller._auto_save()
```

### _auto_save 实现

```python
def _auto_save(self) -> None:
    if not self._auto_save_enabled or not self.query_engine or not self._session_id:
        return
    persistence.save_session(
        session_id=self._session_id,
        messages=self.query_engine.messages,
        name=self._session_name,
        project_path=self.session_options.get("cwd", str(Path.cwd())),
    )
```

### 错误处理

`_auto_save` 的失败是静默的（`try/except: pass`），不阻断用户体验。

---

## 相关代码路径

```
src/pilotcode/
├── cli.py                              # --restore / --session 参数处理
├── tui_v2/
│   └── controller/
│       └── controller.py               # _init_session() / _auto_save() / _update_session_cwd()
├── commands/
│   └── session_cmd.py                  # /session save / load / list / delete / rename
└── services/
    └── session_persistence.py          # SessionPersistence（增量存储核心）
```

### SessionPersistence 关键方法

| 方法 | 职责 |
|------|------|
| `save_session()` | 判断增量/rollover → 调用 `_append_messages()` 或 `_rollover()` |
| `load_session()` | 读 index → 遍历 data_files → 逐行解析 JSONL |
| `_append_messages()` | 追加新消息到当前段，段满创建新段 |
| `_rollover()` | 创建新段，写入全部消息，删除旧段 |
| `_prune_segments()` | 删除最旧段，保留最多 2 个 |
| `list_sessions()` | 扫描 `*.meta.json` |
| `delete_session()` | 删除 index + meta + 所有 data 段 |

---

## 使用示例

### 启动恢复

```bash
# 指定 session 恢复
pilotcode --session sess_20260426_235000

# 自动恢复最近 session
pilotcode --restore

# 正常启动（新 session）
pilotcode
```

### 运行时管理

```bash
# 列出所有会话（表格格式）
/session list

# 加载另一个会话到当前对话
/session load sess_20260426_235000

# 保存当前节点（使用当前 session ID）
/session save checkpoint_after_refactor

# 删除旧会话
/session delete sess_20260426_130326
```

---

## 注意事项

1. **最多保留 2 个数据段**：更早的段会被自动删除。如需完整历史，使用 `/session export` 导出。
2. **auto_compact 触发 rollover**：compact 后下一次保存会全量重写，不是增量追加。
3. **进程重启后首次保存**：从 index 恢复 `last_saved_count`，继续增量，不会误触发 rollover。
4. **session ID 复用**：`/session save` 使用当前 session ID，不会创建新 ID。
5. **加载后 cwd 同步**：恢复时会将 session 的 `project_path` 同步到当前工作目录。

---

## 相关文档

- [会话命令](../commands/session.md) — 用户可见的命令参考
- [智能上下文压缩](./context-compaction.md) — auto_compact 机制
