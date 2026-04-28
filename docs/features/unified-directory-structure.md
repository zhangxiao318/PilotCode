# 统一目录结构

PilotCode 将所有用户级数据统一存放在 `~/.pilotcode/` 下，替代原先分散在 `~/.config/pilotcode/`、`~/.local/share/pilotcode/`、`~/.cache/pilotcode/` 中的文件。

---

## 设计目标

1. **一目了然** — 所有 PilotCode 数据在一个根目录下，便于备份、迁移和清理。
2. **语义分层** — 按 `config` / `data` / `cache` / `themes` 区分数据性质，明确哪些可以删除、哪些需要备份。
3. **跨平台一致** — Windows、Linux、macOS 使用相同的相对结构，平台差异由 `utils/paths.py` 封装。
4. **向后兼容** — 提供自动迁移脚本，将旧路径数据无损迁移到新位置。

---

## 目录布局

### 用户级（全局）

```
~/.pilotcode/
├── config/                     # 用户可编辑，建议备份
│   ├── settings.json           # 全局配置（API Key、模型、主题等）
│   └── model_capability.json   # 本地模型能力缓存
├── data/                       # 持久化应用状态，建议备份
│   ├── sessions/               # 会话持久化文件（JSON Lines 格式）
│   ├── agents/                 # Agent 状态存储
│   ├── knowhow/                # Know-how 规则存储
│   ├── forks.json              # Fork 记录
│   └── input_history.json      # 输入历史
├── cache/                      # 可安全删除，会自动重建
│   ├── prompt_cache/           # Prompt 缓存
│   ├── embeddings/             # 语义搜索向量缓存
│   ├── index/                  # 代码索引缓存
│   ├── plans/                  # Plan 模式缓存
│   └── update_check.json       # 更新检查标记
└── themes/                     # TUI 主题文件
```

### 项目级（每个项目独立）

```
{project}/.pilotcode/
├── memory/                     # 项目记忆知识库
│   ├── facts.jsonl
│   ├── bugs.jsonl
│   ├── decisions.jsonl
│   └── qa.jsonl
├── snapshots/                  # 代码快照
├── project_memory.json         # 项目记忆索引
└── backups/                    # FileEdit 自动备份
```

> **注意**：项目级数据不随统一目录结构迁移而改变，仍保留在项目根目录的 `.pilotcode/` 中。

---

## 与旧路径的对照

| 数据类型 | 旧路径 | 新路径 |
|----------|--------|--------|
| 全局配置 | `~/.config/pilotcode/settings.json` | `~/.pilotcode/config/settings.json` |
| 会话数据 | `~/.local/share/pilotcode/sessions/` | `~/.pilotcode/data/sessions/` |
| 代码索引缓存 | `~/.cache/pilotcode/index_cache/` | `~/.pilotcode/cache/index/` |
| Prompt 缓存 | `~/.cache/pilotcode/prompt_cache/` | `~/.pilotcode/cache/prompt_cache/` |
| 向量缓存 | `~/.cache/pilotcode/embeddings/` | `~/.pilotcode/cache/embeddings/` |
| 主题文件 | `~/.config/pilotcode/themes/` | `~/.pilotcode/themes/` |
| 插件安装 | `~/.config/pilotcode/plugins/` | `~/.pilotcode/config/plugins/` |

---

## 代码中的路径管理

所有路径统一通过 `src/pilotcode/utils/paths.py` 管理：

```python
from pilotcode.utils.paths import (
    get_config_dir,      # ~/.pilotcode/config
    get_data_dir,        # ~/.pilotcode/data
    get_cache_dir,       # ~/.pilotcode/cache
    get_themes_dir,      # ~/.pilotcode/themes
    get_sessions_dir,    # ~/.pilotcode/data/sessions
    get_index_cache_dir, # ~/.pilotcode/cache/index
)
```

**原则**：代码中不应直接硬编码路径字符串，一律通过 `paths.py` 获取。

---

## 迁移说明

首次启动新版 PilotCode 时，系统会自动检测旧路径是否存在数据。如果存在，会执行以下迁移：

1. 创建 `~/.pilotcode/` 及子目录
2. 将 `~/.config/pilotcode/` 中的配置文件移动到 `~/.pilotcode/config/`
3. 将 `~/.local/share/pilotcode/` 中的会话、Agent 数据移动到 `~/.pilotcode/data/`
4. 将 `~/.cache/pilotcode/` 中的缓存移动到 `~/.pilotcode/cache/`
5. 迁移完成后，旧目录保留但不再使用（可手动删除）

---

## 备份与清理建议

### 需要备份的内容

```bash
# 配置 + 数据（体积小，价值高）
tar czf pilotcode-backup.tar.gz ~/.pilotcode/config ~/.pilotcode/data
```

### 可以安全删除的内容

```bash
# 缓存（会自动重建）
rm -rf ~/.pilotcode/cache/*

# 清理旧的已归档会话段
# （系统会自动保留最多 2 个数据段）
```

---

## 相关文档

- [会话管理](./session-management.md) — 会话数据的存储格式和自动保存机制
- [代码索引](./code-indexing.md) — 索引缓存的存储位置和增量更新策略
- [模型配置](./model-configuration.md) — 配置文件的层级和加载优先级
