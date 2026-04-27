# CodeIndex 工具

代码库索引管理工具。

## 作用

- 索引代码库文件
- 管理索引状态
- 导出/导入索引
- **报告索引进度**（基于语言混合估算 ETA）

## 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `action` | string | ✅ | 操作类型 |
| `incremental` | boolean | ❌ | 是否增量索引 |
| `file_path` | string | ❌ | 导出/导入的文件路径 |

## Action 类型

| Action | 说明 |
|--------|------|
| `index` | 索引代码库 |
| `stats` | 查看统计信息 |
| `clear` | 清除索引 |
| `export` | 导出索引 |
| `import` | 导入索引 |

## 使用示例

### 索引代码库

```python
# 增量索引（推荐日常使用）
# 自动使用 mtime + SHA256 双层过滤检测变更文件
# 自动清理已删除文件的索引
CodeIndex(action="index", incremental=True)

# 完整索引
CodeIndex(action="index", incremental=False)
```

### 查看统计

```python
CodeIndex(action="stats")
```

### 导出导入

```python
# 导出
CodeIndex(action="export", file_path="index.json")

# 导入
CodeIndex(action="import", file_path="index.json")
```

## 进度报告

索引工具支持 `on_progress` 回调，可用于 WebSocket/TUI 实时显示进度：

```python
# 估计索引时间 >30s 时自动启用控制台进度输出
# 也可通过回调集成到前端
```

输出示例（预计 >30s 时）：
```
[CodeIndex] Estimated indexing time: 45s for 485 files. Progress will be shown.
[CodeIndex] 100/485 (21%) ~35s remaining
```

## 使用场景

### 场景1：首次索引

```python
# 完整索引项目
CodeIndex(action="index", incremental=False)
```

### 场景2：日常更新

```python
# 代码变化后增量更新
CodeIndex(action="index", incremental=True)
```

### 场景3：备份索引

```python
# 导出索引备份
CodeIndex(action="export", file_path="backup/index_$(date).json")
```

## 输出示例

```
Indexed 369 files
  Symbols: 3574
  Snippets: 1777
  Languages: python: 350, cpp: 15, c: 4
```

## 相关工具

- **CodeSearch** - 搜索代码
- **CodeContext** - 构建代码上下文

## 对应的命令

- `/index` - 更方便的索引命令
